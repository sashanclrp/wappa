"""The Redis hash encoding is a compatibility contract, not an implementation detail.

A top-level boolean is stored as ``"1"`` / ``"0"``. Host Applications read and
write these fields directly — with `redis-cli`, from analytics jobs, from
non-Python services — so the spelling is part of Wappa's observable surface and
changing it silently breaks them. See ADR-0008.

These tests exist to make that intent explicit. If you are here because a test
failed after "fixing" the encoding: the failure is the point. Read the ADR
before changing anything.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from wappa.persistence.redis.redis_handler.utils.serde import (
    dumps,
    dumps_hash,
    loads,
    loads_hash,
)


class Inner(BaseModel):
    on: bool


class Flags(BaseModel):
    active: bool
    disabled: bool
    inner: Inner
    tags: list[bool]


# ── the contract ────────────────────────────────────────────────────────────


def test_a_top_level_boolean_is_stored_as_one_or_zero() -> None:
    """The spelling downstream apps read. Do not change without ADR-0008."""
    assert dumps(True) == "1"
    assert dumps(False) == "0"


def test_one_and_zero_read_back_as_booleans() -> None:
    assert loads("1") is True
    assert loads("0") is False


def test_a_pydantic_model_writes_its_booleans_as_one_and_zero() -> None:
    """SERDE is what translates model bools to the stored spelling."""
    encoded = dumps_hash(
        Flags(active=True, disabled=False, inner=Inner(on=True), tags=[])
    )

    assert encoded["active"] == "1"
    assert encoded["disabled"] == "0"


def test_a_model_round_trips_losslessly_through_the_hash() -> None:
    """Whatever the spelling, a typed read returns real bools."""
    flags = Flags(
        active=True, disabled=False, inner=Inner(on=False), tags=[True, False]
    )

    restored = loads_hash(dumps_hash(flags), models=Flags)

    assert restored == flags
    assert isinstance(restored, Flags)


def test_booleans_nested_inside_a_json_value_keep_json_spelling() -> None:
    """Only the top-level hash field uses 1/0; JSON payloads stay JSON.

    Worth pinning because the two spellings coexist in one row and look like
    an inconsistency until you know the field boundary is where it switches.
    """
    encoded = dumps_hash(
        Flags(active=True, disabled=False, inner=Inner(on=False), tags=[True])
    )

    assert encoded["active"] == "1"
    assert encoded["inner"] == '{"on": false}'
    assert encoded["tags"] == "[true]"


def test_plain_dicts_and_lists_are_json_all_the_way_down() -> None:
    assert dumps({"a": True}) == '{"a": true}'
    assert loads(dumps({"a": True})) == {"a": True}


# ── the accepted cost ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "reads_back_as"),
    [
        pytest.param(1, True, id="int-one-reads-as-true"),
        pytest.param(0, False, id="int-zero-reads-as-false"),
        pytest.param("1", True, id="string-one-reads-as-true"),
        pytest.param("0", False, id="string-zero-reads-as-false"),
    ],
)
def test_untyped_reads_of_one_and_zero_are_ambiguous_by_design(
    value: object, reads_back_as: bool
) -> None:
    """The known, accepted cost of the 1/0 spelling — see ADR-0008.

    An untyped read cannot tell an int 1 from a True, because they share a
    spelling. A Pydantic model settles it (the test below), which is why this
    is a cost rather than a bug: typed rows are the supported way to read.
    """
    assert loads(dumps(value)) is reads_back_as


def test_an_int_or_bool_field_resolves_the_ambiguity() -> None:
    """Declaring the type settles what ``"1"`` meant — for numbers and flags."""

    class Counter(BaseModel):
        attempts: int
        active: bool

    restored = loads_hash(dumps_hash({"attempts": 1, "active": True}), models=Counter)

    assert isinstance(restored, Counter)
    assert restored.attempts == 1 and not isinstance(restored.attempts, bool)
    assert restored.active is True


def test_a_str_field_holding_one_or_zero_fails_validation() -> None:
    """The sharp edge: a *string* "1" is unrecoverable, typed or not.

    It is stored as ``"1"``, reads back as ``True``, and a ``str`` field then
    rejects the bool. Do not store ``"1"`` / ``"0"`` as string values — use a
    real bool, a real int, or a value with a distinguishing prefix. Pinned here
    so the limit is discovered by reading tests, not by a production 500.
    """

    class Label(BaseModel):
        label: str

    with pytest.raises(ValidationError):
        loads_hash(dumps_hash({"label": "1"}), models=Label)

    # Anything that is not exactly "1" or "0" is unaffected.
    assert loads_hash(dumps_hash({"label": "1x"}), models=Label).label == "1x"


def test_other_scalars_are_unaffected() -> None:
    for value in (42, -7, 3.5, "Ada", None, [1, "a"], {"k": "v"}):
        assert loads(dumps(value)) == value
