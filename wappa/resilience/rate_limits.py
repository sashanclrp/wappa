"""Meta rate limits: one async governor for every Platform call.

Meta answers an over-budget call with an error code, and a call made while
blocked still counts against the budget, so retrying in a loop extends the
block (live evidence and sources: the Instagram conversations PRD,
``references/rate-limits.md``). The governor sits at each adapter's transport
choke point (Instagram ``InstagramGraphClient.request``, WhatsApp
``WhatsAppClient``) so sends, uploads, comment actions and reads all obey it:

- **Short limits** (per second, per recipient pair): the call waits with
  ``asyncio.sleep`` and retries, bounded by ``RateLimitPolicy.max_wait``. A
  rate-limit refusal means Meta did not process the call, so the retry cannot
  duplicate a message. Only the task that sent waits; other Users' webhooks
  run in their own tasks.
- **Long limits** (the app's hourly budget, a business account's daily
  budget): no retry. The scope is blocked for a cooldown (Meta's
  ``estimated_time_to_regain_access`` when it gives one), and calls in that
  scope return ``rate_limited`` with ``retry_after`` at once, without calling
  Meta. The Host decides whether to retry later.
- **Pacing**: calls per account are spaced to Meta's per-second send rates
  (Instagram 10/s for audio and video, 100/s otherwise; WhatsApp 80/s).
- **Usage**: ``x-app-usage`` and ``X-Business-Use-Case-Usage`` are read on
  every response; crossing ``usage_warning_percent`` logs a warning.

State is in process memory: each worker process keeps its own view.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from wappa.core.logging.logger import get_logger

logger = get_logger(__name__)


class RateScope(StrEnum):
    """Who a limit is counted for."""

    APP = "app"  # the whole Meta app on one Platform (every Inbox)
    ACCOUNT = "account"  # one Inbox: Instagram account or WhatsApp number
    PAIR = "pair"  # one Inbox and one recipient (WhatsApp pair rate)


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    scope: RateScope
    transient: bool  # True: wait and retry inside the call
    base_delay: float  # seconds before the first retry (or the cooldown base)


# Meta's codes, by Platform. Transient ones are per-second or per-pair limits;
# the rest are hourly or daily budgets. Codes that mean "restricted for
# quality" (WhatsApp 131048, 131064) are not rate limits and stay rejections.
RULES: dict[str, dict[str, RateLimitRule]] = {
    "instagram": {
        "4": RateLimitRule(RateScope.APP, False, 300.0),
        "17": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
        "32": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
        "613": RateLimitRule(RateScope.ACCOUNT, True, 1.0),
        "80002": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
        "80006": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
    },
    "whatsapp": {
        "4": RateLimitRule(RateScope.APP, False, 300.0),
        "80007": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
        "130429": RateLimitRule(RateScope.ACCOUNT, True, 1.0),
        "131056": RateLimitRule(RateScope.PAIR, True, 1.0),  # Meta: 4^X seconds
        "131057": RateLimitRule(RateScope.ACCOUNT, True, 10.0),
        "133016": RateLimitRule(RateScope.ACCOUNT, False, 300.0),
    },
}


def rate_limit_rule(platform: str, code: str | None) -> RateLimitRule | None:
    """The rule for Meta's ``code`` (``"613/2534040"`` matches ``"613"``)."""
    if not code:
        return None
    table = RULES.get(platform, {})
    return table.get(code) or table.get(code.split("/", 1)[0])


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """How the governor waits, blocks and paces. Defaults suit production.

    ``max_wait``: total seconds one call may sleep for short limits before it
    returns ``rate_limited``. ``cooldown_max``: cap for long-limit cooldowns,
    which double on each consecutive block. ``send_rates``: calls per second
    per account and lane; ``None`` turns pacing off.
    """

    max_wait: float = 30.0
    max_retries: int = 3
    cooldown_max: float = 3600.0
    usage_warning_percent: float = 80.0
    send_rates: Mapping[str, Mapping[str, float]] | None = field(
        default_factory=lambda: {
            "instagram": {"media": 10.0, "default": 100.0},
            "whatsapp": {"default": 80.0},
        }
    )


@dataclass(frozen=True, slots=True)
class RateTarget:
    """One call's place in Meta's budgets."""

    platform: str
    account: str  # the Inbox ID
    recipient: str | None = None  # for pair limits
    lane: str = "default"  # "media" for Instagram audio and video

    def key(self, scope: RateScope) -> tuple[str, ...]:
        if scope is RateScope.APP:
            return (self.platform, "app")
        if scope is RateScope.ACCOUNT:
            return (self.platform, "account", self.account)
        return (self.platform, "pair", self.account, self.recipient or "")


