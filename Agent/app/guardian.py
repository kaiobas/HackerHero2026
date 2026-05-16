"""
Guardian Orchestrator

Orquestra o pipeline completo:
  ScreenCapture → OCR → RiskEngine → PatternAgent (periódico) → OverlayProtection

Também gerencia o histórico de alertas e screenshots.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import datetime

import httpx
import numpy as np
from loguru import logger

from app.ai.pattern_agent import PatternAgent
from app.capture.screen_capture import ScreenCapture
from app.ocr.text_extractor import TextExtractor
from app.protection.overlay import OverlayProtection
from app.risk.risk_engine import RiskEngine
from config import settings
from models.schemas import (
    Alert,
    ExtractedText,
    RiskAssessment,
    RiskLevel,
    ScreenshotMeta,
)


class GuardianOrchestrator:
    """Ponto central que conecta todos os módulos."""

    def __init__(self) -> None:
        self.capture    = ScreenCapture()
        self.extractor  = TextExtractor()
        self.risk_engine = RiskEngine()
        self.agent      = PatternAgent()
        self.overlay    = OverlayProtection()

        self.running     = False
        self.started_at  = datetime.utcnow()

        # Histórico em memória (limitado)
        self.screenshot_history: deque[ScreenshotMeta] = deque(maxlen=200)
        self.text_history: deque[str]                  = deque(maxlen=50)
        self.alerts: list[Alert]                       = []
        self.latest_risk: RiskAssessment | None        = None
        self.screenshot_count: int                     = 0

        self._ai_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self.running = True
        self.overlay.start()

        # Registra o callback de pipeline no capturador
        self.capture.register_callback(self._on_screenshot)

        # Inicia captura periódica
        await self.capture.start()

        # Loop periódico do Agente de IA
        self._ai_task = asyncio.create_task(self._ai_loop())

        logger.success("🛡️  Guardian iniciado.")

    async def stop(self) -> None:
        self.running = False
        await self.capture.stop()
        if self._ai_task:
            self._ai_task.cancel()
        await self.agent.close()
        self.overlay.stop()
        logger.info("Guardian parado.")

    # ------------------------------------------------------------------
    # Pipeline principal (chamado a cada captura)
    # ------------------------------------------------------------------

    async def _on_screenshot(self, meta: ScreenshotMeta, image: np.ndarray) -> None:
        self.screenshot_count += 1
        self.screenshot_history.append(meta)

        # 1. OCR — imagem processada em memória e descartada
        extracted: ExtractedText = await self.extractor.extract(meta, image)
        del image   # libera memória imediatamente

        if extracted.raw_text.strip():
            self.text_history.append(extracted.raw_text)

        # 2. Camada 1 — filtro léxico rápido
        layer1 = self.risk_engine.run_layer1(extracted.raw_text)

        if not layer1.suspicious:
            # Nenhum padrão suspeito: pipeline para aqui, sem chamar a IA
            return

        # 3. Camada 1 detectou algo — avalia score L1 imediatamente
        assessment = self.risk_engine.assess(extracted, ai_score=0, layer1=layer1)
        self.latest_risk = assessment

        # 4. Acionar proteção preventiva enquanto aguarda IA
        if assessment.level != RiskLevel.GREEN:
            self.overlay.apply(assessment)
            await self._create_alert(assessment)

        # 5. Camada 2 — IA (Ollama) confirma ou descarta o risco
        try:
            texts_window = list(self.text_history)
            ai_result = await self.agent.analyze(texts_window)

            combined = self.risk_engine.assess(
                extracted, ai_score=ai_result.score, layer1=layer1
            )
            self.latest_risk = combined

            if combined.level != RiskLevel.GREEN:
                self.overlay.apply(combined)
                await self._create_alert(combined)
            else:
                # IA descartou: libera overlay se estava ativado por falso-positivo
                self.overlay.release()
        except Exception as exc:
            logger.error("Erro na Camada 2 (Ollama): {}", exc)

    # ------------------------------------------------------------------
    # Loop do Agente de IA (periódico, mais lento)
    # ------------------------------------------------------------------

    async def _ai_loop(self) -> None:
        """Loop de manutenção — mantém a conexão Ollama aquecida a cada 5 min."""
        while self.running:
            await asyncio.sleep(300)
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    await c.get("http://localhost:11434/api/tags")
            except Exception:
                logger.warning("⚠️  Ollama não está respondendo em localhost:11434")
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Alertas
    # ------------------------------------------------------------------

    async def _create_alert(
        self, assessment: RiskAssessment
    ) -> None:
        # Evita alertas duplicados recentes para o mesmo nível
        if self.alerts and self.alerts[-1].risk_level == assessment.level:
            # Atualiza timestamp mas não duplica
            return

        alert = Alert(
            alert_id=str(uuid.uuid4()),
            risk_level=assessment.level,
            message=assessment.explanation,
            triggered_at=assessment.assessed_at,
        )
        self.alerts.append(alert)
        logger.warning("🚨 Alerta criado: {} | {}", alert.alert_id[:8], alert.message)
