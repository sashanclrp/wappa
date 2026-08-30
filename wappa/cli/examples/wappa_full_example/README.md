# Wappa Full Example

A comprehensive demonstration of the **Wappa Framework** showcasing all WhatsApp Business API features including message handling, interactive commands, state management, and media processing.

## 🌟 Overview

This example demonstrates a production-ready WhatsApp Business application that showcases:

- ✅ **Complete message type handling** with metadata extraction
- 🔘 **Interactive commands** with button and list demonstrations
- 🗃️ **State management** with TTL and Redis caching
- 📎 **Media relay functionality** using media_id
- 👥 **User tracking and analytics** with comprehensive profiles
- 🎉 **Welcome messages** for first-time users
- 🏗️ **Professional architecture** with clean code patterns
- 📊 **Performance monitoring** and statistics tracking

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Redis server running locally or remotely
- WhatsApp Business API access token and phone number ID

### Installation

1. **Clone or navigate to the project:**
   ```bash
   cd wappa_examples/wappa_full_example
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

4. **Configure your WhatsApp Business API credentials in `.env`:**
   ```env
   META_APP_SECRET=your_meta_app_secret_here
   WP_WEBHOOK_VERIFY_TOKEN=your_verify_token_here
   WP_ACCESS_TOKEN=your_access_token_here
   WP_PHONE_ID=your_phone_number_id_here
   WP_BID=your_business_id_here
   REDIS_URL=redis://localhost:6379
   ```

5. **Add media files (optional):**
   - Add `kitty.png` and `puppy.png` to `app/media/buttons/`
   - Add sample files to `app/media/list/` (image.png, video.mp4, audio.mp3, document.pdf)

6. **Run the application:**
   ```bash
   uv run python -m app.main
   ```

## 🎮 Interactive Features

### Special Commands

Send these commands to your WhatsApp number to try the interactive features:

#### `/button` - Interactive Button Demo
- Creates buttons for "🐱 Kitty" and "🐶 Puppy"
- 10-minute TTL with state management
- Sends corresponding animal image on selection
- Demonstrates comprehensive metadata extraction

#### `/list` - Interactive List Demo
- List with Image, Video, Audio, Document options
- Sends actual media files based on selection
- Demonstrates list interaction patterns

#### `/cta` - Call-to-Action Button
- External link to Wappa documentation
- Shows CTA button implementation

#### `/location` - Location Sharing Demo
- Shares predefined location (Bogotá, Colombia)
- Demonstrates location message handling

### Message Type Handling

The application automatically handles and echoes all WhatsApp message types:

| Message Type | Response | Features |
|--------------|----------|----------|
| **Text** | Echo with "Echo - {content}" + metadata | URL detection, mention parsing |
| **Images/Videos/Audio/Documents** | Relay same media using media_id + metadata | File size, dimensions, duration |
| **Location** | Echo same coordinates + metadata | Name, address, coordinates |
| **Contacts** | Echo contact information + metadata | Names, phones, emails |
| **Interactive** | Process button/list selections + metadata | Selection IDs, titles |

## 🏗️ Architecture

### Project Structure

```
wappa_full_example/
├── app/
│   ├── handlers/           # Message, command, and state handlers
│   │   ├── message_handlers.py    # Handle different message types
│   │   ├── command_handlers.py    # Handle special commands
│   │   └── state_handlers.py      # Handle interactive states
│   ├── models/             # Pydantic data models
│   │   ├── webhook_metadata.py    # Metadata models per message type
│   │   ├── user_models.py         # User profile and session models
│   │   └── state_models.py        # Interactive state models
│   ├── utils/              # Utility modules
│   │   ├── metadata_extractor.py  # Extract webhook metadata
│   │   ├── media_handler.py       # Media download/upload
│   │   └── cache_utils.py         # Redis cache operations
│   ├── media/              # Media files for demos
│   │   ├── buttons/        # Button response images
│   │   └── list/          # List response media files
│   ├── master_event.py     # Main WappaEventHandler
│   └── main.py            # FastAPI application
├── logs/                  # Application logs
├── pyproject.toml        # Project configuration
└── README.md            # This file
```

### Key Components

#### 1. **Master Event Handler** (`master_event.py`)
- Main `WappaEventHandler` implementation
- Orchestrates all message processing
- Handles user profiles and welcome messages
- Manages statistics and logging

#### 2. **Message Handlers** (`handlers/message_handlers.py`)
- Type-specific message processing
- Metadata extraction and formatting
- Media relay functionality
- User activity tracking

#### 3. **Command Handlers** (`handlers/command_handlers.py`)
- Special command processing (`/button`, `/list`, `/cta`, `/location`)
- Interactive message creation
- State initialization with TTL

#### 4. **State Handlers** (`handlers/state_handlers.py`)
- Interactive state management
- Button and list response processing
- State validation and cleanup
- Media file serving

#### 5. **Utilities**
- **Metadata Extractor**: Comprehensive webhook metadata extraction
- **Media Handler**: Media download/upload and relay functionality
- **Cache Utils**: Redis operations and user management

## 📊 Features Demonstrated

### User Management
- **First-time user detection** with welcome messages
- **User profile caching** with activity tracking  
- **Message count statistics** and interaction analytics
- **Command usage tracking** and behavioral insights

### State Management
- **TTL-based states** (10-minute expiration for interactive commands)
- **State validation** and error handling
- **Automatic cleanup** of expired states
- **Multi-state support** (buttons, lists, custom states)

### Message Processing
- **Comprehensive metadata extraction** for all message types
- **Media relay using media_id** for efficient bandwidth usage
- **Professional error handling** with user-friendly messages
- **Performance monitoring** with processing time tracking

### Interactive Features
- **Button workflows** with media responses
- **List interactions** with file serving
- **CTA buttons** linking to external resources
- **Location sharing** with predefined coordinates

## 🛠️ Development

### Running in Development

```bash
# Start with auto-reload
uvicorn app.main:app --reload

