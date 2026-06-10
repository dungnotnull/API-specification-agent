FROM python:3.12-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 agentuser

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=agentuser:agentuser . .

# Create data and models directories
RUN mkdir -p /app/data /app/models && chown -R agentuser:agentuser /app/data /app/models

# Verify installation
RUN python -c "from agent.orchestrator import SpecKitOrchestrator; print('Import OK')"

USER agentuser

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8020/health || exit 1

# Default command
CMD ["python", "-m", "agent.main", "serve", "--host", "0.0.0.0", "--port", "8020"]
