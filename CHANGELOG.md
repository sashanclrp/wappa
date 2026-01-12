# Changelog

All notable changes to Wappa will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-11

### Added
- **PostgresDatabasePlugin**: Production-ready async PostgreSQL plugin with 30x-community inspired patterns
  - Asyncpg-powered async engine for high-concurrency conversational apps
  - Connection pooling with configurable pool_size, max_overflow, and timeouts
  - Exponential backoff retry logic for transient database failures
  - Auto-table creation at startup with SQLModel support
  - Statement cache size configuration for Supabase pgBouncer compatibility
  - Comprehensive error handling and health checks

- **RedisPubSubPlugin**: Multi-tenant Redis PubSub messaging system
  - Self-subscribing pattern for bot-to-bot communication
  - Multi-tenant channel management with automatic subscription
  - Channel-based event broadcasting and listening
  - Graceful startup/shutdown with subscription cleanup
  - Example implementation with tenant isolation

- **AIState Pool and Cache System**: Multi-backend state management
  - Pool 4 implementation with Redis, JSON, and Memory backends
  - Conversation state tracking with TTL support
  - Cache factory pattern for easy backend switching

- **CLI Examples Showcase**: Two new production-ready examples
  - `db_redis_echo_example`: PostgreSQL + Redis two-tier storage with SOLID architecture
  - `redis_pubsub_example`: Multi-tenant PubSub with self-subscribing pattern
  - Both now visible in `wappa examples` command

### Changed
- **SOLID Architecture Refactoring**: db_redis_echo_example refactored from monolithic to clean architecture
  - Reduced master_event.py from 700 lines to 258 lines
  - Separated concerns into handlers/, models/, utils/ structure
  - Created comprehensive scaffolding guide documentation
  - Improved testability and maintainability

- **Configuration Management**: db_redis_echo_example now uses Settings class pattern
  - Replaced os.getenv with DBRedisSettings extending base Settings
  - Type-safe configuration with validation at startup
  - Consistent with Wappa's configuration patterns

### Fixed
- **WhatsApp Media Message Schemas**: Added missing `url` field to all media types
  - Fixed video, document, image, audio, and sticker message validation
  - Support for WhatsApp's new direct download URLs in webhook payload
  - Implemented missing abstract methods in WhatsAppVideoMessage

- **Message Persistence**: Enhanced structured data storage for special message types
  - Contact messages: Store full contact data in json_content JSONB field
  - Location messages: Store coordinates and location metadata
  - Interactive messages: Store button/list selections
  - Reaction messages: Store emoji and target message reference

### Documentation
- Created wappa-project-scaffolding-guide.md with SOLID best practices
- Created message-persistence-guide.md for database storage patterns
- Updated db_redis_echo_example README with architecture documentation
- Added comprehensive docstrings to PostgresDatabasePlugin

### Dependencies
- Added asyncpg>=0.31.0 for async PostgreSQL support

## [0.1.10] - Previous Release

Initial stable release with core WhatsApp webhook handling, messaging, and caching capabilities.

---

[0.2.0]: https://github.com/sashanclrp/wappa/compare/v0.1.10...v0.2.0
[0.1.10]: https://github.com/sashanclrp/wappa/releases/tag/v0.1.10