@dataclass(frozen=True, slots=True)
class RateLimitHit:
    """What a response says about rate limits; ``None`` from ``hit_of`` = no hit."""

    code: str
    retry_after: float | None = None  # Meta's own hint, in seconds


@dataclass(frozen=True, slots=True)
class RateLimited:
    """A call Wappa did not complete because of a rate limit.

    Either Meta refused it (and short retries ran out) or the scope was
    already blocked and Meta was not called. Nothing was delivered.
    """

    code: str
    retry_after: float
    called: bool  # False: blocked locally, no call reached Meta

    @property
    def error(self) -> str:
        where = "Meta rate limit" if self.called else "rate limit still active"
        return (
            f"{where} (code {self.code}); not sent, retry after {self.retry_after:.0f}s"
        )


class RateLimitedError(Exception):
    """Raised by transports that report failure by exception (WhatsApp)."""

    def __init__(self, limited: RateLimited) -> None:
        super().__init__(limited.error)
        self.limited = limited

    @property
    def code(self) -> str:
        return self.limited.code

    @property
    def retry_after(self) -> float:
        return self.limited.retry_after


USAGE_HEADERS = ("x-app-usage", "x-business-use-case-usage")


def usage_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Only Meta's usage headers, for ``RateLimitGovernor.observe_usage``."""
    return {name: headers[name] for name in USAGE_HEADERS if name in headers}


def rewind(files: Mapping[str, object] | None) -> None:
    """Seek every uploaded file back to 0, so a retried upload sends it again."""
    for value in (files or {}).values():
        content = value[1] if isinstance(value, tuple) and len(value) > 1 else value
        seek = getattr(content, "seek", None)
        if callable(seek):
            seek(0)


@dataclass(slots=True)
class _Block:
    code: str
    until: float
    transient: bool


