FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Build context MUST be repository root (`docker build -f Dockerfile .`).
COPY apps/voice-sms/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/voice-sms/*.py ./
COPY packages /app/packages
RUN python -c "import packages.core"

# Railway (and many PaaS) set $PORT at runtime; bind to it or local Docker falls back to 8080.
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --loop uvloop --proxy-headers --forwarded-allow-ips \"*\""]
