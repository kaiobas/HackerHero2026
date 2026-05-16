"""
API FastAPI – Rotas do Guardian

Endpoints disponíveis:
  GET  /status            → estado atual do sistema
  GET  /alerts            → lista de alertas gerados
  GET  /alerts/{id}       → detalhe de um alerta
  POST /alerts/{id}/ack   → marca alerta como lido
  GET  /risk/latest       → última avaliação de risco
  POST /protection/release → responsável libera a tela bloqueada
  GET  /screenshots       → lista últimas capturas
  GET  /config            → configurações atuais
  PATCH /config           → atualiza configurações em tempo real
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from Agent.config import settings
from Agent.models.schemas import (
    Alert,
    ProtectionState,
    RiskAssessment,
    RiskLevel,
    ScreenshotMeta,
)

router = APIRouter(prefix="/api/v1", tags=["guardian"])

# ---------------------------------------------------------------------------
# Dependência: acesso ao estado global (injetado pelo main.py via app.state)
# ---------------------------------------------------------------------------

def get_guardian(request=None):
    """Retorna a instância do GuardianOrchestrator a partir do app.state."""
    from fastapi import Request
    # Importado aqui para evitar circular imports
    return request.app.state.guardian  # type: ignore


# ---------------------------------------------------------------------------
# Schemas de resposta
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    app_name: str
    version: str
    running: bool
    current_risk: RiskLevel
    protection_active: bool
    uptime_seconds: float
    total_screenshots: int
    total_alerts: int


class ConfigPatch(BaseModel):
    capture_interval_seconds: int | None = None
    risk_yellow_threshold: int | None = None
    risk_red_threshold: int | None = None
    ai_analysis_interval_seconds: int | None = None


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.get("/status", response_model=StatusResponse)
async def get_status(request: "fastapi.Request"):  # type: ignore[name-defined]
    g = request.app.state.guardian
    prot = g.overlay.state
    return StatusResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        running=g.running,
        current_risk=g.latest_risk.level if g.latest_risk else RiskLevel.GREEN,
        protection_active=prot.active,
        uptime_seconds=(datetime.utcnow() - g.started_at).total_seconds(),
        total_screenshots=g.screenshot_count,
        total_alerts=len(g.alerts),
    )


@router.get("/alerts", response_model=list[Alert])
async def list_alerts(request: "fastapi.Request"):  # type: ignore[name-defined]
    g = request.app.state.guardian
    return list(reversed(g.alerts))   # mais recentes primeiro


@router.get("/alerts/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str, request: "fastapi.Request"):  # type: ignore[name-defined]
    g = request.app.state.guardian
    for alert in g.alerts:
        if alert.alert_id == alert_id:
            return alert
    raise HTTPException(status_code=404, detail="Alerta não encontrado.")


@router.post("/alerts/{alert_id}/ack", response_model=Alert)
async def acknowledge_alert(alert_id: str, request: "fastapi.Request"):  # type: ignore[name-defined]
    g = request.app.state.guardian
    for alert in g.alerts:
        if alert.alert_id == alert_id:
            alert.acknowledged = True
            return alert
    raise HTTPException(status_code=404, detail="Alerta não encontrado.")


@router.get("/risk/latest", response_model=RiskAssessment | None)
async def latest_risk(request: "fastapi.Request"):  # type: ignore[name-defined]
    return request.app.state.guardian.latest_risk


@router.post("/protection/release", response_model=ProtectionState)
async def release_protection(request: "fastapi.Request"):  # type: ignore[name-defined]
    g = request.app.state.guardian
    g.overlay.release()
    return g.overlay.state


@router.get("/config")
async def get_config():
    return {
        "capture_interval_seconds": settings.capture_interval_seconds,
        "risk_yellow_threshold": settings.risk_yellow_threshold,
        "risk_red_threshold": settings.risk_red_threshold,
        "ai_analysis_interval_seconds": settings.ai_analysis_interval_seconds,
        "ocr_languages": settings.ocr_languages,
        "openai_model": settings.openai_model,
        "blur_strength": settings.blur_strength,
    }


@router.patch("/config")
async def patch_config(patch: ConfigPatch):
    """Atualiza configurações em tempo real (sem reiniciar o app)."""
    if patch.capture_interval_seconds is not None:
        settings.capture_interval_seconds = patch.capture_interval_seconds
    if patch.risk_yellow_threshold is not None:
        settings.risk_yellow_threshold = patch.risk_yellow_threshold
    if patch.risk_red_threshold is not None:
        settings.risk_red_threshold = patch.risk_red_threshold
    if patch.ai_analysis_interval_seconds is not None:
        settings.ai_analysis_interval_seconds = patch.ai_analysis_interval_seconds
    return {"ok": True, "updated": patch.model_dump(exclude_none=True)}
