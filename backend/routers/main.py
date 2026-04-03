"""
DocVerify AI — Backend Verification API
FastAPI application exposing verification endpoints for all document types.

Run with:
    uvicorn backend.main:app --reload --port 8000

Or from project root:
    python -m uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.routers import college, government, corporate

app = FastAPI(
    title="DocVerify AI — Backend API",
    description="""
## Document Verification Backend API

Provides verification endpoints for multiple document types:

### Supported APIs
| API | Status | Endpoint Prefix |
|-----|--------|----------------|
| **College / Academic** | ✅ Live (Dummy DB) | `/api/college` |
| **Government ID** | 🔶 Placeholder | `/api/government` |
| **Corporate / Employment** | 🔶 Placeholder | `/api/corporate` |

### College API Features
- Student lookup by PRN, name, certificate number, enrollment number
- Fuzzy name matching with confidence scoring
- Field-level match/mismatch reporting
- College registry with alias resolution

### Adding a New API
1. Create `backend/routers/your_api.py`
2. Register in `backend/main.py`
3. Add a client in `utils/api_clients/`
4. Register in `utils/api_clients/registry.py`
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS (allow Streamlit frontend) ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register Routers ─────────────────────────────────────────────────────────
app.include_router(college.router)
app.include_router(government.router)
app.include_router(corporate.router)


# ─── Root & Health ────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "service": "DocVerify AI Backend API",
        "version": "1.0.0",
        "status": "running",
        "apis": {
            "college": "/api/college",
            "government": "/api/government",
            "corporate": "/api/corporate",
        },
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "service": "DocVerify AI Backend"}


# ─── Run directly ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
