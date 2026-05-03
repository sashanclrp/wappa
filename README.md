# Wappa 🤖

**Open Source Framework for WhatsApp Business Applications**

Build intelligent WhatsApp bots, workflows, and chat applications with clean architecture and modern Python.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![WhatsApp Business API](https://img.shields.io/badge/WhatsApp-Business%20API-25D366.svg)](https://developers.facebook.com/docs/whatsapp)
[![Version](https://img.shields.io/badge/version-0.7.1-orange.svg)](CHANGELOG.md)

> **v0.3.0 — Architectural Hardening Release** — ~3,500 lines of dead code removed, factory pattern completed for cross-platform messages, two runtime bugs fixed (`MediaType` shadowing, case-sensitive 401 detection), enum duplication eliminated across the codebase. See [CHANGELOG.md](CHANGELOG.md) for the full breakdown.

---

## 🚀 What is Wappa?

Wappa is a modern Python framework that transforms WhatsApp Business API into a powerful platform for building:

- **🤖 Smart Chatbots** - AI-powered conversational experiences
- **📋 Workflows** - Multi-step business processes  
- **🎯 Agents** - Intelligent customer service automation
- **💬 Chat Applications** - Full-featured messaging platforms

**Built for developers who want clean code, not webhook complexity.**

## ✨ Key Features

### 🎯 **Simple & Clean**
```python
from wappa import Wappa, WappaEventHandler

class MyBot(WappaEventHandler):
    async def process_message(self, webhook):
        await self.messenger.send_text("Hello!", webhook.user.user_id)

app = Wappa()
app.set_event_handler(MyBot())
app.run()
```

### 🏗️ **Production-Ready Architecture**
- **Clean Architecture** - Domain-driven design with dependency injection
- **Type-Safe** - Full Pydantic models for all WhatsApp data structures
- **Multi-Tenant** - Built for scaling across multiple business numbers
- **Plugin System** - Extensible with Redis, CORS, rate limiting, and custom plugins

### 📱 **Complete WhatsApp Support**
- **All Message Types** - Text, media, interactive buttons, lists, templates
- **Rich Interactions** - Buttons, lists, call-to-action messages
- **Media Handling** - Images, videos, audio, documents with automatic upload/download
- **Templates** - Pre-approved business message templates

### 🆔 **Recipient Contract and BSUID Support**
- **Stable Internal Contract** - Wappa keeps the framework-facing parameter as `recipient` across `self.messenger.send_*`, API routes, and request models
- **Transport Resolution** - In the WhatsApp adapter, `recipient` is resolved to:
  - `to` when the identifier is a phone number
  - `recipient` when the identifier is a BSUID
- **BSUID-Aware Outbound** - Text, media, interactive, template, and specialized messages use the same internal recipient resolution
- **No Framework Fallback** - If a message type cannot be sent via BSUID, Wappa does not automatically downgrade to phone-number transport

#### Important BSUID Risk
Wappa currently treats BSUID support as a transport concern, not as a delivery fallback workflow.

This means:
- your application can keep calling `send_*` with `recipient=...` exactly as before
- Wappa will choose the correct WhatsApp request field internally
- but if Meta rejects a BSUID for a specific message type, Wappa will return an explicit error instead of retrying with a phone number

This is intentional for now. The fallback policy depends on each Wappa implementation because only the application knows:
- whether a phone number is available
- whether falling back is legally or product-wise acceptable
- whether that specific message should be retried with a different recipient identity

If your bot needs automatic fallback, implement it in your application layer around `self.messenger`, your user identity store, or your delivery orchestration logic.

### 🛠️ **Developer Experience**
```bash
# Initialize new project
wappa init my-bot

# Start development server with auto-reload
wappa dev app/main.py

# Browse interactive examples
wappa examples
```

### 💾 **Flexible State Management**
```python
# Memory, JSON file, or Redis caching
app = Wappa(cache="redis")  # or "memory" or "json"

# Automatic state persistence
await self.state_cache.set("conversation", {"step": "greeting"})
```

### 🏭 **Factory Pattern for Cross-Platform Messages** (v0.3.0)
Text, read-status, and media payloads are produced by dedicated factories (`WhatsAppMessageFactory`, `WhatsAppMediaFactory`) and consumed by `WhatsAppMessenger` through dependency injection. This keeps pure payload construction separate from I/O and gives you clean injection points in FastAPI routes.

```python
# Defaults keep the library ergonomic:
messenger = WhatsAppMessenger(
    client=client,
    media_handler=media_handler,
    interactive_handler=interactive_handler,
    template_handler=template_handler,
    specialized_handler=specialized_handler,
    tenant_id=tenant_id,
)

# Or inject custom factories for advanced use cases (testing, multi-tenant extensions):
messenger = WhatsAppMessenger(
    client=client,
    # ... handlers ...
    tenant_id=tenant_id,
    message_factory=MyCustomMessageFactory(),
    media_factory=MyCustomMediaFactory(),
)
```

**Why only text/media have factories?** Interactive messages, templates, and specialized types (contact, location) are platform-specific — Telegram has inline keyboards instead of WhatsApp buttons/lists, templates are WA-only, and Instagram has quick replies but no lists. Factories are reserved for concepts that truly cross platforms. Platform-specific types are owned by their corresponding handlers.

## 📦 Installation

### Using uv (Recommended)
```bash
# Create new project
uv init my-wappa-project
cd my-wappa-project

# Add Wappa
uv add wappa

# Initialize project structure
wappa init .
```

### Using pip
```bash
pip install wappa

# Initialize new project
wappa init my-wappa-project
cd my-wappa-project
```

### Using Poetry
```bash
poetry new my-wappa-project
cd my-wappa-project
poetry add wappa

# Initialize project structure  
wappa init .
```

## 🏃‍♂️ Quick Start

### 1. Get WhatsApp Business API Credentials

1. Visit [Meta for Developers](https://developers.facebook.com)
2. Create a WhatsApp Business App
3. Get your credentials:
   - **Access Token**
   - **Phone Number ID** 
   - **Business Account ID**

### 2. Create Your Bot

```bash
# Initialize project
wappa init my-bot
cd my-bot

# Configure environment
cp .env.example .env
# Edit .env with your WhatsApp credentials
```

### 3. Run Development Server

```bash
# Start with auto-reload
wappa dev app/main.py

# Or manually
uv run python -m app.main
```

### 4. Test Your Bot

Send a message to your WhatsApp Business number and watch it echo back!

## 🎛️ Architecture Overview

```mermaid
graph TD
    A[👤 WhatsApp User] -->|Message| B[📡 Webhook Endpoint]
    B --> C[🔄 Event Dispatcher]
    C --> D[⚡ Your Event Handler]
    D --> E[💬 Messenger Interface]
    E --> F[📱 WhatsApp API]

    D --> G[💾 State Management]
    D --> H[🧠 Business Logic]
    G --> I[🗄️ Redis/Memory/JSON Cache]
    H --> J[🔗 External Services]

    style D fill:#333481,color:#fff,stroke:#333481,stroke-width:3px
    style E fill:#4A90E2,color:#fff,stroke:#4A90E2,stroke-width:3px
    style G fill:#333481,color:#fff,stroke:#333481,stroke-width:3px
    style A fill:#25D366,color:#fff,stroke:#25D366,stroke-width:3px
    style F fill:#25D366,color:#fff,stroke:#25D366,stroke-width:3px
```

- **Event-Driven**: Webhook → Event Handler → Response
- **Type-Safe**: Full Pydantic models for all WhatsApp data structures  
- **FastAPI Core**: Built on modern async Python with automatic OpenAPI docs
- **Production Ready**: Docker support, Redis caching, structured logging

## 📚 Documentation

**📖 [Complete Documentation](https://wappa.mimeia.com/docs)**

### Quick Links

- **🚀 [Quick Start](https://wappa.mimeia.com/docs/getting-started)** - Get running in 5 minutes
- **🏗️ [Architecture Guide](https://wappa.mimeia.com/docs/concepts/architecture)** - Understanding the framework
- **📡 [API Reference](https://wappa.mimeia.com/docs/api/messaging)** - Complete messaging API
- **💾 [State Management](https://wappa.mimeia.com/docs/concepts/state-management)** - Caching and persistence
- **🚀 [Deploy to Railway](https://wappa.mimeia.com/docs/deployment/railway)** - Production deployment
- **🛠️ [WhatsApp Setup](https://wappa.mimeia.com/docs/setup/whatsapp-setup)** - Configure WhatsApp Business API

### Example Projects

Explore 6 complete example applications:

```bash
# Browse examples interactively
wappa examples

# Copy specific example
wappa examples redis-cache-demo
```

- **Simple Echo** - Basic message echoing
- **JSON Cache Demo** - File-based state persistence
- **Redis Cache Demo** - High-performance caching
- **OpenAI Transcription** - Voice message processing
- **Full-Featured Bot** - Complete production example
- **Basic Project** - Minimal setup template

## 🛠️ Advanced Usage

### Builder Pattern for Complex Apps

```python
from wappa import WappaBuilder

app = await (WappaBuilder()
             .with_whatsapp(
                 token="your_token",
                 phone_id="your_phone_id", 
                 business_id="your_business_id"
             )
             .with_redis_cache("redis://localhost:6379")
             .with_cors_enabled()
             .with_rate_limiting(requests_per_minute=100)
             .build())

app.set_event_handler(MyAdvancedHandler())
app.run()
```

### Plugin System

```python
from wappa.plugins import DatabasePlugin, CorsPlugin

app = Wappa(cache="redis")
app.add_plugin(DatabasePlugin("postgresql://..."))
app.add_plugin(CorsPlugin(allow_origins=["*"]))
app.set_event_handler(MyHandler())
app.run()
```

### CLI Commands

```bash
# Project management
wappa init [directory]          # Initialize new project
wappa examples [target]         # Browse/copy examples

# Development
wappa dev app/main.py           # Development server with auto-reload
wappa prod app/main.py          # Production server

# Help
wappa --help                    # Show all commands
```

## 🚀 Deployment

### Railway (Recommended)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway add redis
railway up

# Set environment variables
railway variables set WP_ACCESS_TOKEN=your_token
railway variables set WP_PHONE_ID=your_phone_id
railway variables set WP_BID=your_business_id
```

See [complete Railway deployment guide](https://wappa.mimeia.com/docs/deployment/railway).

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install uv
RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "python", "-m", "app.main"]
```

## 🧪 Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/sashanclrp/wappa.git
cd wappa

# Install dependencies
uv sync --group dev

# Run tests
uv run pytest

# Code formatting
uv run ruff check .
uv run ruff format .
```

### Project Structure

```
wappa/
├── wappa/                  # Core framework
│   ├── core/              # Application core & plugins
│   ├── messaging/         # WhatsApp messaging implementation
│   ├── persistence/       # Cache backends (Memory/JSON/Redis)
│   ├── cli/               # CLI tools & project templates
│   └── api/               # FastAPI routes & dependencies
├── examples/              # Example applications
├── docs/                  # Documentation source
└── tests/                # Test suite
```

## 🤝 Community & Support

### 💬 **Join the Community**
- **💭 [Discord Community](https://discord.gg/wappa)** - Get help, share projects, and connect with other developers
- **🐛 [GitHub Issues](https://github.com/sashanclrp/wappa/issues)** - Bug reports and feature requests
- **📖 [GitHub Discussions](https://github.com/sashanclrp/wappa/discussions)** - Questions and community discussions

### 📞 **Get Support**
- **📚 [Documentation](https://wappa.mimeia.com/docs)** - Comprehensive guides and API reference
- **💡 [Examples](https://wappa.mimeia.com/docs/resources/examples)** - 6 complete working examples
- **🔧 [Configuration Guide](https://wappa.mimeia.com/docs/setup/whatsapp-setup)** - WhatsApp Business API setup

### 🤝 **Contributing**
We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

- **🐛 Found a bug?** Open an [issue](https://github.com/sashanclrp/wappa/issues)
- **💡 Have an idea?** Start a [discussion](https://github.com/sashanclrp/wappa/discussions)
- **🔧 Want to contribute?** Check out [good first issues](https://github.com/sashanclrp/wappa/labels/good%20first%20issue)

## 📋 Requirements

- **Python 3.12+** - Modern Python with latest type hints
- **WhatsApp Business API** - Meta for Developers account
- **Redis** (optional) - For production caching and state management

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Meta** - For the WhatsApp Business API
- **FastAPI** - For the excellent async Python framework
- **Redis** - For high-performance caching
- **Open Source Community** - For inspiration and contributions

---

**Built with ❤️ by [Mimeia](https://mimeia.com) • Open Source • Apache 2.0 License**

*Transform your business communication with WhatsApp automation.*
