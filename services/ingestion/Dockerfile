FROM python:3.11-slim

WORKDIR /app

# python-magic requires libmagic.
RUN apt-get update \
  && apt-get install -y --no-install-recommends libmagic1 libmagic-mgc \
  && rm -rf /var/lib/apt/lists/*

COPY services/ingestion/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services /app/services

EXPOSE 8000

CMD ["uvicorn", "services.ingestion.fetcher:app", "--host", "0.0.0.0", "--port", "8000"]
