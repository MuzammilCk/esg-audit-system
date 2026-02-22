FROM python:3.11-slim

WORKDIR /app

COPY services/security/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services /app/services

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8006

EXPOSE 8006

CMD ["uvicorn", "services.security.api:app", "--host", "0.0.0.0", "--port", "8006"]