# Or use uv run
uv run python -m app.main

# With specific host/port
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy app/
```

### Testing

```bash
# Run tests (when test suite is added)
uv run pytest

# With coverage
uv run pytest --cov=app tests/
```

## 📈 Monitoring and Analytics

The application provides comprehensive statistics:

### Handler Statistics
- Total messages processed
- Success/failure rates
- Processing time metrics
- Feature usage analytics

### User Analytics
- New user registrations
- Message type distribution
- Command usage patterns
- Interactive feature engagement

### Cache Statistics
- Redis operation metrics
- User profile hit rates
- State management efficiency
- Memory usage patterns

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `META_APP_SECRET` | Meta app secret; authenticates every webhook POST body | Yes | - |
| `WP_WEBHOOK_VERIFY_TOKEN` | Token Meta echoes during the GET verification challenge | Yes | - |
| `WP_ACCESS_TOKEN` | WhatsApp Business API access token (legacy mode) | Yes | - |
| `WP_PHONE_ID` | WhatsApp phone number ID — the Inbox ID (legacy mode) | Yes | - |
| `WP_BID` | WhatsApp Business ID (legacy mode) | Yes | - |
| `REDIS_URL` | Redis connection URL | Yes | `redis://localhost:6379` |
| `SYSTEM_LOG_LEVEL` | Application log level | No | `INFO` |
| `SYSTEM_ENVIRONMENT` | Environment (`DEV` / `PROD`) | No | `DEV` |

### Redis Configuration

The application uses Redis for:
- **User profiles** (24-hour TTL)
- **Interactive states** (10-minute TTL)
- **Message history** (7-day TTL)
- **Application statistics** (persistent)

## 🎯 Use Cases

This example demonstrates patterns useful for:

### Business Applications
- **Customer support** with interactive menus
- **Order management** with button workflows
- **Appointment booking** with list selections
- **Product catalogs** with media sharing

### Educational Applications
- **Interactive tutorials** with step-by-step guidance
- **Quiz systems** with button-based answers
- **File sharing** for educational resources
- **Location sharing** for campus navigation

### E-commerce Applications
- **Product browsing** with media catalogs
- **Order confirmation** with interactive buttons
- **Payment flows** with CTA buttons
- **Delivery tracking** with location updates

## 📚 Learning Resources

### Wappa Framework
- [Documentation](https://wappa.mimeia.com/docs)
- [GitHub Repository](https://github.com/mimeia/wappa)
- [API Reference](https://wappa.mimeia.com/docs/api)

### WhatsApp Business API
- [Official Documentation](https://developers.facebook.com/docs/whatsapp)
- [Message Types](https://developers.facebook.com/docs/whatsapp/cloud-api/messages)
- [Interactive Messages](https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-messages)

## 🤝 Contributing

This example is part of the Wappa framework project. To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

Wappa, and this example, are licensed under the Apache License 2.0 — see [LICENSE](https://github.com/sashanclrp/wappa/blob/main/LICENSE) for details.

## 🙋‍♀️ Support

- **Documentation**: [wappa.mimeia.com](https://wappa.mimeia.com)
- **Issues**: [GitHub Issues](https://github.com/mimeia/wappa/issues)
- **Community**: [Discord](https://discord.gg/wappa)
- **Email**: support@mimeia.com

---

**Built with ❤️ using the Wappa Framework**

**This comprehensive example showcases production-ready patterns for building sophisticated WhatsApp Business applications. Use it as a foundation for your own projects and explore the full potential of conversational interfaces.**