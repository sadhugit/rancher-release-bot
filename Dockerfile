# ==============================================================================
# FILE: Dockerfile
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py .
COPY config.yaml .

# Create directory for database
RUN mkdir -p /app/data

# Expose ports (FastAPI on 8000, Slack bot on 3000)
EXPOSE 8000 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run application
CMD ["python", "main.py"]
