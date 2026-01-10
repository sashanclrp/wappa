"""
Base interface for score modules following Interface Segregation Principle.

This module defines the common interface that all score modules must implement,
ensuring consistent behavior across different business logic handlers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import Logger

from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.webhooks import IncomingMessageWebhook


@dataclass
class ScoreDependencies:
    """
    Dependencies required by score modules.

    This follows Dependency Inversion Principle by providing
    abstractions that score modules depend on.

    The cache_factory provides context-aware cache instances that are created
    per-request with tenant and user identity already injected.
    """

    messenger: WhatsAppMessenger
    cache_factory: ICacheFactory
    logger: Logger


class ScoreBase(ABC):
    """
    Base class for all score modules.

    Implements Interface Segregation Principle by providing
    only the methods that score modules actually need.
    """

    def __init__(self, dependencies: ScoreDependencies):
        """
        Initialize score with injected dependencies.

        Args:
            dependencies: Required dependencies for the score
        """
        self.messenger = dependencies.messenger
        self.cache_factory = dependencies.cache_factory
        self.logger = dependencies.logger

        # Track processing statistics
        self._processing_count = 0
        self._error_count = 0

    # ---- Cache accessor properties for cleaner code in subclasses ----
    @property
    def user_cache(self):
        """Get user cache from factory (pre-bound to current user context)."""
        return self.cache_factory.create_user_cache()

    @property
    def table_cache(self):
        """Get table cache from factory (pre-bound to current tenant context)."""
        return self.cache_factory.create_table_cache()

    @property
    def state_cache(self):
        """Get state cache from factory (pre-bound to current user context)."""
        return self.cache_factory.create_state_cache()

    @property
    def score_name(self) -> str:
        """Return the name of this score module."""
        return self.__class__.__name__

    @property
    def processing_stats(self) -> dict:
        """Return processing statistics for this score."""
        return {
            "processed": self._processing_count,
            "errors": self._error_count,
            "success_rate": (
                (self._processing_count - self._error_count) / self._processing_count
                if self._processing_count > 0
                else 0.0
            ),
        }

    @abstractmethod
    async def can_handle(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Determine if this score can handle the given webhook.

        Args:
            webhook: Incoming message webhook to evaluate

        Returns:
            True if this score should process the webhook
        """
        pass

    @abstractmethod
    async def process(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Process the webhook with this score's business logic.

        Args:
            webhook: Incoming message webhook to process

        Returns:
            True if processing was successful and complete
        """
        pass

    async def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available.

        Returns:
            True if all dependencies are valid
        """
        if not all([self.messenger, self.cache_factory, self.logger]):
            self.logger.error(f"{self.score_name}: Missing required dependencies")
            return False
        return True

    def _record_processing(self, success: bool = True) -> None:
        """Record processing statistics."""
        self._processing_count += 1
        if not success:
            self._error_count += 1

    async def _handle_error(self, error: Exception, context: str) -> None:
        """
        Handle errors consistently across score modules.

        Args:
            error: Exception that occurred
            context: Context where error occurred
        """
        self._record_processing(success=False)
        self.logger.error(
            f"{self.score_name} error in {context}: {str(error)}", exc_info=True
        )

    def __str__(self) -> str:
        """String representation of the score."""
        return f"{self.score_name}(processed={self._processing_count}, errors={self._error_count})"


class ScoreRegistry:
    """
    Registry for managing score modules.

    Implements Open/Closed Principle by allowing new scores
    to be registered without modifying existing code.
    """

    def __init__(self):
        self._scores: list[ScoreBase] = []

    def register_score(self, score: ScoreBase) -> None:
        """Register a score module."""
        if not isinstance(score, ScoreBase):
            raise ValueError("Score must inherit from ScoreBase")

        self._scores.append(score)

    def get_scores(self) -> list[ScoreBase]:
        """Get all registered scores."""
        return self._scores.copy()

    async def find_handler(self, webhook: IncomingMessageWebhook) -> ScoreBase | None:
        """
        Find the first score that can handle the webhook.

        Args:
            webhook: Webhook to find handler for

        Returns:
            Score that can handle the webhook, or None
        """
        for score in self._scores:
            try:
                if await score.can_handle(webhook):
                    return score
            except Exception as e:
                # Log error but continue to next score
                score.logger.error(
                    f"Error checking if {score.score_name} can handle webhook: {e}"
                )

        return None

    def get_score_stats(self) -> dict:
        """Get statistics for all registered scores."""
        return {score.score_name: score.processing_stats for score in self._scores}
