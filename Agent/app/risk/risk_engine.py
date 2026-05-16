"""
Camada 1 – Filtro Rápido de Risco

Analisa o texto extraído via regex/léxico nas 5 categorias de alerta
definidas para detecção de grooming online:

  1. pedido_segredo   – pedir para não contar, "só entre nós", etc.
  2. envio_midia      – solicitar fotos, vídeos, selfies
  3. diferenca_etaria – perguntar idade, comentar ser mais velho/novo
  4. insistencia      – pressão repetida, "vai", "por favor", "só dessa vez"
  5. manipulacao      – ameaças, chantagem, coerção, elogios excessivos

Retorna:
  - suspicious: bool  → True se qualquer sinal for encontrado
  - signals: list     → sinais específicos detectados
  - score: int        → pontuação bruta (0-100) para combinar com Camada 2

Se não houver sinais (suspicious=False), o pipeline para aqui.
A IA (Camada 2) só é chamada quando suspicious=True.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
# Léxico Camada 1 — 5 categorias de alerta
# ---------------------------------------------------------------------------

LAYER1_LEXICON: list[dict] = [

    # ── 1. PEDIDO DE SEGREDO ──────────────────────────────────────────
    {"pattern": r"\b(n[aã]o conta|segredo|s[oó] n[oó]s|entre n[oó]s|n[aã]o fala pra ningu[eé]m)\b",
     "category": "pedido_segredo", "weight": 8},
    {"pattern": r"\b(n[aã]o diz pra|n[aã]o fala pra|mant[eé]m segredo|guarda segredo)\b",
     "category": "pedido_segredo", "weight": 8},
    {"pattern": r"\b(keep (it )?secret|don[''']?t tell|just between us|our secret)\b",
     "category": "pedido_segredo", "weight": 8},

    # ── 2. ENVIO DE MÍDIA ─────────────────────────────────────────────
    {"pattern": r"\b(manda (uma )?foto|me (envia|manda) (foto|pic|imagem|v[ií]deo))\b",
     "category": "envio_midia", "weight": 9},
    {"pattern": r"\b(selfie|nude|pelad[oa]|sem roupa|tira (uma )?foto)\b",
     "category": "envio_midia", "weight": 10},
    {"pattern": r"\b(send (me )?(a )?(pic|photo|picture|video|nude)|show me)\b",
     "category": "envio_midia", "weight": 9},
    {"pattern": r"\b(c[aâ]mera|ativa (a )?cam|liga (a )?webcam|me mostra)\b",
     "category": "envio_midia", "weight": 8},

    # ── 3. DIFERENÇA ETÁRIA ───────────────────────────────────────────
    {"pattern": r"\b(quantos anos (voc[eê] tem|vc tem)|qual (é |e )?sua idade|how old are you)\b",
     "category": "diferenca_etaria", "weight": 6},
    {"pattern": r"\b(sou mais velho|tenho \d{2} anos|eu tenho \d+ e voc[eê])\b",
     "category": "diferenca_etaria", "weight": 7},
    {"pattern": r"\b(menor de idade|[eé] de menor|voc[eê] [eé] novo|you[''']?re young|you[''']?re a kid)\b",
     "category": "diferenca_etaria", "weight": 7},

    # ── 4. INSISTÊNCIA ────────────────────────────────────────────────
    {"pattern": r"\b(s[oó] (dessa|uma) vez|vai l[aá]|vamos l[aá]|pfv|plz|please)\b",
     "category": "insistencia", "weight": 4},
    {"pattern": r"\b(t[eê] imploro|eu preciso|[eé] s[oó] isso|n[aã]o custa nada)\b",
     "category": "insistencia", "weight": 6},
    {"pattern": r"\b(faz isso pra mim|me ajuda nisso|n[aã]o [eé] nada demais)\b",
     "category": "insistencia", "weight": 5},
    {"pattern": r"\b(just (do it|this once|one time)|come on|don[''']?t be shy)\b",
     "category": "insistencia", "weight": 5},

    # ── 5. MANIPULAÇÃO ───────────────────────────────────────────────
    {"pattern": r"\b(te amo|gosto muito de voc[eê]|voc[eê] [eé] especial|minha namorad[oa])\b",
     "category": "manipulacao", "weight": 6},
    {"pattern": r"\b(vou te dar|te pago|te presentei|te d[aã]o (gift|skin|item|v-bucks|robux))\b",
     "category": "manipulacao", "weight": 7},
    {"pattern": r"\b(se n[aã]o (fizer|mandar)|vou contar pra|vou te denunciar|vou postar)\b",
     "category": "manipulacao", "weight": 9},
    {"pattern": r"\b(s[oó] voc[eê] me entende|seus pais n[aã]o entendem|eles n[aã]o precisam saber)\b",
     "category": "manipulacao", "weight": 8},
    {"pattern": r"\b(i love you|you[''']?re special|i[''']?ll give you|i[''']?ll buy you)\b",
     "category": "manipulacao", "weight": 6},
    {"pattern": r"\b(if you don[''']?t|i[''']?ll tell everyone|i[''']?ll post it)\b",
     "category": "manipulacao", "weight": 9},
]

# Pré-compila
_COMPILED_L1: list[tuple[re.Pattern, str, int]] = [
    (re.compile(e["pattern"], re.IGNORECASE | re.DOTALL), e["category"], e["weight"])
    for e in LAYER1_LEXICON
]


# ---------------------------------------------------------------------------
# Resultado da Camada 1
# ---------------------------------------------------------------------------

@dataclass
class Layer1Result:
    suspicious: bool
    signals: list[RiskSignal] = field(default_factory=list)
    raw_score: int = 0
    categories_hit: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Camada 1
# ---------------------------------------------------------------------------

class Layer1Filter:
    """Filtro rápido léxico — Camada 1 do pipeline de detecção."""

    def run(self, text: str) -> Layer1Result:
        if not text.strip():
            return Layer1Result(suspicious=False)

        signals: list[RiskSignal] = []
        total_weight = 0

        for pattern, category, weight in _COMPILED_L1:
            if pattern.search(text):
                signals.append(RiskSignal(
                    keyword=pattern.pattern,
                    category=category,
                    weight=weight,
                ))
                total_weight += weight

        if not signals:
            return Layer1Result(suspicious=False)

        categories_hit = {s.category for s in signals}
        raw_score = min(int(total_weight / 25 * 100), 100)

        logger.info(
            "⚡ Camada 1 — SUSPEITO | Score: {} | Categorias: {}",
            raw_score,
            ", ".join(sorted(categories_hit)),
        )

        return Layer1Result(
            suspicious=True,
            signals=signals,
            raw_score=raw_score,
            categories_hit=categories_hit,
        )


# ---------------------------------------------------------------------------
# Motor de Risco — combina Camada 1 + resultado da IA (Camada 2)
# ---------------------------------------------------------------------------

class RiskEngine:
    """
    Avalia o risco final combinando o score da Camada 1 com o da IA.
    Só deve ser chamado após a Camada 1 retornar suspicious=True.
    """

    _filter = Layer1Filter()

    def run_layer1(self, text: str) -> Layer1Result:
        """Executa apenas a Camada 1. Use para decidir se aciona a IA."""
        return self._filter.run(text)

    def assess(self, extracted: ExtractedText, ai_score: int = 0,
               layer1: Layer1Result | None = None) -> RiskAssessment:
        if layer1 is None:
            layer1 = self._filter.run(extracted.raw_text)

        if not layer1.suspicious and ai_score == 0:
            return RiskAssessment(
                screenshot_id=extracted.screenshot_id,
                level=RiskLevel.GREEN,
                score=0,
                signals=[],
                assessed_at=datetime.utcnow(),
                explanation="Nenhum padrão suspeito detectado.",
            )

        # 60% Camada 1 + 40% IA
        combined_score = int(layer1.raw_score * 0.6 + ai_score * 0.4)
        level = self._score_to_level(combined_score)
        explanation = self._build_explanation(level, layer1, combined_score)

        logger.info(
            "🎯 Risco final [{}] | L1: {} | IA: {} | Combined: {} | {}",
            extracted.screenshot_id[:8],
            layer1.raw_score, ai_score, combined_score,
            level.value.upper(),
        )

        return RiskAssessment(
            screenshot_id=extracted.screenshot_id,
            level=level,
            score=combined_score,
            signals=layer1.signals,
            assessed_at=datetime.utcnow(),
            explanation=explanation,
        )

    @staticmethod
    def _score_to_level(score: int) -> RiskLevel:
        if score >= settings.risk_red_threshold:
            return RiskLevel.RED
        if score >= settings.risk_yellow_threshold:
            return RiskLevel.YELLOW
        return RiskLevel.GREEN

    @staticmethod
    def _build_explanation(level: RiskLevel, layer1: Layer1Result, score: int) -> str:
        cats = ", ".join(sorted(layer1.categories_hit))
        if level == RiskLevel.GREEN:
            return "Nenhum padrão suspeito confirmado."
        if level == RiskLevel.YELLOW:
            return (f"⚠️ Padrões suspeitos detectados (score {score}/100). "
                    f"Categorias: {cats}.")
        return (f"🚨 RISCO ALTO (score {score}/100). "
                f"Categorias: {cats}. Tela bloqueada.")
