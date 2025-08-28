# Echo Project - Wappa Framework Comprehensive Demo

A comprehensive demonstration project showcasing all features of the Wappa framework for WhatsApp Business API integration.

## Overview

The Echo Project replicates and extends the original `echo_test_event` project using Wappa's unified architecture. It demonstrates:

- **Comprehensive Message Echo**: All message types with metadata extraction
- **Interactive Features**: Buttons, lists, CTA buttons, and location requests
- **State Management**: Redis-based interactive session management
- **Media Processing**: WhatsApp media ID echo functionality
- **User Storage**: 24-hour user profile caching
- **Clean Architecture**: Layered processing with functional business logic

## Architecture

### New Simplified Architecture (No Bridge Modules!)

**The Echo Project now uses Wappa's new unified architecture** - eliminating complex bridge modules and threading code!

```
main.py                 # Simple: app = Wappa(cache="redis") + app.run()
echo_handler.py        # Master event handler (WappaEventHandler)
constants.py           # Shared configuration and constants
components/            # Core processing components
├── state_manager.py      # Redis state management
├── interactive_builder.py # Interactive message builder
└── media_processor.py    # Media echo processor
logic/                 # Business logic modules (20 modules)
├── text_echo.py          # Text message processing
├── image_echo.py         # Image message processing
├── video_echo.py         # Video message processing
├── audio_echo.py         # Audio/voice processing
├── document_echo.py      # Document processing
├── location_echo.py      # Location sharing
├── contact_echo.py       # Contact sharing
├── button_*.py           # Button interaction logic (3 modules)
├── list_*.py             # List interaction logic (3 modules)
├── cta_activation.py     # CTA button logic
├── location_activation.py # Location request logic
├── state_management.py   # State utilities
├── metadata_extraction.py # Metadata processing
├── user_storage.py       # User profile management
└── message_confirmation.py # Read receipts & typing
media/                 # Sample media files (7 files)
```

### Key Improvements

✅ **Eliminated Complex Boilerplate**: No more `create_fastapi_app()` with threading!  
✅ **Clean Module-Level Setup**: `app = Wappa(cache="redis")` is all you need  
✅ **Three Development Modes**: Direct Python, uvicorn, or CLI - your choice  
✅ **Standards Compliant**: Uses FastAPI `.asgi` property pattern  
✅ **Auto-Reload Compatible**: Works seamlessly with `uvicorn --reload`

## Features

### Core Echo Functionality
- **Text Messages**: Full echo with comprehensive metadata
- **Media Messages**: Echo using WhatsApp media IDs (image, video, audio, document)
- **Location Messages**: Location data echo with coordinates and map links
- **Contact Messages**: Contact information echo with formatted details
- **Message Confirmation**: Read receipts and typing indicators

### Interactive Features
- **Button Demo** (`/button`): Interactive buttons with image responses
- **List Demo** (`/list`): Interactive lists with media file samples
- **CTA Demo** (`/cta`): Call-to-action buttons with external links
- **Location Request** (`/location`): Location sharing prompts

### State Management
- **Redis Integration**: Persistent state across interactions
- **TTL Management**: 10-minute session timeouts
- **State Cleanup**: Automatic expired state removal
- **Conflict Resolution**: Prevention of overlapping interactive states

### User Storage
- **Profile Caching**: 24-hour user profile retention
- **Metadata Storage**: Comprehensive user interaction history
- **Privacy Compliance**: Automatic data expiration

## Installation

### Prerequisites
- Python 3.12+
- Redis server
- WhatsApp Business API credentials
- uv package manager

### Setup

1. **Clone and navigate to project**:
```bash
cd /path/to/wappa/examples/echo_project
```

2. **Install dependencies** (from main Wappa directory):
```bash
uv sync
```

3. **Configure environment variables**:
```bash
# Copy and edit environment configuration
cp ../../.env.example .env

# Required variables:
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_verify_token
REDIS_URL=redis://localhost:6379/0
```

4. **Add sample media files**:
```bash
# Replace placeholder files in media/ directory with actual media files
# See media/README.md for requirements
```

### Running the Application

1. **Start Redis server**:
```bash
redis-server
```

2. **Choose your preferred development mode**:

**Option A: Direct Python execution** (recommended for development):
```bash
cd examples/echo_project
uv run python main.py
```

**Option B: FastAPI-style with uvicorn** (industry standard):
```bash
cd examples/echo_project
uv run uvicorn main:app.asgi --reload
```

**Option C: Wappa CLI** (batteries-included convenience):
```bash
uv run wappa dev examples/echo_project/main.py
```

3. **For production deployment**:
```bash
cd examples/echo_project
uv run hypercorn main:app.asgi --workers 1 --bind "[::]:8000"
```

## Usage

### Basic Echo Testing
Send any message type to see comprehensive echo functionality:
- Text messages → Full echo with metadata
- Images → Media ID echo with file information
- Videos → Media ID echo with format details
- Audio/Voice → Media ID echo with duration info
- Documents → Media ID echo with filename and size
- Location → Formatted location with map links
- Contacts → Formatted contact information

### Interactive Commands
- **`/button`** - Demonstrates interactive button functionality
- **`/list`** - Shows interactive list with media options
- **`/cta`** - Call-to-action button example
- **`/location`** - Location sharing request

