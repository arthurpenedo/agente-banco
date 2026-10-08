"""Cliente de chat com tool calling no formato da OpenAI (Ollama, vLLM, OpenAI, Groq...)."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict


@dataclass
class Resposta:
    texto: str
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    chamada_em_texto: bool = False  # o modelo escreveu a chamada como texto, e nós convertemos
    tokens_entrada: int = 0
    tokens_saida: int = 0


class LLM(Protocol):
    nome: str

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta: ...


_JSON_CHAMADA = re.compile(r"\{[^{}]*\"name\"\s*:\s*\"(\w+)\"[^{}]*\"arguments\"\s*:\s*(\{.*?\})\s*\}", re.DOTALL)


def _chamada_escrita_como_texto(texto: str, nomes: set[str]) -> list[ChamadaFerramenta]:
    """Modelos pequenos às vezes devolvem {"name": ..., "arguments": {...}} no texto em vez de tool_calls."""
    chamadas = []
    for m in _JSON_CHAMADA.finditer(texto or ""):
        if m.group(1) in nomes:
            try:
                chamadas.append(ChamadaFerramenta(f"txt_{uuid.uuid4().hex[:8]}", m.group(1), json.loads(m.group(2))))
            except json.JSONDecodeError:
                pass
    return chamadas


@dataclass
class ClienteOpenAI:
    modelo: str
    url_base: str = "http://localhost:11434/v1"
    chave: str | None = None
    timeout: float = 240.0
    seed: int = 42

    @property
    def nome(self) -> str:
        return self.modelo

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta:
        corpo = {"model": self.modelo, "messages": mensagens, "tools": ferramentas, "temperature": 0, "seed": self.seed}
        cabecalhos = {"Authorization": f"Bearer {self.chave}"} if self.chave else {}
        for tentativa in range(3):
            try:
                r = httpx.post(f"{self.url_base}/chat/completions", json=corpo, headers=cabecalhos, timeout=self.timeout)
                r.raise_for_status()
                break
            except httpx.HTTPError:
                if tentativa == 2:
                    raise
                time.sleep(3 * (tentativa + 1))
        dados = r.json()
        msg = dados["choices"][0]["message"]
        uso = dados.get("usage") or {}
        chamadas = []
        for c in msg.get("tool_calls") or []:
            args = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                args = {}
            chamadas.append(ChamadaFerramenta(c.get("id") or f"c_{uuid.uuid4().hex[:8]}", c["function"]["name"], args))
        em_texto = False
        if not chamadas:
            nomes = {f["function"]["name"] for f in ferramentas}
            chamadas = _chamada_escrita_como_texto(msg.get("content") or "", nomes)
            em_texto = bool(chamadas)
        return Resposta(texto="" if em_texto else (msg.get("content") or ""), chamadas=chamadas,
                        chamada_em_texto=em_texto, tokens_entrada=uso.get("prompt_tokens", 0),
                        tokens_saida=uso.get("completion_tokens", 0))


@dataclass
class RoteiroLLM:
    """LLM falso para testes: devolve as respostas de uma lista, em ordem."""

    respostas: list[Resposta]
    nome: str = "roteiro"
    recebido: list[list[dict]] = field(default_factory=list)

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta:
        self.recebido.append(json.loads(json.dumps(mensagens)))
        return self.respostas.pop(0) if self.respostas else Resposta("Posso ajudar em algo mais?")
