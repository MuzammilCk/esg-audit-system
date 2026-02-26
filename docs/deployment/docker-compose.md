# Docker Compose Deployment

This guide covers local development and testing using Docker Compose.

## Prerequisites

- Docker 24.0+
- Docker Compose v2.0+
- 8GB RAM minimum
- OpenAI API key

## Quick Start (Safe Build Order)

```bash
# Clone the repository
git clone https://github.com/your-org/esg-audit-system.git
cd esg-audit-system

# Create environment file
cat > .env << EOF
OPENAI_API_KEY=sk-your-key
PRIVACY_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
EOF

# 1) Build only the base dependencies first
docker compose build document-fetcher privacy-service audit-agents

# 2) Start stateful infra
docker compose up -d redis qdrant

# 3) Start application services
docker compose up -d document-fetcher privacy-service audit-agents vector-store

# 4) Optional services (UI/security/normalizer profile)
docker compose up -d ui-service security-service
docker compose --profile normalizer up -d format-normalizer postgres

# Validate
docker compose ps
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| audit-agents | 8003 | Multiagent orchestration |
| vector-store | 8004 | Qdrant document retrieval |
| security | 8006 | Threat detection |
| ingestion | 8001 | Document fetching |
| privacy | 8002 | PII masking |
| verification | 8005 | C2PA validation |
| qdrant | 6333 | Vector database |
| redis | 6379 | Encrypted cache |

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4-turbo-preview

# Qdrant Configuration
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=esg_documents

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Security
API_KEY=your-secure-api-key
ENCRYPTION_KEY=your-32-byte-encryption-key

# Logging
LOG_LEVEL=INFO
```

### Docker Compose Override

For local development, create `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  audit-agents:
    volumes:
      - ./services/agents:/app/services/agents:ro
    environment:
      - LOG_LEVEL=DEBUG
```

## Common Operations

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f audit-agents
```

### Restart Services

```bash
# All services
docker compose restart

# Specific service
docker compose restart audit-agents
```

### Scale Services

```bash
# Scale audit agents
docker compose up -d --scale audit-agents=3
```

### Clean Up

```bash
# Stop and remove containers
docker compose down

# Remove volumes (clears all data)
docker compose down -v
```

## Health Checks

```bash
# Check all services
curl http://localhost:8003/healthz
curl http://localhost:8004/healthz
curl http://localhost:8006/healthz
```

## Testing

```bash
# Run integration tests
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# Run specific test
docker compose exec audit-agents pytest tests/integration/test_audit_workflow.py -v
```

## Troubleshooting

### Qdrant Not Starting

```bash
# Check Qdrant logs
docker compose logs qdrant

# Common fix: remove stale data
docker compose down -v
docker compose up -d qdrant
```

### Redis Connection Issues

```bash
# Verify Redis is running
docker compose exec redis redis-cli ping

# Check network connectivity
docker compose exec audit-agents ping redis
```

### Memory Issues

```bash
# Increase Docker memory limit
# Docker Desktop -> Settings -> Resources -> Memory

# Or limit container memory
docker compose up -d --memory=2g audit-agents
```

## Production Considerations

For production deployment, use Kubernetes. See [Kubernetes Deployment](kubernetes.md).

## Preventing Disk Blow-Ups and Build Loops

### Why disk usage can spike

- Building many images from the same large context repeatedly.
- Downloading large NLP assets (for example spaCy `en_core_web_lg`) in multiple images.
- Rebuilding with `--no-cache` frequently.
- Not pruning old/untagged build layers.

### Operational guardrails

```bash
# 1) Inspect Docker space before and after builds
docker system df -v

# 2) Build only what you need (do not build every service by default)
docker compose build audit-agents privacy-service

# 3) Stream logs for one service if you suspect restart loops
docker compose logs -f --tail=200 audit-agents

# 4) Inspect restart count / exit reason
docker inspect $(docker compose ps -q audit-agents) --format='{{.State.Status}} {{.State.RestartCount}} {{.State.Error}}'

# 5) Safely reclaim space (keeps running containers untouched)
docker image prune -f
docker builder prune -f --filter until=24h

# 6) Deep clean (only when you accept deleting unused assets)
docker system prune -a --volumes -f
```

### Use smaller spaCy model during local development

By default the compose file uses `en_core_web_lg` for behavior compatibility.
For lightweight local development, override at build time:

```bash
export SPACY_MODEL_WHL_URL=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
docker compose build privacy-service ui-service
```

> Use `en_core_web_lg` in staging/production for parity unless you've validated model-quality impact.