class RateLimitGovernor:
    """Process-wide rate-limit state. Use ``rate_governor()`` for the shared one."""

    def __init__(
        self,
        policy: RateLimitPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.policy = policy or RateLimitPolicy()
        self._clock = clock
        self._sleep = sleep
        self._blocks: dict[tuple[str, ...], _Block] = {}
        self._strikes: dict[tuple[str, ...], int] = {}
        self._next_slot: dict[tuple[str, ...], float] = {}
        self._warned: dict[tuple[str, ...], float] = {}

    # ── public ──────────────────────────────────────────────────────────

    async def run[T](
        self,
        target: RateTarget,
        call: Callable[[], Awaitable[T]],
        hit_of: Callable[[T], RateLimitHit | None],
    ) -> T | RateLimited:
        """Run ``call`` within Meta's limits for ``target``.

        Returns the call's own result, or ``RateLimited`` when a limit stopped
        it. Waiting is ``asyncio.sleep``: it holds this task only.
        """
        waited = 0.0
        for attempt in range(self.policy.max_retries + 1):
            block = self._active_block(target)
            if block is not None:
                code, remaining, transient = block
                if not transient or waited + remaining > self.policy.max_wait:
                    return RateLimited(code, remaining, called=False)
                await self._sleep(remaining)
                waited += remaining
            await self._pace(target)
            result = await call()
            hit = hit_of(result)
            if hit is None:
                self._clear_strikes(target)
                return result
            rule = rate_limit_rule(target.platform, hit.code)
            if rule is None:  # caller flagged a code the table lacks: treat as long
                rule = RateLimitRule(RateScope.ACCOUNT, False, 300.0)
            wait = self._record(target, rule, hit, attempt)
            last = attempt == self.policy.max_retries
            if not rule.transient or last or waited + wait > self.policy.max_wait:
                return RateLimited(hit.code, wait, called=True)
            logger.warning(
                "Rate limit %s on %s %s; retrying in %.1fs (attempt %s)",
                hit.code,
                target.platform,
                target.account,
                wait,
                attempt + 1,
            )
            await self._sleep(wait)
            waited += wait
        raise AssertionError("unreachable")  # pragma: no cover

    def observe_usage(
        self, target: RateTarget, headers: Mapping[str, str]
    ) -> float | None:
        """Read Meta's usage headers; warn near the limit.

        Returns Meta's ``estimated_time_to_regain_access`` in seconds when
        the account is currently throttled, else ``None``.
        """
        app = _json(headers.get("x-app-usage"))
        if isinstance(app, Mapping):
            self._warn_usage(target, "app", _max_percent(app))
        regain: float | None = None
        buc = _json(headers.get("x-business-use-case-usage"))
        if isinstance(buc, Mapping):
            for entries in buc.values():
                for entry in entries if isinstance(entries, list) else []:
                    if not isinstance(entry, Mapping):
                        continue
                    self._warn_usage(
                        target,
                        f"business:{entry.get('type', '?')}",
                        _max_percent(entry),
                    )
                    minutes = entry.get("estimated_time_to_regain_access")
                    if isinstance(minutes, int | float) and minutes > 0:
                        regain = max(regain or 0.0, float(minutes) * 60)
        return regain

    def blocked_for(self, target: RateTarget) -> float | None:
        """Seconds until ``target`` may call Meta again, or ``None``."""
        block = self._active_block(target)
        return block[1] if block else None

    def reset(self) -> None:
        """Forget every block, strike and pacing slot (tests, operator reset)."""
        self._blocks.clear()
        self._strikes.clear()
        self._next_slot.clear()
        self._warned.clear()

    # ── internals ───────────────────────────────────────────────────────

    def _active_block(self, target: RateTarget) -> tuple[str, float, bool] | None:
        now = self._clock()
        worst: tuple[str, float, bool] | None = None
        for scope in RateScope:
            if scope is RateScope.PAIR and not target.recipient:
                continue
            key = target.key(scope)
            block = self._blocks.get(key)
            if block is None:
                continue
            if block.until <= now:
                del self._blocks[key]
                continue
            remaining = block.until - now
            if worst is None or remaining > worst[1]:
                worst = (block.code, remaining, block.transient)
        return worst

    def _record(
        self, target: RateTarget, rule: RateLimitRule, hit: RateLimitHit, attempt: int
    ) -> float:
        key = target.key(rule.scope)
        if rule.transient:
            wait = hit.retry_after or rule.base_delay * (4**attempt)
        else:
            strikes = self._strikes.get(key, 0) + 1
            self._strikes[key] = strikes
            wait = hit.retry_after or rule.base_delay * (2 ** (strikes - 1))
            wait = min(wait, self.policy.cooldown_max)
            logger.error(
                "Rate limit %s on %s %s (%s scope): calls blocked for %.0fs",
                hit.code,
                target.platform,
                target.account,
                rule.scope.value,
                wait,
            )
        self._blocks[key] = _Block(hit.code, self._clock() + wait, rule.transient)
        return wait

    def _clear_strikes(self, target: RateTarget) -> None:
        for scope in (RateScope.APP, RateScope.ACCOUNT):
            self._strikes.pop(target.key(scope), None)

    async def _pace(self, target: RateTarget) -> None:
        rates = (self.policy.send_rates or {}).get(target.platform)
        if not rates:
            return
        rate = rates.get(target.lane) or rates.get("default")
        if not rate:
            return
        key = (*target.key(RateScope.ACCOUNT), target.lane)
        now = self._clock()
        slot = max(now, self._next_slot.get(key, now))
        self._next_slot[key] = slot + 1.0 / rate
        if slot > now:
            await self._sleep(slot - now)

    def _warn_usage(self, target: RateTarget, kind: str, percent: float | None) -> None:
        if percent is None or percent < self.policy.usage_warning_percent:
            return
        key = (target.platform, target.account, kind)
        now = self._clock()
        if now - self._warned.get(key, -1e9) < 60:
            return
        self._warned[key] = now
        logger.warning(
            "Meta %s usage at %.0f%% for %s %s (limit at 100%%)",
            kind,
            percent,
            target.platform,
            target.account,
        )


def _json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _max_percent(usage: Mapping[str, object]) -> float | None:
    values = [
        float(v)
        for k in ("call_count", "total_cputime", "total_time")
        if isinstance(v := usage.get(k), int | float)
    ]
    return max(values) if values else None


_governor = RateLimitGovernor()


def rate_governor() -> RateLimitGovernor:
    """The process-wide governor every adapter uses."""
    return _governor


def use_rate_governor(governor: RateLimitGovernor) -> None:
    """Replace the process-wide governor (a custom policy, or tests)."""
    global _governor
    _governor = governor


__all__ = [
    "RULES",
    "RateLimitGovernor",
    "RateLimitHit",
    "RateLimitPolicy",
    "RateLimitRule",
    "RateLimited",
    "RateLimitedError",
    "RateScope",
    "USAGE_HEADERS",
    "RateTarget",
    "rate_governor",
    "rate_limit_rule",
    "rewind",
    "usage_headers",
    "use_rate_governor",
]
