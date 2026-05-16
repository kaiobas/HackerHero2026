"""
Módulo OCR – extração de texto a partir de arrays numpy em memória.

Recebe a imagem diretamente do ScreenCapture (nunca lida do disco).
Usa EasyOCR com suporte a português e inglês.
O reader é inicializado uma vez (lazy) para economizar memória.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from Agent.config import settings
from Agent.models.schemas import ExtractedText, ScreenshotMeta

# EasyOCR importado com tratamento de ausência de GPU
try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False
    logger.warning("easyocr não encontrado – OCR desativado.")


class TextExtractor:
    """Extrai texto de arrays de imagem em memória via EasyOCR."""

    def __init__(self) -> None:
        self._reader: Optional["easyocr.Reader"] = None

    # ------------------------------------------------------------------
    # Inicialização lazy
    # ------------------------------------------------------------------

    def _get_reader(self):
        if self._reader is None:
            if not _EASYOCR_AVAILABLE:
                raise RuntimeError("easyocr não está instalado.")
            logger.info(
                "Inicializando EasyOCR (idiomas: {}, GPU: {}) …",
                settings.ocr_languages,
                settings.ocr_gpu,
            )
            self._reader = easyocr.Reader(
                settings.ocr_languages,
                gpu=settings.ocr_gpu,
                verbose=False,
            )
            logger.info("EasyOCR pronto.")
        return self._reader

    # ------------------------------------------------------------------
    # Extração principal
    # ------------------------------------------------------------------

    async def extract(self, meta: ScreenshotMeta, image: np.ndarray) -> ExtractedText:
        """
        Extrai texto de um array de imagem numpy de forma assíncrona.
        A imagem existe apenas em memória e é descartada após o processamento.
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._extract_sync, meta, image)
        return result

    def _extract_sync(self, meta: ScreenshotMeta, image: np.ndarray) -> ExtractedText:
        if image is None or image.size == 0:
            return ExtractedText(
                screenshot_id=meta.id,
                raw_text="",
                confidence=0.0,
                extracted_at=datetime.utcnow(),
            )

        # Pré-processamento da imagem para melhorar acurácia OCR
        processed = self._preprocess(image)

        reader = self._get_reader()
        results = reader.readtext(processed, detail=1, paragraph=False)

        # Agrega textos e calcula confiança média
        texts: list[str] = []
        confidences: list[float] = []
        for (_bbox, text, conf) in results:
            if conf > 0.2 and text.strip():   # filtra ruído
                texts.append(text.strip())
                confidences.append(conf)

        raw_text = " ".join(texts)
        avg_conf = float(np.mean(confidences)) if confidences else 0.0

        logger.debug(
            "OCR [{}] – {} palavras, confiança média: {:.2f}",
            meta.id[:8],
            len(texts),
            avg_conf,
        )

        return ExtractedText(
            screenshot_id=meta.id,
            raw_text=raw_text,
            confidence=round(avg_conf, 4),
            extracted_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Pré-processamento
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """
        Pipeline de pré-processamento:
        1. Converte para escala de cinza
        2. Aplica denoising
        3. Aumenta contraste (CLAHE)
        4. Binarização adaptativa
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        denoised = cv2.fastNlMeansDenoising(gray, h=10)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Binarização – melhora leitura de texto em fundos variados
        binary = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2,
        )
        return binary
