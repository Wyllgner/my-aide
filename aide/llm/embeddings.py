"""Embeddings: a metade semântica da busca.

Modelo separado e muito barato ($0.02/1M). Vetores viram BLOB no SQLite —
o volume de um vault pessoal não justifica um banco vetorial.
"""

from __future__ import annotations

import array
import logging
import math

log = logging.getLogger(__name__)

MODELO_PADRAO = "text-embedding-3-small"
# ~8k tokens é o teto do modelo; cortar por caractere é aproximação suficiente
LIMITE_CARACTERES = 24000


def empacotar(vetor: list[float]) -> bytes:
    return array.array("f", vetor).tobytes()


def desempacotar(dados: bytes) -> list[float]:
    vetor = array.array("f")
    vetor.frombytes(dados)
    return list(vetor)


def similaridade(a: list[float], b: list[float]) -> float:
    """Cosseno. Vetores da OpenAI já vêm normalizados, mas não custa garantir."""
    if not a or not b or len(a) != len(b):
        return 0.0
    produto = sum(x * y for x, y in zip(a, b, strict=True))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if not norma_a or not norma_b:
        return 0.0
    return produto / (norma_a * norma_b)


class Embedder:
    def __init__(self, config, usage_sink=None, modelo: str = MODELO_PADRAO):
        from openai import OpenAI

        if not config.llm.api_key:
            raise RuntimeError("OPENAI_API_KEY não definida")
        self.client = OpenAI(api_key=config.llm.api_key, timeout=config.llm.timeout_seconds)
        self.modelo = modelo
        self.usage_sink = usage_sink

    def embed(self, textos: list[str]) -> list[list[float]]:
        """Uma chamada para vários textos — é assim que sai barato."""
        limpos = [t.strip()[:LIMITE_CARACTERES] for t in textos if t and t.strip()]
        if not limpos:
            return []

        resposta = self.client.embeddings.create(model=self.modelo, input=limpos)
        if self.usage_sink:
            self.usage_sink(self.modelo, "embedding",
                            getattr(resposta.usage, "prompt_tokens", 0) or 0, 0, 0)
        return [item.embedding for item in resposta.data]

    def embed_one(self, texto: str) -> list[float] | None:
        vetores = self.embed([texto])
        return vetores[0] if vetores else None
