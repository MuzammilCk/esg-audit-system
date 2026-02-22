# Dockerfile for AWS Nitro Enclave
# This image runs inside the Nitro Enclave isolated memory

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY enclave/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /app/deps /app/deps
ENV PYTHONPATH=/app/deps

# Copy application code
COPY enclave /app/enclave
COPY services /app/services

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ENCLAVE_PORT=5005

# Expose vsock port (informational only)
EXPOSE 5005

# Run the enclave application
CMD ["python", "-m", "enclave.main"]
