"""
HackerHero Guardian – Ponto de Entrada

Inicia o servidor FastAPI + o orquestrador em background.

Uso:
    python main.py

Ou diretamente via uvicorn:
    uvicorn main:app --host 127.0.0.1 --port 8000
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import router
from app.guardian import GuardianOrchestrator
from config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
)
logger.add(
    "logs/guardian_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    guardian = GuardianOrchestrator()
    app.state.guardian = guardian
    await guardian.start()
    logger.success("✅ {} v{} rodando em http://{}:{}",
                   settings.app_name, settings.app_version,
                   settings.api_host, settings.api_port)
    yield
    # ── Shutdown ──
    await guardian.stop()
    logger.info("Servidor encerrado.")


# ---------------------------------------------------------------------------
# Aplicação FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API de proteção de crianças em jogos online. "
        "Monitora a tela, detecta padrões suspeitos e aciona proteção em tempo real."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ---------------------------------------------------------------------------
# Health-check simples (sem autenticação)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok", "app": settings.app_name}


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="warning",   # uvicorn silencioso – loguru cuida do resto
    )
