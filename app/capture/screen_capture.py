"""
Módulo de captura periódica de tela.

Usa `mss` para capturas em memória — NENHUMA imagem é salva em disco.
As capturas são processadas pelo pipeline (OCR → Risco) e descartadas.
Privacidade da criança preservada: pais são notificados apenas sobre o risco.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from io import BytesIO

import mss
import numpy as np
from loguru import logger
from PIL import Image

from config import settings
from models.schemas import ScreenshotMeta


class ScreenCapture:
    """Realiza capturas de tela periódicas, processadas em memória e descartadas."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: list = []   # recebem (meta, image_array)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        logger.info(
            "ScreenCapture iniciado – intervalo: {}s (modo privado: sem disco)",
            settings.capture_interval_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ScreenCapture parado.")

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    async def _capture_loop(self) -> None:
        while self._running:
            try:
                meta, image_array = await asyncio.get_event_loop().run_in_executor(
                    None, self._take_screenshot
                )
                await self._notify(meta, image_array)
                # image_array sai de escopo aqui — memória liberada pelo GC
            except Exception as exc:
                logger.error("Erro na captura de tela: {}", exc)
            await asyncio.sleep(settings.capture_interval_seconds)

    # ------------------------------------------------------------------
    # Captura individual (em memória)
    # ------------------------------------------------------------------

    def _take_screenshot(self) -> tuple[ScreenshotMeta, np.ndarray]:
        """
        Captura a tela e retorna (meta, array numpy BGR).
        Nenhum arquivo é escrito em disco.
        """
        shot_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        with mss.mss() as sct:
            monitor = sct.monitors[0]       # monitor principal
            raw = sct.grab(monitor)
            # Converte para array numpy BGR (compatível com OpenCV/EasyOCR)
            image_array = np.array(raw)     # formato BGRA
            image_array = image_array[:, :, :3]  # descarta canal alpha → BGR

        meta = ScreenshotMeta(
            id=shot_id,
            captured_at=timestamp,
            width=raw.width,
            height=raw.height,
        )
        logger.debug("Captura em memória: {} ({}x{})", shot_id[:8], raw.width, raw.height)
        return meta, image_array

    # ------------------------------------------------------------------
    # Registro de callbacks e notificação
    # ------------------------------------------------------------------

    def register_callback(self, fn) -> None:
        """Registra uma função async chamada após cada captura.
        Assinatura esperada: async def fn(meta: ScreenshotMeta, image: np.ndarray)
        """
        self._callbacks.append(fn)

    async def _notify(self, meta: ScreenshotMeta, image_array: np.ndarray) -> None:
        for cb in self._callbacks:
            try:
                await cb(meta, image_array)
            except Exception as exc:
                logger.warning("Erro no callback de captura: {}", exc)

    # ------------------------------------------------------------------
    # Acesso pontual (sem loop — útil para testes)
    # ------------------------------------------------------------------

    def capture_once(self) -> tuple[ScreenshotMeta, np.ndarray]:
        """Captura única síncrona. Retorna (meta, array). Nada salvo em disco."""
        return self._take_screenshot()
