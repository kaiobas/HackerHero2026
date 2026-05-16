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

import numpy as np
from loguru import logger

from Agent.app.ai.pattern_agent import PatternAgent
from Agent.app.capture.screen_capture import ScreenCapture
from Agent.app.ocr.text_extractor import TextExtractor
from Agent.app.protection.overlay import OverlayProtection
from Agent.app.risk.risk_engine import RiskEngine
from Agent.config import settings
from Agent.models.schemas import (
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

        # 2. Avaliação de risco com léxico (sem IA – rápido)
        assessment = self.risk_engine.assess(extracted)
        self.latest_risk = assessment

        # 3. Acionar proteção visual (overlay decide prioridade RED > YELLOW)
        if assessment.level != RiskLevel.GREEN:
            self.overlay.apply(assessment)
            await self._create_alert(assessment)

    # ------------------------------------------------------------------
    # Loop do Agente de IA (periódico, mais lento)
    # ------------------------------------------------------------------

    async def _ai_loop(self) -> None:
        while self.running:
            await asyncio.sleep(settings.ai_analysis_interval_seconds)
            try:
                texts = list(self.text_history)
                if not texts:
                    continue

                ai_result = await self.agent.analyze(texts)
                logger.info(
                    "🤖 IA | Score: {} | Nível: {} | {}",
                    ai_result.score,
                    ai_result.risk_level.value.upper(),
                    ai_result.summary[:80],
                )

                # Re-avalia o último screenshot combinando com score da IA
                if self.screenshot_history and self.latest_risk:
                    last_meta = self.screenshot_history[-1]
                    # Re-avalia usando o último texto (sem nova captura de tela)
                    from Agent.models.schemas import ExtractedText as ET
                    from datetime import datetime as dt
                    dummy_extracted = ET(
                        screenshot_id=last_meta.id,
                        raw_text=" ".join(list(self.text_history)[-3:]),
                        confidence=1.0,
                        extracted_at=dt.utcnow(),
                    )
                    combined = self.risk_engine.assess(dummy_extracted, ai_score=ai_result.score)
                    self.latest_risk = combined

                    if combined.level != RiskLevel.GREEN:
                        self.overlay.apply(combined)
                        await self._create_alert(combined)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Erro no loop de IA: {}", exc)

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
