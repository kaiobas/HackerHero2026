"""Schemas Pydantic compartilhados entre módulos."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    GREEN  = "green"    # Sem risco detectado
    YELLOW = "yellow"   # Alerta – conversa suspeita
    RED    = "red"      # Risco alto – bloqueia e desfoca a tela


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------

class ScreenshotMeta(BaseModel):
    id: str
    captured_at: datetime
    width: int
    height: int
    # Nota: sem filepath — screenshots nunca são salvos em disco (privacidade)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

class ExtractedText(BaseModel):
    screenshot_id: str
    raw_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_at: datetime


# ---------------------------------------------------------------------------
# Risco
# ---------------------------------------------------------------------------

class RiskSignal(BaseModel):
    keyword: str
    category: str          # ex: "grooming", "violência", "contato pessoal"
    weight: int = Field(ge=1, le=10)


class RiskAssessment(BaseModel):
    screenshot_id: str
    level: RiskLevel
    score: int = Field(ge=0, le=100)
    signals: list[RiskSignal] = []
    assessed_at: datetime
    explanation: str = ""


# ---------------------------------------------------------------------------
# Agente de IA
# ---------------------------------------------------------------------------

class AIAnalysisRequest(BaseModel):
    texts: list[str]           # janela de textos recentes (últimas N capturas)
    context_window: int = 10


class AIAnalysisResult(BaseModel):
    risk_level: RiskLevel
    score: int = Field(ge=0, le=100)
    summary: str
    keywords_found: list[str] = []
    analyzed_at: datetime
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Overlay / Proteção
# ---------------------------------------------------------------------------

class ProtectionAction(str, Enum):
    NONE       = "none"
    WARN       = "warn"        # exibe alerta visual leve
    BLUR       = "blur"        # desfoca a tela
    QUARANTINE = "quarantine"  # tela bloqueada + mensagem
    UNBLOCK    = "unblock"     # remove proteção


class ProtectionState(BaseModel):
    active: bool = False
    action: ProtectionAction = ProtectionAction.NONE
    triggered_at: datetime | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Alert (para notificação aos pais)
# ---------------------------------------------------------------------------

class Alert(BaseModel):
    alert_id: str
    risk_level: RiskLevel
    message: str
    # Sem screenshot_path: privacidade da criança preservada.
    # Pais são notificados apenas sobre o nível de risco.
    triggered_at: datetime
    acknowledged: bool = False
