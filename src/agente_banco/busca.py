"""Busca BM25 sobre os documentos de política (RAG pequeno, sem dependências).

São poucos documentos curtos, então cada item de lista vira um trecho. BM25 é o mesmo
algoritmo clássico dos buscadores: pesa palavras raras mais do que palavras comuns.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from importlib import resources

_PARADAS = set("a o e de da do das dos em no na nos nas um uma para por com que se ao à os as é ou não mais".split())


def _tokens(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    # radical simples: os 6 primeiros caracteres ("estornar", "estorno", "estornos" -> "estorn")
    return [t[:6] for t in re.findall(r"[a-z0-9]+", sem_acento) if t not in _PARADAS and len(t) > 1]


@dataclass(frozen=True)
class Trecho:
    documento: str
    texto: str


def carregar_trechos() -> list[Trecho]:
    trechos = []
    pasta = resources.files("agente_banco").joinpath("politicas")
    for arquivo in sorted(pasta.iterdir(), key=lambda p: p.name):
        if not arquivo.name.endswith(".md"):
            continue
        titulo = ""
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.startswith("# "):
                titulo = linha[2:].strip()
            elif linha.startswith("- "):
                trechos.append(Trecho(titulo, linha[2:].strip()))
    return trechos


class BM25:
    def __init__(self, trechos: list[Trecho], k1: float = 1.5, b: float = 0.75) -> None:
        self.trechos = trechos
        self.docs = [_tokens(f"{t.documento} {t.texto}") for t in trechos]
        self.media = sum(map(len, self.docs)) / len(self.docs)
        df = Counter(tok for doc in self.docs for tok in set(doc))
        n = len(self.docs)
        self.idf = {tok: math.log(1 + (n - f + 0.5) / (f + 0.5)) for tok, f in df.items()}
        self.k1, self.b = k1, b

    def buscar(self, pergunta: str, k: int = 3) -> list[tuple[Trecho, float]]:
        consulta = _tokens(pergunta)
        notas = []
        for trecho, doc in zip(self.trechos, self.docs):
            freq = Counter(doc)
            nota = 0.0
            for tok in consulta:
                if tok in freq:
                    f = freq[tok]
                    nota += self.idf[tok] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.media))
            notas.append((trecho, nota))
        return [x for x in sorted(notas, key=lambda x: -x[1])[:k] if x[1] > 0]
