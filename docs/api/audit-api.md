# Audit API Reference

The Audit Agents API provides endpoints for submitting ESG compliance audits, checking status, and retrieving reports.

**Base URL**: `http://localhost:8003`

## Authentication

All API requests require authentication via API key:

```http
X-API-Key: your-api-key
```

## Endpoints

### Health Check

```http
GET /healthz
```

Returns service health status.

**Response**:
```json
{
  "status": "ok",
  "service": "audit-agents"
}
```

---

### Submit Audit

```http
POST /api/audit
```

Submit a document for ESG compliance analysis.

**Request Body**:
```json
{
  "content": "string (required) - Document text content",
  "source_url": "string - Original document URL",
  "original_filename": "string - Original filename",
  "mime_type": "string - MIME type (default: text/plain)",
  "supplier_id": "string - Supplier identifier",
  "region": "string - Geographic region (EU, US, etc.)",
  "reporting_period": "string - Reporting period (e.g., 2024)"
}
```

**Response**:
```json
{
  "thread_id": "uuid",
  "status": "COMPLIANT",
  "compliance_score": 0.85,
  "compliance_decision": "APPROVE",
  "trust_score": 1.0,
  "findings_count": 5,
  "requires_review": false,
  "report_id": "uuid"
}
```

**Status Codes**:
| Code | Description |
|------|-------------|
| 200 | Audit completed successfully |
| 400 | Invalid request body |
| 500 | Internal server error |

**Example**:
```bash
curl -X POST http://localhost:8003/api/audit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "content": "Sustainability Report 2024\n\nGHG Emissions: Scope 1: 15,000 tCO2e...",
    "source_url": "https://example.com/report.pdf",
    "original_filename": "esg_report_2024.pdf",
    "supplier_id": "SUPP-001",
    "region": "EU",
    "reporting_period": "2024"
  }'
```

---

### Get Audit Status

```http
GET /api/audit/{thread_id}
```

Get detailed status and results of an audit.

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| thread_id | string | Audit thread identifier |

**Response**:
```json
{
  "thread_id": "uuid",
  "status": "COMPLIANT",
  "document_id": "uuid",
  "compliance_score": 0.85,
  "compliance_decision": "APPROVE",
  "provenance_trust_score": 1.0,
  "findings_summary": [
    {
      "regulation_code": "ESRS E1",
      "status": "APPROVE",
      "confidence": 0.9
    }
  ],
  "recommendations": [
    "Continue monitoring Scope 3 emissions"
  ],
  "requires_review": false,
  "audit_trail": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "node": "compliance_analysis",
      "action": "COMPLETE"
    }
  ]
}
```

**Status Codes**:
| Code | Description |
|------|-------------|
| 200 | Audit found |
| 404 | Audit not found |

---

### Resume Audit (Human-in-the-Loop)

```http
POST /api/audit/{thread_id}/resume
```

Resume a paused audit with human decision.

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| thread_id | string | Audit thread identifier |

**Request Body**:
```json
{
  "human_decision": "APPROVE",
  "reviewer": "john.doe@example.com"
}
```

**Response**: Same as Submit Audit

**Status Codes**:
| Code | Description |
|------|-------------|
| 200 | Audit resumed successfully |
| 400 | Invalid decision or audit not in REVIEW status |
| 404 | Audit not found |

---

### Get Audit Report

```http
GET /api/audit/{thread_id}/report
```

Get the full audit report.

**Response**:
```json
{
  "report_id": "uuid",
  "document_id": "uuid",
  "generated_at": "2024-01-15T10:35:00Z",
  "overall_status": "COMPLIANT",
  "compliance_decision": "APPROVE",
  "compliance_score": 0.85,
  "provenance_trust_score": 1.0,
  "findings_summary": [...],
  "detailed_findings": [...],
  "recommendations": [...],
  "audit_trail": [...]
}
```

---

## Status Values

### ProcessingStatus

| Value | Description |
|-------|-------------|
| PENDING | Audit not started |
| INGESTING | Document being fetched |
| VERIFYING | Provenance verification |
| ANALYZING | Compliance analysis |
| COMPLIANT | Audit passed |
| NON_COMPLIANT | Audit failed |
| REQUIRES_REVIEW | Human review needed |
| ERROR | Processing failed |

### AgentDecision

| Value | Description |
|-------|-------------|
| APPROVE | Compliance verified |
| REJECT | Non-compliant |
| REVIEW | Needs human review |
| ESCALATE | Escalate to senior auditor |

---

## Error Responses

All errors follow this format:

```json
{
  "detail": {
    "error": "Error message",
    "code": "ERROR_CODE"
  }
}
```

### Common Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| INVALID_REQUEST | 400 | Malformed request body |
| DOCUMENT_TOO_LARGE | 413 | Document exceeds size limit |
| AUDIT_NOT_FOUND | 404 | Thread ID not found |
| ANALYSIS_FAILED | 500 | Internal processing error |
