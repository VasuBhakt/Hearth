# ============================================================================
# Hearth: Privacy-First Family Assistant MCP Server
# Production-ready, lightweight Docker container
# ============================================================================
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server/ ./server/
# Copy environment defaults and configuration
COPY .env.example .env.example
COPY .env* ./
COPY pytest.ini ./
COPY tests/ ./tests/

# Expose simulator web port
EXPOSE 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/api/config || exit 1

# Start Hearth Simulator
CMD ["uvicorn", "server.simulator_api:app", "--host", "0.0.0.0", "--port", "8080"]
