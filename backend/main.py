import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from api.routes.agent import router as agent_router
from api.routes.eval import router as eval_router
from api.routes.ingest import router as ingest_router
from api.routes.product import router as product_router
from api.routes.tools import router as tools_router
from api.routes.workspace import router as workspace_router

load_dotenv()


def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_ORIGIN")
    default_origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    if not configured_origins:
        return default_origins

    origins = [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    ]
    return sorted(set([*origins, *default_origins]))

app = FastAPI(
    title="LegalMind AI API",
    description="Backend API for multi-format legal document intelligence.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(ingest_router)
app.include_router(tools_router)
app.include_router(agent_router)
app.include_router(workspace_router)
app.include_router(product_router)
app.include_router(eval_router)
