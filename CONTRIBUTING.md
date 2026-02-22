# Contributing to ESG Audit System

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git
- OpenAI API key

### Local Development

```bash
# Clone the repository
git clone https://github.com/your-org/esg-audit-system.git
cd esg-audit-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=services --cov-report=html

# Run specific test file
pytest services/agents/tests/test_graph.py

# Run integration tests
pytest -m integration
```

### Running Services Locally

```bash
# Start infrastructure
docker-compose up redis qdrant

# Run individual services
uvicorn services.agents.api:app --reload --port 8003
uvicorn services.vectorstore.api:app --reload --port 8004
uvicorn services.security.api:app --reload --port 8006
```

---

## Project Structure

```
esg-audit-system/
├── services/
│   ├── agents/          # Multiagent system (LangGraph)
│   ├── vectorstore/     # Qdrant + embeddings
│   ├── llm/             # OpenAI integration
│   ├── privacy/         # PII masking
│   ├── verification/    # C2PA provenance
│   ├── security/        # Honeypot + Red Teaming
│   └── ingestion/       # Document fetcher
├── enclave/             # AWS Nitro Enclave
├── k8s/                 # Kubernetes manifests
└── docs/                # Additional documentation
```

---

## Coding Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use [Black](https://black.readthedocs.io/) for formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Use [mypy](https://mypy.readthedocs.io/) for type checking

```bash
# Format code
black services/
isort services/

# Type check
mypy services/
```

### Code Quality

```bash
# Run linters
ruff check services/

# Run all quality checks
make lint
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new compliance framework support
fix: resolve PII masking edge case
docs: update API documentation
test: add unit tests for honeypot manager
refactor: simplify compliance router logic
chore: update dependencies
```

---

## Pull Request Process

### Before Submitting

1. **Create an issue** first for significant changes
2. **Fork the repository** and create a feature branch
3. **Write tests** for new functionality
4. **Update documentation** if needed
5. **Run all tests** and ensure they pass
6. **Run linters** and fix any issues

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] Commit messages follow conventional commits
- [ ] No secrets or sensitive data in code

### PR Review Process

1. Submit PR with clear description
2. Wait for CI checks to pass
3. Address review feedback
4. Squash commits before merge (if requested)
5. Maintainer will merge when approved

---

## Testing Guidelines

### Unit Tests

```python
import pytest
from unittest.mock import Mock, AsyncMock

from services.agents.state import AuditState, AgentDecision

class TestComplianceAnalysis:
    @pytest.mark.asyncio
    async def test_compliance_score_calculation(self):
        # Arrange
        state = AuditState(normalized_text="Sample text")
        
        # Act
        result = await compliance_analysis_node(state)
        
        # Assert
        assert result["compliance_result"].compliance_score >= 0.0
        assert result["compliance_result"].compliance_score <= 1.0
```

### Integration Tests

```python
@pytest.mark.integration
async def test_full_audit_workflow():
    graph = create_audit_graph()
    
    result = await graph.run_audit(
        raw_content="Test document content",
        metadata=DocumentMetadata(supplier_id="TEST-001")
    )
    
    assert result.status in [ProcessingStatus.COMPLIANT, ProcessingStatus.NON_COMPLIANT]
```

---

## Documentation

### Code Documentation

```python
async def analyze_compliance(
    text: str,
    regulations: List[str],
    metadata: Dict[str, Any],
) -> List[ComplianceFinding]:
    """
    Analyze document text against regulatory frameworks.
    
    Args:
        text: Document text to analyze
        regulations: List of regulation codes (e.g., ["ESRS E1", "SEC-GHG"])
        metadata: Document metadata including supplier_id and region
    
    Returns:
        List of ComplianceFinding objects with scores and evidence
    
    Raises:
        ValueError: If text is empty or regulations list is invalid
    
    Example:
        >>> findings = await analyze_compliance(
        ...     text="Our GHG emissions...",
        ...     regulations=["ESRS E1"],
        ...     metadata={"region": "EU"}
        ... )
    """
```

### API Documentation

Update OpenAPI schemas in FastAPI endpoints:

```python
@app.post(
    "/api/audit",
    response_model=AuditResponse,
    summary="Submit document for ESG compliance audit",
    description="Analyzes document against CSRD/SEC frameworks",
    responses={
        200: {"description": "Audit completed successfully"},
        400: {"description": "Invalid request"},
        500: {"description": "Internal server error"},
    }
)
async def submit_audit(request: AuditRequest):
    ...
```

---

## Security Considerations

### Reporting Security Issues

**DO NOT** open public issues for security vulnerabilities.

Email: security@example.com

See [SECURITY.md](SECURITY.md) for details.

### Secure Coding Practices

1. **Never commit secrets** - Use environment variables
2. **Validate all inputs** - Assume malicious data
3. **Sanitize outputs** - Prevent injection attacks
4. **Use parameterized queries** - Prevent SQL injection
5. **Log security events** - But never log PII or secrets

---

## Architecture Decisions

When proposing architectural changes:

1. **Document the decision** in an ADR (Architecture Decision Record)
2. **Explain trade-offs** considered
3. **Show benchmarks** for performance claims
4. **Update diagrams** if relevant

---

## Release Process

1. Update version in `__init__.py`
2. Update `CHANGELOG.md`
3. Create release PR
4. Tag release: `git tag v1.x.x`
5. Build and push Docker images
6. Deploy to staging for testing
7. Deploy to production

---

## Getting Help

- Open an issue for bugs or feature requests
- Join discussions in existing issues
- Email: maintainers@example.com

---

Thank you for contributing!
