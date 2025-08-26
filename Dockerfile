# Railway-optimized Dockerfile for Mimeia AI Platform
# Multi-stage build for smaller production image

FROM python:3.12-slim as builder

# Set environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Production stage
FROM python:3.12-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy dependency files (for reference, dependencies already installed in builder stage)
COPY pyproject.toml uv.lock ./

# Copy application code
COPY app/ ./app/

# Create logs directory and set permissions
RUN mkdir -p logs /tmp/uv-cache && \
    chown -R appuser:appuser /app /tmp/uv-cache

# Switch to non-root user
USER appuser

# Health check using the app's health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Expose port (Railway will override with $PORT)
EXPOSE ${PORT:-8000}

# Start the application with Hypercorn
# Railway requires IPv6 binding with [::]
CMD ["sh", "-c", "echo '=== Starting Mimeia AI Platform ===' && uv run hypercorn app.main:app --workers 1 --bind \"[::]:${PORT:-8000}\" --access-log -"]