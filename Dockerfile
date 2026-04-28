FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Build context MUST be repository root (`docker build -f Dockerfile .`).
COPY apps/voice-sms/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/voice-sms/*.py ./
COPY packages /app/packages
RUN python -c "import packages.core"

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop", "--proxy-headers", "--forwarded-allow-ips", "*"]
