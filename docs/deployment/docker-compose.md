# Docker Compose Deployment

This guide covers local development and testing using Docker Compose.

## Prerequisites

- Docker 24.0+
- Docker Compose v2.0+
- 8GB RAM minimum
- OpenAI API key

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/esg-audit-system.git
cd esg-audit-system

# Create environment file
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start all services
docker-compose up -d

# Check service health
docker-compose ps
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
docker-compose logs -f

# Specific service
docker-compose logs -f audit-agents
```

### Restart Services

```bash
# All services
docker-compose restart

# Specific service
docker-compose restart audit-agents
```

### Scale Services

```bash
# Scale audit agents
docker-compose up -d --scale audit-agents=3
```

### Clean Up

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (clears all data)
docker-compose down -v
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
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

# Run specific test
docker-compose exec audit-agents pytest tests/integration/test_audit_workflow.py -v
```

## Troubleshooting

### Qdrant Not Starting

```bash
# Check Qdrant logs
docker-compose logs qdrant

# Common fix: remove stale data
docker-compose down -v
docker-compose up -d qdrant
```

### Redis Connection Issues

```bash
# Verify Redis is running
docker-compose exec redis redis-cli ping

# Check network connectivity
docker-compose exec audit-agents ping redis
```

### Memory Issues

```bash
# Increase Docker memory limit
# Docker Desktop -> Settings -> Resources -> Memory

# Or limit container memory
docker-compose up -d --memory=2g audit-agents
```

## Production Considerations

For production deployment, use Kubernetes. See [Kubernetes Deployment](kubernetes.md).
