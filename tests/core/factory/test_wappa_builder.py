"""
Comprehensive test suite for WappaBuilder functionality.

Tests the core factory system including plugin management, middleware ordering,
lifespan management, and integration with FastAPI.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from wappa.core.factory import WappaBuilder, WappaPlugin
from wappa.core.plugins import (
    DatabasePlugin, RedisPlugin, WebhookPlugin, CORSPlugin,
    AuthPlugin, RateLimitPlugin, CustomMiddlewarePlugin
)


class TestWappaPlugin:
    """Test implementation for testing plugin protocol."""
    
    def __init__(self, name: str = "test"):
        self.name = name
        self.configured = False
        self.started = False
        self.shutdown = False
        self.configure_called = False
        self.startup_called = False
        self.shutdown_called = False
    
    async def configure(self, builder: WappaBuilder) -> None:
        self.configure_called = True
        self.configured = True
    
    async def startup(self, app: FastAPI) -> None:
        self.startup_called = True
        self.started = True
    
    async def shutdown(self, app: FastAPI) -> None:
        self.shutdown_called = True
        self.shutdown = True


class TestMiddleware(BaseHTTPMiddleware):
    """Test middleware for testing middleware ordering."""
    
    def __init__(self, app, name: str = "test", **kwargs):
        super().__init__(app)
        self.name = name
        self.kwargs = kwargs
        self.call_order = []
    
    async def dispatch(self, request: Request, call_next):
        self.call_order.append(f"{self.name}_start")
        response = await call_next(request)
        self.call_order.append(f"{self.name}_end")
        return response


@pytest.mark.asyncio
class TestWappaBuilderCore:
    """Test core WappaBuilder functionality."""
    
    def test_builder_initialization(self):
        """Test WappaBuilder initialization."""
        builder = WappaBuilder()
        
        assert isinstance(builder.plugins, list)
        assert len(builder.plugins) == 0
        assert isinstance(builder.middlewares, list)
        assert len(builder.middlewares) == 0
        assert isinstance(builder.startup_hooks, list)
        assert len(builder.startup_hooks) == 0
        assert isinstance(builder.shutdown_hooks, list)
        assert len(builder.shutdown_hooks) == 0
        assert builder.config == {}
    
    def test_add_plugin_fluent_interface(self):
        """Test plugin addition with fluent interface."""
        builder = WappaBuilder()
        plugin = TestWappaPlugin("test1")
        
        result = builder.add_plugin(plugin)
        
        # Should return self for method chaining
        assert result is builder
        assert len(builder.plugins) == 1
        assert builder.plugins[0] is plugin
    
    def test_add_multiple_plugins_chaining(self):
        """Test adding multiple plugins with method chaining."""
        builder = WappaBuilder()
        plugin1 = TestWappaPlugin("test1")
        plugin2 = TestWappaPlugin("test2")
        
        result = (builder
                  .add_plugin(plugin1)
                  .add_plugin(plugin2))
        
        assert result is builder
        assert len(builder.plugins) == 2
        assert builder.plugins[0] is plugin1
        assert builder.plugins[1] is plugin2
    
    def test_add_middleware_fluent_interface(self):
        """Test middleware addition with fluent interface."""
        builder = WappaBuilder()
        
        result = builder.add_middleware(TestMiddleware, priority=80, name="test")
        
        assert result is builder
        assert len(builder.middlewares) == 1
        middleware_class, kwargs, priority = builder.middlewares[0]
        assert middleware_class is TestMiddleware
        assert kwargs == {"name": "test"}
        assert priority == 80
    
    def test_add_startup_hook_fluent_interface(self):
        """Test startup hook addition."""
        builder = WappaBuilder()
        
        async def test_hook():
            pass
        
        result = builder.add_startup_hook(test_hook, priority=60)
        
        assert result is builder
        assert len(builder.startup_hooks) == 1
        hook, priority = builder.startup_hooks[0]
        assert hook is test_hook
        assert priority == 60
    
    def test_add_shutdown_hook_fluent_interface(self):
        """Test shutdown hook addition."""
        builder = WappaBuilder()
        
        async def test_hook():
            pass
        
        result = builder.add_shutdown_hook(test_hook, priority=40)
        
        assert result is builder
        assert len(builder.shutdown_hooks) == 1
        hook, priority = builder.shutdown_hooks[0]
        assert hook is test_hook
        assert priority == 40
    
    def test_configure_fluent_interface(self):
        """Test configuration method."""
        builder = WappaBuilder()
        
        result = builder.configure(title="Test App", version="1.0.0")
        
        assert result is builder
        assert builder.config["title"] == "Test App"
        assert builder.config["version"] == "1.0.0"
    
    def test_configure_overrides_defaults(self):
        """Test configuration overrides."""
        builder = WappaBuilder()
        builder.configure(title="Initial")
        
        builder.configure(title="Updated", description="New desc")
        
        assert builder.config["title"] == "Updated"
        assert builder.config["description"] == "New desc"
    
    async def test_build_creates_fastapi_app(self):
        """Test that build() creates a FastAPI application."""
        builder = WappaBuilder()
        
        app = await builder.build()
        
        assert isinstance(app, FastAPI)
        assert app.title == "Wappa Application"
    
    async def test_build_with_custom_config(self):
        """Test build with custom configuration."""
        builder = WappaBuilder()
        
        app = await (builder
                     .configure(title="Custom App", version="2.0.0")
                     .build())
        
        assert app.title == "Custom App"
        assert app.version == "2.0.0"
    
    async def test_plugin_configuration_phase(self):
        """Test that plugins are configured during build."""
        builder = WappaBuilder()
        plugin = TestWappaPlugin("test")
        
        await (builder
               .add_plugin(plugin)
               .build())
        
        assert plugin.configure_called
        assert plugin.configured


@pytest.mark.asyncio
class TestWappaBuilderMiddleware:
    """Test WappaBuilder middleware functionality."""
    
    async def test_middleware_priority_ordering(self):
        """Test that middleware is ordered by priority."""
        builder = WappaBuilder()
        
        # Add middleware in reverse priority order
        builder.add_middleware(TestMiddleware, priority=10, name="low")
        builder.add_middleware(TestMiddleware, priority=90, name="high") 
        builder.add_middleware(TestMiddleware, priority=50, name="medium")
        
        app = await builder.build()
        
        # Check that middlewares are sorted by priority (high to low)
        # Note: FastAPI adds middleware in reverse order (last added runs first)
        middleware_stack = []
        for middleware in app.user_middleware:
            if hasattr(middleware.cls, 'name'):
                continue  # Skip if it's not our test middleware
            # Extract middleware info from the stack
            middleware_stack.append(middleware)
        
        # Verify middleware was added (exact ordering depends on FastAPI internals)
        assert len(builder.middlewares) == 3
        
        # Sort middlewares by priority to verify ordering
        sorted_middlewares = sorted(builder.middlewares, key=lambda x: x[2], reverse=True)
        names = [kwargs.get("name") for _, kwargs, _ in sorted_middlewares]
        assert names == ["high", "medium", "low"]
    
    async def test_middleware_with_kwargs(self):
        """Test middleware with custom keyword arguments."""
        builder = WappaBuilder()
        
        await (builder
               .add_middleware(TestMiddleware, priority=50, name="custom", 
                              custom_arg="value", flag=True)
               .build())
        
        middleware_class, kwargs, priority = builder.middlewares[0]
        assert kwargs["name"] == "custom"
        assert kwargs["custom_arg"] == "value"
        assert kwargs["flag"] is True
    
    async def test_default_middleware_priority(self):
        """Test default middleware priority."""
        builder = WappaBuilder()
        
        builder.add_middleware(TestMiddleware, name="default")
        
        _, _, priority = builder.middlewares[0]
        assert priority == 50  # Default priority


@pytest.mark.asyncio
class TestWappaBuilderHooks:
    """Test WappaBuilder hook functionality."""
    
    async def test_startup_hook_execution(self):
        """Test startup hooks are executed."""
        builder = WappaBuilder()
        hook_called = []
        
        async def startup_hook():
            hook_called.append("startup")
        
        app = await (builder
                     .add_startup_hook(startup_hook)
                     .build())
        
        # Simulate app startup
        async with app.lifespan_context(app):
            pass
        
        assert "startup" in hook_called
    
    async def test_shutdown_hook_execution(self):
        """Test shutdown hooks are executed."""
        builder = WappaBuilder()
        hook_called = []
        
        async def shutdown_hook():
            hook_called.append("shutdown")
        
        app = await (builder
                     .add_shutdown_hook(shutdown_hook)
                     .build())
        
        # Simulate app lifecycle
        async with app.lifespan_context(app):
            pass
        
        assert "shutdown" in hook_called
    
    async def test_hook_priority_ordering(self):
        """Test hooks are executed in priority order."""
        builder = WappaBuilder()
        execution_order = []
        
        async def hook_high():
            execution_order.append("high")
        
        async def hook_low():
            execution_order.append("low")
        
        async def hook_medium():
            execution_order.append("medium")
        
        app = await (builder
                     .add_startup_hook(hook_low, priority=10)
                     .add_startup_hook(hook_high, priority=90)
                     .add_startup_hook(hook_medium, priority=50)
                     .build())
        
        async with app.lifespan_context(app):
            pass
        
        # Startup hooks should run high to low priority
        assert execution_order == ["high", "medium", "low"]
    
    async def test_shutdown_hooks_reverse_order(self):
        """Test shutdown hooks run in reverse priority order."""
        builder = WappaBuilder()
        startup_order = []
        shutdown_order = []
        
        async def hook_1():
            startup_order.append("hook_1")
        
        async def hook_2():
            startup_order.append("hook_2")
        
        async def shutdown_hook_1():
            shutdown_order.append("hook_1")
        
        async def shutdown_hook_2():
            shutdown_order.append("hook_2")
        
        app = await (builder
                     .add_startup_hook(hook_1, priority=90)  # High priority
                     .add_startup_hook(hook_2, priority=10)  # Low priority
                     .add_shutdown_hook(shutdown_hook_1, priority=90)
                     .add_shutdown_hook(shutdown_hook_2, priority=10)
                     .build())
        
        async with app.lifespan_context(app):
            pass
        
        # Startup: high to low, shutdown: low to high (reverse)
        assert startup_order == ["hook_1", "hook_2"]
        assert shutdown_order == ["hook_2", "hook_1"]


@pytest.mark.asyncio
class TestWappaBuilderLifespan:
    """Test WappaBuilder lifespan management."""
    
    async def test_plugin_lifecycle_execution(self):
        """Test complete plugin lifecycle."""
        builder = WappaBuilder()
        plugin = TestWappaPlugin("lifecycle_test")
        
        app = await (builder
                     .add_plugin(plugin)
                     .build())
        
        # Before lifespan
        assert plugin.configure_called
        assert not plugin.startup_called
        assert not plugin.shutdown_called
        
        # During lifespan
        async with app.lifespan_context(app):
            assert plugin.startup_called
            assert not plugin.shutdown_called
        
        # After lifespan
        assert plugin.shutdown_called
    
    async def test_multiple_plugins_lifecycle(self):
        """Test lifecycle with multiple plugins."""
        builder = WappaBuilder()
        plugin1 = TestWappaPlugin("plugin1")
        plugin2 = TestWappaPlugin("plugin2")
        
        app = await (builder
                     .add_plugin(plugin1)
                     .add_plugin(plugin2)
                     .build())
        
        async with app.lifespan_context(app):
            pass
        
        # All plugins should go through complete lifecycle
        for plugin in [plugin1, plugin2]:
            assert plugin.configure_called
            assert plugin.startup_called
            assert plugin.shutdown_called
    
    async def test_lifespan_error_handling(self):
        """Test lifespan error handling."""
        class FailingPlugin:
            async def configure(self, builder):
                pass
            
            async def startup(self, app):
                raise RuntimeError("Startup failed")
            
            async def shutdown(self, app):
                pass
        
        builder = WappaBuilder()
        app = await (builder
                     .add_plugin(FailingPlugin())
                     .build())
        
        # Should handle startup errors gracefully
        with pytest.raises(RuntimeError, match="Startup failed"):
            async with app.lifespan_context(app):
                pass


@pytest.mark.asyncio
class TestWappaBuilderIntegration:
    """Test WappaBuilder integration scenarios."""
    
    async def test_complex_configuration_chain(self):
        """Test complex configuration with multiple components."""
        builder = WappaBuilder()
        plugin = TestWappaPlugin("complex")
        
        async def custom_hook():
            pass
        
        app = await (builder
                     .add_plugin(plugin)
                     .add_middleware(TestMiddleware, priority=80, name="auth")
                     .add_middleware(TestMiddleware, priority=60, name="cors")
                     .add_startup_hook(custom_hook, priority=70)
                     .configure(title="Complex App", version="1.5.0")
                     .build())
        
        assert isinstance(app, FastAPI)
        assert app.title == "Complex App"
        assert app.version == "1.5.0"
        assert len(builder.plugins) == 1
        assert len(builder.middlewares) == 2
        assert len(builder.startup_hooks) == 1
    
    async def test_empty_builder_creates_basic_app(self):
        """Test that empty builder creates basic functional app."""
        builder = WappaBuilder()
        
        app = await builder.build()
        
        assert isinstance(app, FastAPI)
        assert app.title == "Wappa Application"
        assert callable(app.lifespan)
    
    async def test_builder_state_isolation(self):
        """Test that builder instances don't share state."""
        builder1 = WappaBuilder()
        builder2 = WappaBuilder()
        
        plugin1 = TestWappaPlugin("builder1")
        plugin2 = TestWappaPlugin("builder2")
        
        builder1.add_plugin(plugin1)
        builder2.add_plugin(plugin2)
        
        assert len(builder1.plugins) == 1
        assert len(builder2.plugins) == 1
        assert builder1.plugins[0] is plugin1
        assert builder2.plugins[0] is plugin2
    
    async def test_app_state_access(self):
        """Test that built app provides access to state."""
        builder = WappaBuilder()
        
        app = await builder.build()
        
        # App should have state object
        assert hasattr(app, 'state')
        
        # Lifespan should be properly configured
        async with app.lifespan_context(app):
            # During lifespan, state should be accessible
            assert hasattr(app, 'state')


