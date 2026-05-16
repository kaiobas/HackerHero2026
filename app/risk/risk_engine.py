"""
Motor de Risco – Semáforo de Proteção

Classifica o risco de cada texto extraído em três níveis:
  🟢 GREEN  – sem risco detectado
  🟡 YELLOW – conversa suspeita / alerta
  🔴 RED    – risco alto, acionar proteção imediata

A pontuação é calculada combinando:
  1. Correspondência de palavras-chave categorizadas (léxico estático)
  2. Pontuação do Agente de IA (quando disponível)
"""

from __future__ import annotations

import re
from datetime import datetime

from loguru import logger

from config import settings
from models.schemas import (
    ExtractedText,
    RiskAssessment,
    RiskLevel,
    RiskSignal,
)

# ---------------------------------------------------------------------------
# Léxico de palavras-chave por categoria e peso
# ---------------------------------------------------------------------------
# Pesos: 1-3 = baixo, 4-6 = médio, 7-10 = alto
# Categorias seguem o modelo de grooming online (UNESCO / SaferNet)

KEYWORD_LEXICON: list[dict] = [
    # --- Grooming / aproximação ---
    {"pattern": r"\b(oi|olá|ei)\b.*\b(sozinho|sozinha)\b",  "category": "grooming",         "weight": 5},
    {"pattern": r"\b(quantos anos|sua idade|como old are you)\b",  "category": "grooming",   "weight": 6},
    {"pattern": r"\b(não conta|segredo|entre nós|só nós dois)\b",  "category": "grooming",   "weight": 8},
    {"pattern": r"\b(encontrar|se encontrar|te ver pessoalmente)\b","category": "encontro",  "weight": 9},
    {"pattern": r"\b(manda foto|me envia foto|foto tua|selfie)\b",  "category": "grooming",  "weight": 8},
    {"pattern": r"\b(gosto de você|te amo|namorad[oa])\b",          "category": "grooming",  "weight": 5},

    # --- Contato pessoal / fora da plataforma ---
    {"pattern": r"\b(whatsapp|telegram|discord|instagram|snapchat)\b","category": "contato_externo","weight": 6},
    {"pattern": r"\b(meu número|meu cel|meu telefone|me add)\b",     "category": "contato_externo","weight": 7},

    # --- Conteúdo sexual explícito ---
    {"pattern": r"\b(nude|pelad[oa]|sexo|transar|ficar)\b",         "category": "sexual",    "weight": 10},
    {"pattern": r"\b(porn[oô]|xcam|webcam|strip)\b",                "category": "sexual",    "weight": 10},
    {"pattern": r"\b(ped[oô]|menor|criança.*(sexo|foto))\b",        "category": "sexual",    "weight": 10},

    # --- Ameaça / extorsão ---
    {"pattern": r"\b(vou te machucar|vou te achar|sei onde você mora)\b","category": "ameaça","weight": 10},
    {"pattern": r"\b(chantagem|vai se arrepender|te denuncio)\b",   "category": "ameaça",    "weight": 9},
    {"pattern": r"\b(se não fizer|se não mandar)\b",                "category": "coerção",   "weight": 8},

    # --- Bullying / assédio ---
    {"pattern": r"\b(idiota|imbecil|lixo|inútil|sua mãe)\b",       "category": "bullying",  "weight": 4},
    {"pattern": r"\b(se mata|se matar|vai morrer)\b",               "category": "violência", "weight": 10},
    {"pattern": r"\b(feio|feia|gordo|gorda|lerdo)\b",               "category": "bullying",  "weight": 3},

    # --- Informações pessoais (tentativa de coleta) ---
    {"pattern": r"\b(qual.*escola|onde.*mora|seu endereço)\b",      "category": "dados_pessoais","weight": 8},
    {"pattern": r"\b(nome completo|cpf|senha)\b",                   "category": "dados_pessoais","weight": 9},
]

# Pré-compila os padrões regex
_COMPILED: list[tuple[re.Pattern, str, int]] = [
    (re.compile(entry["pattern"], re.IGNORECASE | re.DOTALL), entry["category"], entry["weight"])
    for entry in KEYWORD_LEXICON
]


# ---------------------------------------------------------------------------
# Motor de Risco
# ---------------------------------------------------------------------------

class RiskEngine:
    """Avalia o nível de risco de um texto extraído."""

    def assess(self, extracted: ExtractedText, ai_score: int = 0) -> RiskAssessment:
        """
        Calcula a pontuação de risco combinando léxico + pontuação da IA.

        Args:
            extracted: Texto extraído pelo módulo OCR.
            ai_score:  Pontuação (0-100) retornada pelo Agente de IA (opcional).

        Returns:
            RiskAssessment com nível semáforo, sinais detectados e explicação.
        """
        text = extracted.raw_text
        signals: list[RiskSignal] = []
        total_weight = 0

        for pattern, category, weight in _COMPILED:
            if pattern.search(text):
                signal = RiskSignal(keyword=pattern.pattern, category=category, weight=weight)
                signals.append(signal)
                total_weight += weight

        # Pontuação léxica normalizada (0-100)
        # Assume que 30+ pontos de peso bruto = score 100
        lexicon_score = min(int(total_weight / 30 * 100), 100)

        # Combina léxico (60%) com IA (40%)
        combined_score = int(lexicon_score * 0.6 + ai_score * 0.4)

        level = self._score_to_level(combined_score)

        explanation = self._build_explanation(level, signals, combined_score)

        logger.info(
            "Risco [{}] | Score: {} | Nível: {} | Sinais: {}",
            extracted.screenshot_id[:8],
            combined_score,
            level.value.upper(),
            len(signals),
        )

        return RiskAssessment(
            screenshot_id=extracted.screenshot_id,
            level=level,
            score=combined_score,
            signals=signals,
            assessed_at=datetime.utcnow(),
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_level(score: int) -> RiskLevel:
        if score >= settings.risk_red_threshold:
            return RiskLevel.RED
        if score >= settings.risk_yellow_threshold:
            return RiskLevel.YELLOW
        return RiskLevel.GREEN

    @staticmethod
    def _build_explanation(level: RiskLevel, signals: list[RiskSignal], score: int) -> str:
        if level == RiskLevel.GREEN:
            return "Nenhum padrão suspeito detectado."

        categories = list({s.category for s in signals})
        cat_str = ", ".join(categories)

        if level == RiskLevel.YELLOW:
            return (
                f"Padrões suspeitos detectados (score {score}/100). "
                f"Categorias: {cat_str}. Monitoramento intensificado."
            )

        return (
            f"🚨 RISCO ALTO (score {score}/100). Categorias: {cat_str}. "
            "Tela bloqueada. Responsável notificado."
        )
