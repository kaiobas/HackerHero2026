"""
Agente de IA – Camada 2 (Ollama local)

Chamado APENAS quando a Camada 1 (Layer1Filter) detectar padrões suspeitos.
Usa o modelo qwen2.5:7b rodando localmente via Ollama para análise contextual
profunda, sem enviar dados a servidores externos.

Endpoint Ollama: http://localhost:11434/api/chat
Modelo padrão  : qwen2.5:7b  (configurável via OLLAMA_MODEL no .env)

O agente retorna:
  - Nível de risco (green / yellow / red)
  - Score 0-100
  - Resumo em linguagem natural
  - Palavras/frases-chave encontradas
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from config import settings
from models.schemas import AIAnalysisResult, RiskLevel

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
Você é um agente especializado em proteção de crianças no ambiente digital,
com foco em detecção de grooming, assédio sexual, bullying e extorsão online.

Você receberá trechos de texto extraídos da tela de uma criança enquanto ela
joga ou usa o computador. A Camada 1 (filtro léxico) já identificou sinais
suspeitos. Seu papel é confirmar ou descartar o risco com análise contextual.

Você DEVE retornar APENAS um JSON válido com o seguinte schema:
{
  "risk_level": "green" | "yellow" | "red",
  "score": <inteiro 0-100>,
  "summary": "<resumo em português, máx 120 chars>",
  "keywords_found": ["<palavra ou frase suspeita>"]
}

Critérios:
- GREEN  (0-39):  Falso positivo — contexto normal de jogo.
- YELLOW (40-69): Comportamento suspeito mas inconclusivo.
- RED    (70-100): Grooming confirmado, coerção, conteúdo sexual, ameaças.

Os textos podem estar em português (BR) ou inglês. Considere gírias e
linguagem de jogos online. Na dúvida, classifique um nível acima.
RETORNE APENAS O JSON, sem texto adicional.
""".strip()

_OLLAMA_URL = "http://localhost:11434/api/chat"
_TIMEOUT = 60.0   # segundos — modelo local pode ser mais lento


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------

class PatternAgent:
    """Camada 2 — análise contextual via Ollama (qwen2.5:7b)."""

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._http

    # ------------------------------------------------------------------
    # Análise principal
    # ------------------------------------------------------------------

    async def analyze(self, texts: list[str]) -> AIAnalysisResult:
        """
        Analisa uma janela de textos suspeitos e retorna avaliação de risco.

        Só deve ser chamado após Camada 1 retornar suspicious=True.

        Args:
            texts: Lista de textos extraídos das últimas N capturas.

        Returns:
            AIAnalysisResult com nível de risco, score e resumo.
        """
        if not texts:
            return self._empty_result()

        window = texts[-settings.ai_context_window:]
        user_content = self._build_user_message(window)

        payload = {
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
            "format": "json",
        }

        try:
            resp = await self._client().post(_OLLAMA_URL, json=payload)
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            result = self._parse_response(raw)
            logger.info(
                "🤖 Ollama | Score: {} | {} | {}",
                result.score, result.risk_level.value.upper(), result.summary[:60],
            )
            return result

        except httpx.ConnectError:
            logger.error("Ollama não está rodando em {}. Inicie com: ollama serve", _OLLAMA_URL)
            return self._empty_result()
        except Exception as exc:
            logger.error("Erro no Agente Ollama: {}", exc)
            return self._empty_result()

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_message(texts: list[str]) -> str:
        numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(texts))
        return (
            f"Analise os seguintes {len(texts)} trechos de texto "
            f"capturados da tela:\n\n{numbered}"
        )

    @staticmethod
    def _parse_response(raw: str) -> AIAnalysisResult:
        try:
            data: dict[str, Any] = json.loads(raw)
            level_str = data.get("risk_level", "green").lower()
            level = (
                RiskLevel(level_str)
                if level_str in RiskLevel._value2member_map_
                else RiskLevel.GREEN
            )
            return AIAnalysisResult(
                risk_level=level,
                score=int(data.get("score", 0)),
                summary=str(data.get("summary", "")),
                keywords_found=list(data.get("keywords_found", [])),
                analyzed_at=datetime.utcnow(),
                raw_response=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Falha ao parsear resposta Ollama: {} | Raw: {}", exc, raw[:200])
            return PatternAgent._empty_result()

    @staticmethod
    def _empty_result() -> AIAnalysisResult:
        return AIAnalysisResult(
            risk_level=RiskLevel.GREEN,
            score=0,
            summary="Análise indisponível.",
            analyzed_at=datetime.utcnow(),
        )
