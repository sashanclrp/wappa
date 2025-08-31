# ================================================================
# WAPPA FULL EXAMPLE - RAILWAY OPTIMIZED DOCKERFILE
# ================================================================
# Simple, single-stage production build optimized for Railway.app
# ================================================================

FROM python:3.12-slim

# Set build arguments
ARG BUILD_DATE
ARG VCS_REF

# Labels for metadata
LABEL org.opencontainers.image.title="Wappa Full Example"
LABEL org.opencontainers.image.description="Production-ready WhatsApp Business API application using Wappa framework"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.created=$BUILD_DATE
LABEL org.opencontainers.image.revision=$VCS_REF
LABEL org.opencontainers.image.vendor="Mimeia"
LABEL org.opencontainers.image.source="https://github.com/mimeia/wappa"
LABEL maintainer="contact@mimeia.com"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv for fast Python package management
RUN pip install --no-cache-dir uv

# Create non-root user for security
RUN groupadd --gid 1000 wappa \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash wappa

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock ./

# Install Python dependencies
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install --no-cache-dir -r pyproject.toml

# Copy application code
COPY --chown=wappa:wappa . .

# Create required directories with proper permissions
RUN mkdir -p /app/logs /app/media/buttons /app/media/list \
    && chown -R wappa:wappa /app \
    && chmod -R 755 /app

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=PROD
ENV LOG_LEVEL=INFO
ENV PORT=8000

# Health check configuration
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Expose application port
EXPOSE 8000

# Switch to non-root user
USER wappa

# Railway-optimized startup command
CMD ["uv", "run", "uvicorn", "app.main:app.asgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# ================================================================
# RAILWAY DEPLOYMENT NOTES:
# ================================================================
# 1. Railway automatically detects this Dockerfile
# 2. PORT environment variable is automatically set by Railway
# 3. No need for nginx - Railway handles load balancing
# 4. Environment variables set via Railway dashboard
# 5. Redis can be added as a Railway plugin
# ================================================================