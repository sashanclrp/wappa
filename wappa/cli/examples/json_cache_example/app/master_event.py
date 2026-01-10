"""
Master Event Handler - WappaEventHandler implementation following SOLID principles.

This module defines the main WappaEventHandler that:
- Extends WappaEventHandler with proper method signatures
- Coordinates multiple score modules using dependency injection
- Follows Single Responsibility Principle for event handling
- Uses Open/Closed Principle for score module extensibility
- Implements Liskov Substitution for handler compatibility
- Uses Interface Segregation with focused score interfaces
- Follows Dependency Inversion with injected dependencies
"""

from typing import Any

from wappa import WappaEventHandler
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

from .scores import AVAILABLE_SCORES, ScoreDependencies
from .scores.score_base import ScoreRegistry
from .utils.message_utils import extract_user_data, sanitize_message_text


class JSONCacheExampleHandler(WappaEventHandler):
    """
    Main WappaEventHandler implementation for JSON cache example following SOLID principles.

    This handler serves as the main entry point for the Wappa framework and demonstrates:
    - Proper WappaEventHandler method implementations
    - SOLID architecture with score module orchestration
    - Dependency injection and lifecycle management
    - Professional error handling and logging
    """

    def __init__(self):
        """Initialize the JSON cache example handler."""
        super().__init__()

        # Score module registry (following Open/Closed Principle)
        self.score_registry = ScoreRegistry()

        # Processing statistics
        self._total_messages = 0
        self._successful_processing = 0
        self._failed_processing = 0

        # Master handler state
        self._initialized = False

        self.logger.info(
            "🎯 JSONCacheExampleHandler initialized - ready for SOLID architecture setup"
        )

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Main message processing method required by WappaEventHandler.

        This method orchestrates score modules following SOLID principles and
        demonstrates proper webhook processing with dependency injection.

        Args:
            webhook: Incoming message webhook to process
        """
        self._total_messages += 1
        start_time = self._get_current_timestamp()

        try:
            # Initialize SOLID architecture on first message if not already done
            if not self._initialized:
                await self._initialize_solid_architecture()

            # Extract basic user information for logging
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]
            message_text = webhook.get_message_text() or "[NON-TEXT MESSAGE]"

            self.logger.info(
                f"📨 Processing message from {user_id}: "
                f"{sanitize_message_text(message_text)[:50]}..."
            )

            # Execute score module processing pipeline
            processing_result = await self._execute_score_pipeline(webhook)

            # Record processing results
            if processing_result["success"]:
                self._successful_processing += 1
                processing_time = self._get_current_timestamp() - start_time

                self.logger.info(
                    f"✅ Message processed successfully in {processing_time:.2f}s "
                    f"(processed by {processing_result['processed_count']} score modules)"
                )
            else:
                self._failed_processing += 1
                self.logger.warning(
                    f"⚠️ Message processing completed with issues: "
                    f"{processing_result.get('error', 'Unknown error')}"
                )

                # Send fallback response to user
                await self._send_error_response(
                    webhook, processing_result.get("error", "Processing error")
                )

        except Exception as e:
            self._failed_processing += 1
            self.logger.error(
                f"❌ Critical error in message processing: {e}", exc_info=True
            )
            await self._send_error_response(webhook, f"System error: {str(e)}")

    async def process_status(self, webhook: StatusWebhook) -> None:
        """
        Process status webhooks from WhatsApp Business API.

        Args:
            webhook: Status webhook containing delivery status information
        """
        try:
            status_value = webhook.status.value
            recipient = webhook.recipient_id

            self.logger.info(
                f"📊 Message status: {status_value.upper()} for {recipient}"
            )

            # You can add custom status processing logic here
            # For example, updating delivery statistics or handling failed deliveries

        except Exception as e:
            self.logger.error(f"❌ Error processing status webhook: {e}", exc_info=True)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """
        Process error webhooks from WhatsApp Business API.

        Args:
            webhook: Error webhook containing error information
        """
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"🚨 WhatsApp API error: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title}"
            )

            # Record error in statistics
            self._failed_processing += 1

            # You can add custom error handling logic here
            # For example, alerting systems or retry mechanisms

        except Exception as e:
            self.logger.error(f"❌ Error processing error webhook: {e}", exc_info=True)

    async def _initialize_solid_architecture(self) -> None:
        """
        Initialize SOLID architecture with score modules and dependency injection.

        This method demonstrates Dependency Inversion Principle by injecting
        abstractions and follows Single Responsibility Principle.
        """
        try:
            if not self.validate_dependencies():
                self.logger.error(
                    "❌ Dependencies not properly injected - cannot initialize SOLID architecture"
                )
                return

            if not self.cache_factory:
                self.logger.error(
                    "❌ Cache factory not available - cannot initialize SOLID architecture"
                )
                return

            # Create dependencies container with cache factory (Dependency Inversion)
            # The cache factory creates context-aware cache instances per-request
            # with tenant and user identity already bound
            dependencies = ScoreDependencies(
                messenger=self.messenger,
                cache_factory=self.cache_factory,
                logger=self.logger,
            )

            # Auto-register all available score modules (Open/Closed Principle)
            registered_count = 0
            for score_class in AVAILABLE_SCORES:
                try:
                    # Instantiate score with dependency injection
                    score_instance = score_class(dependencies)
                    self.score_registry.register_score(score_instance)
                    registered_count += 1

                    self.logger.info(
                        f"✅ Registered score module: {score_instance.score_name}"
                    )

                except Exception as e:
                    self.logger.error(
                        f"❌ Failed to register {score_class.__name__}: {e}"
                    )

            self._initialized = True
            self.logger.info(
                f"🎯 SOLID architecture initialized successfully: {registered_count} score modules registered"
            )

        except Exception as e:
            self.logger.error(
                f"❌ Critical error initializing SOLID architecture: {e}", exc_info=True
            )
            raise

    async def _execute_score_pipeline(
        self, webhook: IncomingMessageWebhook
    ) -> dict[str, Any]:
        """
        Execute the score module processing pipeline.

        Processes webhook through all applicable score modules following
        the Chain of Responsibility pattern.

        Args:
            webhook: Webhook to process

        Returns:
            Processing result with success status and metadata
        """
        try:
            if not self._initialized:
                return {
                    "success": False,
                    "error": "SOLID architecture not initialized",
                    "processed_count": 0,
                }

            scores = self.score_registry.get_scores()
            processed_count = 0
            processing_errors = []

            # Process webhook through all applicable score modules
            for score in scores:
                try:
                    # Check if score can handle this webhook (Interface Segregation)
                    can_handle = await score.can_handle(webhook)

                    if can_handle:
                        self.logger.debug(f"🎯 Processing with {score.score_name}")

                        # Process with the score module
                        success = await score.process(webhook)

                        if success:
                            processed_count += 1
                            self.logger.debug(
                                f"✅ {score.score_name} completed successfully"
                            )
                        else:
                            processing_errors.append(
                                f"{score.score_name}: Processing failed"
                            )
                            self.logger.warning(
                                f"⚠️ {score.score_name} reported processing failure"
                            )
                    else:
                        self.logger.debug(
                            f"⏭️ {score.score_name} skipped (cannot handle this webhook)"
                        )

                except Exception as score_error:
                    processing_errors.append(f"{score.score_name}: {str(score_error)}")
                    self.logger.error(
                        f"❌ Error in {score.score_name}: {score_error}", exc_info=True
                    )

            # Determine overall success
            overall_success = processed_count > 0 and len(processing_errors) == 0

            return {
                "success": overall_success,
                "processed_count": processed_count,
                "total_scores": len(scores),
                "errors": processing_errors if processing_errors else None,
                "message": (
                    f"Processed by {processed_count}/{len(scores)} score modules"
                    + (
                        f" with {len(processing_errors)} errors"
                        if processing_errors
                        else ""
                    )
                ),
            }

        except Exception as e:
            self.logger.error(
                f"❌ Critical error in score pipeline: {e}", exc_info=True
            )
            return {
                "success": False,
                "processed_count": 0,
                "error": f"Pipeline error: {str(e)}",
            }

    async def _send_error_response(
        self, webhook: IncomingMessageWebhook, error_details: str
    ) -> None:
        """
        Send user-friendly error response when processing fails.

        Args:
            webhook: Original webhook that failed to process
            error_details: Details about the error for logging
        """
        try:
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]

            error_message = (
                "🚨 SOLID JSON Cache Example\n\n"
                "❌ An error occurred while processing your message.\n"
                "Our team has been notified and will resolve this issue soon.\n\n"
                "Please try again later or contact support if the problem persists."
            )

            result = await self.messenger.send_text(
                recipient=user_id,
                text=error_message,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(f"🚨 Error response sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send error response: {result.error}")

        except Exception as e:
            self.logger.error(f"❌ Error sending error response: {e}")

    def _get_current_timestamp(self) -> float:
        """Get current timestamp for performance measurement."""
        import time

        return time.time()

    async def get_handler_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive handler and score module statistics.

        Returns:
            Dictionary with processing statistics and score module metrics
        """
        try:
            # Calculate success rate
            success_rate = (
                (self._successful_processing / self._total_messages)
                if self._total_messages > 0
                else 0.0
            )

            # Get score-specific statistics if initialized
            score_stats = {}
            if self._initialized:
                score_stats = self.score_registry.get_score_stats()

            return {
                "handler_status": "initialized"
                if self._initialized
                else "pending_initialization",
                "total_messages": self._total_messages,
                "successful_processing": self._successful_processing,
                "failed_processing": self._failed_processing,
                "success_rate": success_rate,
                "registered_scores": len(self.score_registry.get_scores())
                if self._initialized
                else 0,
                "score_modules": score_stats,
            }

        except Exception as e:
            self.logger.error(f"❌ Error collecting handler statistics: {e}")
            return {"error": f"Statistics collection failed: {str(e)}"}

    async def validate_system_health(self) -> dict[str, Any]:
        """
        Validate system health including all score modules and dependencies.

        Returns:
            Health check results for the entire system
        """
        try:
            health_results = {
                "overall_healthy": True,
                "initialized": self._initialized,
                "components": {},
                "registered_scores": len(self.score_registry.get_scores())
                if self._initialized
                else 0,
            }

            # Check core dependencies
            core_components = {
                "messenger": self.messenger,
                "cache_factory": self.cache_factory,
            }

            for component_name, component in core_components.items():
                if component is not None:
                    health_results["components"][component_name] = "Available"
                else:
                    health_results["components"][component_name] = "Missing"
                    health_results["overall_healthy"] = False

            # Check score modules if initialized
            if self._initialized:
                scores = self.score_registry.get_scores()
                for score in scores:
                    try:
                        # Basic validation check
                        is_valid = await score.validate_dependencies()
                        health_results["components"][score.score_name] = (
                            "Healthy" if is_valid else "Dependency Issues"
                        )
                        if not is_valid:
                            health_results["overall_healthy"] = False

                    except Exception as e:
                        health_results["components"][score.score_name] = (
                            f"Error: {str(e)}"
                        )
                        health_results["overall_healthy"] = False

            return health_results

        except Exception as e:
            self.logger.error(f"❌ Error validating system health: {e}")
            return {"overall_healthy": False, "error": f"Health check failed: {str(e)}"}

    def __str__(self) -> str:
        """String representation of the handler."""
        return (
            f"JSONCacheExampleHandler("
            f"messages={self._total_messages}, "
            f"success_rate={self._successful_processing / max(1, self._total_messages):.2%}, "
            f"scores={len(self.score_registry.get_scores()) if self._initialized else 'pending'}, "
            f"initialized={self._initialized}"
            f")"
        )
