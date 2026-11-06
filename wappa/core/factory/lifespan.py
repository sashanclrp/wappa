"""Lifespan hook runners: priority-ordered startup and shutdown hook execution."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from ..logging.logger import get_app_logger


async def run_startup_hooks(
    startup_hooks: list[tuple[Callable, int]], app: FastAPI
) -> None:
    """
    Execute all startup hooks in unified priority order.

    This replaces the old plugin-specific startup execution with a unified
    approach where all hooks (from plugins and user code) are executed
    in a single priority-ordered sequence.

    Args:
        app: FastAPI application instance
    """
    logger = get_app_logger()

    try:
        # Execute all startup hooks in priority order (10, 20, 30, ...)
        sorted_hooks = sorted(startup_hooks, key=lambda x: x[1])

        if not sorted_hooks:
            logger.debug("No startup hooks registered")
            return

        logger.debug(
            f"Executing {len(sorted_hooks)} startup hooks in priority order..."
        )

        for hook, priority in sorted_hooks:
            hook_name = getattr(hook, "__name__", "anonymous_hook")
            logger.debug(
                f"⚡ Executing startup hook: {hook_name} (priority: {priority})"
            )

            try:
                await hook(app)
                logger.debug(f"✅ Startup hook {hook_name} completed")
            except Exception as e:
                logger.error(f"❌ Startup hook {hook_name} failed: {e}", exc_info=True)
                raise  # Re-raise to fail fast

    except Exception as e:
        logger.error(f"❌ Startup sequence failed: {e}", exc_info=True)
        raise


async def run_shutdown_hooks(
    shutdown_hooks: list[tuple[Callable, int]], app: FastAPI
) -> None:
    """
    Execute all shutdown hooks in reverse priority order.

    This replaces the old plugin-specific shutdown execution with a unified
    approach where all hooks are executed in reverse priority order,
    with error isolation to prevent shutdown cascading failures.

    Args:
        app: FastAPI application instance
    """
    logger = get_app_logger()

    # Execute shutdown hooks in reverse priority order (90, 70, 50, 30, 20, 10)
    sorted_hooks = sorted(shutdown_hooks, key=lambda x: x[1], reverse=True)

    if not sorted_hooks:
        logger.debug("No shutdown hooks registered")
        return

    logger.debug(
        f"Executing {len(sorted_hooks)} shutdown hooks in reverse priority order..."
    )

    for hook, priority in sorted_hooks:
        hook_name = getattr(hook, "__name__", "anonymous_hook")
        try:
            logger.debug(
                f"🛑 Executing shutdown hook: {hook_name} (priority: {priority})"
            )
            await hook(app)
            logger.debug(f"✅ Shutdown hook {hook_name} completed")
        except Exception as e:
            # Don't re-raise in shutdown - log and continue with other hooks
            logger.error(f"❌ Error in shutdown hook {hook_name}: {e}", exc_info=True)
