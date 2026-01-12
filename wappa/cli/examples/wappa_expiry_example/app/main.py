"""
Wappa Expiry Example - Main Application Entry Point

Demonstrates ExpiryActions system with inactivity detection:
- Messages accumulate in UserCache during conversation
- 15-second inactivity timer resets on each message
- After 15s of silence, all messages are echoed back with timestamps
- Clean up happens automatically via expiry handler

This example shows the wpDemoHotels pattern of using expiry triggers
for inactivity detection and batch processing.
"""

from wappa import ExpiryPlugin, Wappa

# Import expiry handlers to register decorators
from . import expiry_handlers  # noqa: F401
from .master_event import MasterEventHandler

# Create Wappa application with Redis cache
app = Wappa(cache="redis")

# Add ExpiryPlugin to enable expiry action system
app.add_plugin(ExpiryPlugin())

# Set event handler
app.set_event_handler(MasterEventHandler())

# Note: Expiry handlers are auto-registered via @expiry_registry decorator
# See app/expiry_handlers.py for the handler implementation
