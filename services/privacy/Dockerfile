FROM python:3.11

WORKDIR /app

# Switch to full image to avoid apt-get errors with build-essential.
# If other deps are needed, add them here.


COPY services/privacy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Download spaCy model during build to cache it
RUN pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl

COPY services/privacy /app/services/privacy

# Set python path to include root for imports if needed, though structure might vary
# Assuming we run from root context in docker-compose, but here we copy to /app/services/privacy
# If we want to run as a module `uvicorn services.privacy.main:app`, we need proper structure.

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.privacy.main:app", "--host", "0.0.0.0", "--port", "8002"]