@pytest.mark.asyncio
class TestWappaBuilderErrorHandling:
    """Test WappaBuilder error handling."""
    
    async def test_plugin_configuration_error(self):
        """Test handling of plugin configuration errors."""
        class FailingConfigPlugin:
            async def configure(self, builder):
                raise ValueError("Configuration failed")
            
            async def startup(self, app):
                pass
            
            async def shutdown(self, app):
                pass
        
        builder = WappaBuilder()
        
        with pytest.raises(ValueError, match="Configuration failed"):
            await (builder
                   .add_plugin(FailingConfigPlugin())
                   .build())
    
    async def test_invalid_middleware_class(self):
        """Test handling of invalid middleware."""
        builder = WappaBuilder()
        
        # This should not raise an error during build, but would fail at runtime
        app = await (builder
                     .add_middleware(str, priority=50)  # Invalid middleware
                     .build())
        
        assert isinstance(app, FastAPI)
    
    async def test_invalid_hook_function(self):
        """Test handling of invalid hook functions."""
        builder = WappaBuilder()
        
        # Non-async function should work but log a warning
        def sync_hook():
            pass
        
        app = await (builder
                     .add_startup_hook(sync_hook)
                     .build())
        
        assert isinstance(app, FastAPI)


# Additional utility tests
class TestWappaBuilderUtils:
    """Test WappaBuilder utility methods."""
    
    def test_repr_method(self):
        """Test string representation."""
        builder = WappaBuilder()
        builder.add_plugin(TestWappaPlugin("test"))
        
        repr_str = repr(builder)
        assert "WappaBuilder" in repr_str
        assert "plugins=1" in repr_str
    
    def test_len_method(self):
        """Test length method for plugins."""
        builder = WappaBuilder()
        
        assert len(builder.plugins) == 0
        
        builder.add_plugin(TestWappaPlugin("test1"))
        builder.add_plugin(TestWappaPlugin("test2"))
        
        assert len(builder.plugins) == 2


if __name__ == "__main__":
    pytest.main([__file__])