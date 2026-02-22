FROM python:3.11

WORKDIR /app

# Removed explicit apt-get install build-essential as python:3.11 includes common build tools
# If specific libs are needed, add them here.


COPY services/ui/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Download spaCy model (shared with privacy service logic)
# Ideally we should use a shared base or volume for models, but for simplicity:
RUN pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl

COPY services /app/services

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.ui.main:app", "--host", "0.0.0.0", "--port", "8080"]
