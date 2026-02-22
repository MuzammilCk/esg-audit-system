
import os
import logging
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import shutil

# Import logic from other services
# In a real microservice architecture, these would be HTTP calls to other containers.
# For simplicity and given the codebase structure, we import the modules directly if available,
# or we stub them if dependencies are missing in this container.
# The user asked to integrate them.
try:
    from services.verification.c2pa_validator import C2PAValidator
    from services.privacy.presidio_masker import PIIMasker
    from services.privacy.redis_manager import RedisManager
except ImportError as e:
    logging.warning(f"Could not import internal services: {e}. Running in mock mode.")
    C2PAValidator = None
    PIIMasker = None
    RedisManager = None

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="services/ui/static"), name="static")

# Service instances
c2pa_validator = C2PAValidator() if C2PAValidator else None
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
encryption_key = os.getenv("ENCRYPTION_KEY", "test-key-must-be-bytes") # Fallback for dev

if RedisManager:
    redis_manager = RedisManager(host=redis_host, port=redis_port, encryption_key=encryption_key)
    pii_masker = PIIMasker(redis_manager) if PIIMasker else None
else:
    pii_masker = None

@app.get("/")
async def read_index():
    return FileResponse("services/ui/static/index.html")

@app.post("/api/verify")
async def verify_provenance(file: UploadFile = File(...)):
    if not c2pa_validator:
         return JSONResponse(status_code=503, content={"status": "FAILURE", "errors": ["Validation service unavailable"]})
    
    try:
        contents = await file.read()
        report = c2pa_validator.validate_provenance(contents)
        return report.dict()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "FAILURE", "errors": [str(e)]})

class TextRequest(BaseModel):
    text: str

@app.post("/api/redact")
async def redact_pii(request: TextRequest):
    if not pii_masker:
        return JSONResponse(status_code=503, content={"error": "Privacy service unavailable"})

    # Generate a simple Doc ID for demo
    import uuid
    doc_id = str(uuid.uuid4())
    
    masked_text, success = pii_masker.mask_text(request.text, doc_id)
    
    if success:
        return {"masked_text": masked_text, "key": f"pii:{doc_id}"}
    else:
        return JSONResponse(status_code=500, content={"error": "Masking failed"})
