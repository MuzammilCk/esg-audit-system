FROM python:3.11-slim

WORKDIR /app

COPY services/privacy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

ARG SPACY_MODEL_WHL_URL="https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl"
# Download spaCy model during build to cache it. Override the URL at build time to use a smaller model.
RUN pip install --no-cache-dir "${SPACY_MODEL_WHL_URL}"

COPY services/privacy /app/services/privacy

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.privacy.main:app", "--host", "0.0.0.0", "--port", "8002"]
