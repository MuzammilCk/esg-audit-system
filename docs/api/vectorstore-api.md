# Vector Store API Reference

The Vector Store API provides document indexing and semantic search capabilities using Qdrant.

**Base URL**: `http://localhost:8004`

## Endpoints

### Health Check

```http
GET /healthz
```

**Response**:
```json
{
  "status": "ok",
  "service": "vector-store"
}
```

---

### Get Statistics

```http
GET /api/stats
```

Get collection statistics.

**Response**:
```json
{
  "collection_name": "esg_documents",
  "vectors_count": 15000,
  "indexed_vectors_count": 15000,
  "segments_count": 4,
  "status": "green"
}
```

---

### Index Document

```http
POST /api/index
```

Index a document for semantic search.

**Request Body**:
```json
{
  "content": "string (required) - Document content",
  "document_id": "string (required) - Unique identifier",
  "source_url": "string - Source URL",
  "original_filename": "string - Original filename",
  "mime_type": "string - MIME type",
  "supplier_id": "string - Supplier identifier",
  "region": "string - Geographic region",
  "reporting_period": "string - Reporting period"
}
```

**Response**:
```json
{
  "document_id": "doc-123",
  "chunks_indexed": 5,
  "total_tokens": 2500,
  "errors": []
}
```

**Example**:
```bash
curl -X POST http://localhost:8004/api/index \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Sustainability Report...",
    "document_id": "doc-123",
    "source_url": "https://example.com/report.pdf",
    "region": "EU"
  }'
```

---

### Search Documents

```http
POST /api/search
```

Search indexed documents.

**Request Body**:
```json
{
  "query": "string (required) - Search query",
  "limit": "integer - Max results (default: 10)",
  "method": "string - dense, sparse, or hybrid (default: hybrid)",
  "filters": {
    "supplier_id": "string",
    "region": "string",
    "regulation_codes": ["ESRS E1"]
  },
  "dense_weight": "float - Dense weight for hybrid (default: 0.7)",
  "sparse_weight": "float - Sparse weight for hybrid (default: 0.3)"
}
```

**Response**:
```json
{
  "query": "GHG emissions",
  "results": [
    {
      "id": "chunk-123",
      "content": "Scope 1 emissions: 15,000 tCO2e...",
      "score": 0.92,
      "metadata": {
        "document_id": "doc-123",
        "chunk_index": 0,
        "regulation_codes": ["ESRS E1"]
      }
    }
  ],
  "total_results": 5,
  "method": "hybrid"
}
```

---

### Delete Document

```http
DELETE /api/index/{document_id}
```

Remove a document and all its chunks.

**Response**:
```json
{
  "success": true
}
```

---

### Get Regulation Context

```http
POST /api/regulation-context
```

Get context specific to a regulation code.

**Request Body**:
```json
{
  "regulation_code": "ESRS E1",
  "supplier_id": "string (optional)",
  "region": "string (optional)",
  "limit": "integer (default: 5)"
}
```

**Response**:
```json
{
  "regulation_code": "ESRS E1",
  "relevant_chunks": [...],
  "compliance_hints": [
    "Document contains disclosure language for ESRS E1"
  ],
  "related_requirements": ["ESRS E2", "ESRS E3", "SEC-GHG"]
}
```

---

## Search Methods

### Dense Search
Semantic similarity using vector embeddings. Best for:
- Conceptual queries
- Paraphrased content
- Multi-language support

### Sparse Search
BM25-style keyword matching. Best for:
- Exact term matching
- Technical terminology
- Regulation code lookup

### Hybrid Search (Default)
Combines dense and sparse using reciprocal rank fusion. Best for:
- General-purpose search
- Balanced relevance
- Most ESG queries

---

## Embedding Models

| Model | Dimensions | Use Case |
|-------|------------|----------|
| text-embedding-3-small | 1536 | Default, cost-effective |
| text-embedding-3-large | 3072 | Higher accuracy |
| local-all-MiniLM-L6-v2 | 384 | Offline, no API calls |
