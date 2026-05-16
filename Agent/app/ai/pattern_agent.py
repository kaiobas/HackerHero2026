"""
Agente de IA – Detecção de Padrões de Assédio / Grooming

Usa um LLM (OpenAI GPT-4o-mini por padrão) via LangChain para analisar
uma janela de textos recentes e classificar o risco de forma contextual,
indo além das palavras-chave do léxico estático.

O agente retorna:
  - Nível de risco (green / yellow / red)
  - Score 0-100
  - Resumo em linguagem natural
  - Palavras/frases-chave encontradas
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from loguru import logger

from Agent.config import settings
from Agent.models.schemas import AIAnalysisResult, RiskLevel

# ---------------------------------------------------------------------------
# System Prompt do Agente
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
Você é um agente especializado em proteção de crianças no ambiente digital, 
com foco em detecção de grooming, assédio sexual, bullying e extorsão online.

Você receberá trechos de texto extraídos da tela de uma criança enquanto ela
joga ou usa o computador. Seu papel é analisar o CONTEXTO e identificar
padrões suspeitos de comportamento de adultos mal-intencionados.

Você DEVE retornar APENAS um JSON válido com o seguinte schema:
{
  "risk_level": "green" | "yellow" | "red",
  "score": <inteiro 0-100>,
  "summary": "<resumo em português>",
  "keywords_found": ["<palavra ou frase suspeita>", ...]
}

Critérios de classificação:
- GREEN  (score 0-39):  Conversas normais de jogo, sem indícios de assédio.
- YELLOW (score 40-69): Sinais de alerta: tentativa de isolamento, 
                         pedidos de informações pessoais, linguagem inapropriada,
                         tentativa de migrar para outra plataforma.
- RED    (score 70-100): Conteúdo sexual explícito, ameaças, coerção, 
                          solicitação de fotos/vídeos, marcação de encontros.

Contexto cultural: os textos podem estar em português (BR) ou inglês.
Considere gírias, abreviações e linguagem de jogos online.
Seja conservador: na dúvida, prefira classificar um nível acima.
RETORNE APENAS O JSON, sem texto adicional.
""".strip()


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------

class PatternAgent:
    """Agente LLM que analisa padrões de risco em janelas de texto."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        """Inicializa o cliente OpenAI de forma lazy."""
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY não configurada. "
                    "Defina a variável no arquivo .env."
                )
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    # ------------------------------------------------------------------
    # Análise principal
    # ------------------------------------------------------------------

    async def analyze(self, texts: list[str]) -> AIAnalysisResult:
        """
        Analisa uma janela de textos recentes e retorna a avaliação de risco.

        Args:
            texts: Lista de textos extraídos das últimas N capturas.

        Returns:
            AIAnalysisResult com nível de risco, score e resumo.
        """
        if not texts:
            return self._empty_result()

        # Limita ao tamanho da janela de contexto configurada
        window = texts[-settings.ai_context_window :]
        user_content = self._build_user_message(window)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                temperature=0.1,          # baixa temperatura = respostas mais consistentes
                max_tokens=512,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            return self._parse_response(raw)

        except Exception as exc:
            logger.error("Erro no Agente de IA: {}", exc)
            return self._empty_result()

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
            level = RiskLevel(level_str) if level_str in RiskLevel._value2member_map_ else RiskLevel.GREEN
            return AIAnalysisResult(
                risk_level=level,
                score=int(data.get("score", 0)),
                summary=str(data.get("summary", "")),
                keywords_found=list(data.get("keywords_found", [])),
                analyzed_at=datetime.utcnow(),
                raw_response=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Falha ao parsear resposta da IA: {} | Raw: {}", exc, raw[:200])
            return PatternAgent._empty_result()

    @staticmethod
    def _empty_result() -> AIAnalysisResult:
        return AIAnalysisResult(
            risk_level=RiskLevel.GREEN,
            score=0,
            summary="Análise indisponível.",
            analyzed_at=datetime.utcnow(),
        )
