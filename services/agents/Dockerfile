FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/agents/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services /app/services

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8003

EXPOSE 8003

CMD ["uvicorn", "services.agents.api:app", "--host", "0.0.0.0", "--port", "8003"]
