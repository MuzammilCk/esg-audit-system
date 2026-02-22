FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/vectorstore/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services /app/services

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8004

EXPOSE 8004

CMD ["uvicorn", "services.vectorstore.api:app", "--host", "0.0.0.0", "--port", "8004"]