### State Interactions
1. Send `/button` to activate button mode
2. Select a button option to receive image response
3. Send `/list` to activate list mode
4. Select media type to receive sample file
5. States automatically expire after 10 minutes

## Configuration

### Feature Flags
Edit `constants.py` to enable/disable features:
```python
FEATURES = {
    "comprehensive_echo": True,
    "interactive_buttons": True,
    "interactive_lists": True,
    "media_echo": True,
    "user_storage": True,
    # ... more features
}
```

### TTL Settings
```python
USER_DATA_TTL_HOURS = 24          # User profile cache
BUTTON_STATE_TTL_SECONDS = 600    # Button session (10 min)
LIST_STATE_TTL_SECONDS = 600      # List session (10 min)
```

### Media Configuration
```python
MEDIA_ECHO_ENABLED = True
MEDIA_METADATA_ENABLED = True
MAX_MEDIA_SIZE_MB = 16  # WhatsApp limit
```

## Development

### Adding New Logic Modules
1. Create module in `logic/` directory
2. Follow existing patterns for error handling
3. Update `logic/__init__.py` imports
4. Add constants to `constants.py`
5. Update echo handler routing in `echo_handler.py`

### Custom Interactive Features
1. Add activation command to constants
2. Create activation logic module
3. Create selection/response logic module
4. Create prompt logic for invalid selections
5. Add state management in `state_manager.py`
6. Update `interactive_builder.py` if needed

### Testing
```bash
# Run linting
uv run ruff check .
uv run ruff format .

# Test Redis connectivity
redis-cli ping

# Test webhook endpoint
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"entry": [{"changes": [{"value": {"messages": []}}]}]}'
```

## Integration with Wappa Framework

### New Unified Architecture Benefits

**Before (Complex Bridge Modules)**:
```python
# OLD WAY - 50+ lines of complex threading code!
def create_fastapi_app():
    import asyncio, threading
    # Complex event loop detection...
    # Threading gymnastics...
    # Bridge module generation...
    return result

fastapi_app = create_fastapi_app()  # Required for uvicorn
```

**After (Clean & Simple)**:
```python
# NEW WAY - Just 3 lines!
from wappa import Wappa
from echo_handler import EchoProjectHandler

app = Wappa(cache="redis")
handler = EchoProjectHandler()
app.set_event_handler(handler)

# That's it! No complex boilerplate needed.
```

### Dependency Injection
The echo handler receives all required dependencies through Wappa's unified system:
```python
async def process_message(self, webhook: IncomingMessageWebhook):
    # Access injected dependencies via WappaBuilder's unified lifespan
    messenger = self.messenger
    cache_factory = self.cache_factory
    # Components created from dependencies
    state_manager = StateManager(cache_factory.create_state_cache())
    media_processor = MediaProcessor(messenger)
```

### Wappa Cache Integration
Redis integration through Wappa's unified plugin architecture:
```python
# In main.py - Wappa automatically adds RedisPlugin!
app = Wappa(cache="redis")  # That's it - no complex setup needed
```

### Universal Webhook Interface
Seamless webhook processing through WappaBuilder's unified lifespan:
```python
# Automatic webhook parsing, plugin initialization, and routing
webhook: IncomingMessageWebhook = parsed_automatically
result = await handler.process_message(webhook)
```

## Performance Considerations

- **Redis Connection Pooling**: Automatic through Wappa framework
- **Async Operations**: All I/O operations are async
- **Media Efficiency**: Uses WhatsApp media IDs for echo
- **State Cleanup**: Automatic expired state removal
- **Connection Reuse**: HTTP client reuse for WhatsApp API

## Security Features

- **Input Validation**: All user inputs validated
- **State Isolation**: User states are isolated
- **Token Management**: Secure credential handling
- **Rate Limiting**: Configurable message rate limits
- **Data Expiration**: Automatic PII cleanup

## Monitoring

### Logging
Comprehensive logging with configurable levels:
```python
LOG_METADATA_EXTRACTION = True
LOG_MEDIA_ECHO_ATTEMPTS = True
LOG_USER_STORAGE = True
LOG_MESSAGE_CONFIRMATION = True
```

### Metrics
Built-in metrics tracking:
- Message processing times
- State operation success rates
- Media echo success rates
- User interaction patterns

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Check Redis server is running: `redis-cli ping`
   - Verify REDIS_URL in environment variables

2. **WhatsApp API Errors**
   - Verify access token validity
   - Check phone number ID configuration
   - Ensure webhook URL is accessible

3. **Media Files Not Found**
   - Check media/ directory has actual files
   - Verify file paths in constants.py
   - Check file permissions

4. **State Not Persisting**
   - Verify Redis connection
   - Check TTL settings in constants
   - Monitor Redis memory usage

### Debug Mode
Enable detailed debugging:
```python
DEBUG_ENABLED = True
DEBUG_LOG_WEBHOOK_DATA = True
DEBUG_LOG_STATE_CHANGES = True
```

## Contributing

1. Follow existing code patterns and architecture
2. Add comprehensive error handling
3. Include logging for debugging
4. Update constants for new features
5. Add documentation for new functionality
6. Test with actual WhatsApp Business API

## License

This project is part of the Wappa framework and follows the same licensing terms.