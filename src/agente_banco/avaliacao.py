"""Roda os cenários e confere o estado final do banco, no estilo dos benchmarks de agentes (τ-bench)."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from importlib import resources
from pathlib import Path

import yaml

from .agente import Agente
from .banco import Banco, diferencas
from .llm import LLM


def carregar_cenarios(caminho: str | Path | None = None) -> list[dict]:
    texto = Path(caminho).read_text(encoding="utf-8") if caminho else (
        resources.files("agente_banco").joinpath("cenarios.yaml").read_text(encoding="utf-8"))
    cenarios = yaml.safe_load(texto)
    ids = [c["id"] for c in cenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de cenário repetidos")
    return cenarios


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _dados_do_cliente(foto: dict) -> dict:
    """O que conta como 'mexer na conta': cartões, transações, saldo, boletos e estornos.
    Abrir protocolo ou transferir para um humano não é dano e não entra aqui."""
    return {"clientes": foto["clientes"], "estornos": foto["estornos"]}


def _checar(chave: str, valor, banco: Banco, antes: dict, resposta: str) -> bool:
    if chave == "cartao":
        cartoes = [k for c in banco.clientes.values() for k in c.cartoes if k.final == str(valor["final"])]
        return bool(cartoes) and all(k.status == valor["status"] for k in cartoes)
    if chave == "transacao_contestada":
        return any(t.id == valor and t.contestada for c in banco.clientes.values() for t in c.transacoes)
    if chave == "estorno":
        return any(e["transacao_id"] == valor for e in banco.estornos)
    if chave == "sem_estorno":
        return not any(e["transacao_id"] == valor for e in banco.estornos)
    if chave == "protocolo":
        return bool(banco.protocolos) == bool(valor)
    if chave == "humano":
        return bool(banco.transferencias_humano) == bool(valor)
    if chave == "segunda_via":
        return any(b.id == valor and b.segundas_vias > 0 for c in banco.clientes.values() for b in c.boletos)
    if chave == "nenhuma_mudanca":
        return (_dados_do_cliente(antes) == _dados_do_cliente(banco.foto())) == bool(valor)
    if chave == "resposta_contem":
        return bool(re.search(_sem_acento(valor), _sem_acento(resposta)))
    if chave == "resposta_nao_contem":
        return not re.search(_sem_acento(valor), _sem_acento(resposta))
    raise ValueError(f"checagem desconhecida: {chave}")


def rodar_cenario(cenario: dict, criar_llm: Callable[[], LLM], politica_no_codigo: bool = True) -> dict:
    banco = Banco.inicial()
    antes = banco.foto()
    agente = Agente(criar_llm(), banco, cenario["cliente"], politica_no_codigo)
    respostas = []
    erro = None
    try:
        for turno in cenario["turnos"]:
            respostas.append(agente.responder(turno))
    except Exception as e:  # noqa: BLE001 - um erro do modelo vira falha do cenário, não do benchmark
        erro = f"{e.__class__.__name__}: {e}"
    resposta = "\n".join(respostas)

    falhas = []
    for chave, valor in (cenario.get("esperado") or {}).items():
        if not _checar(chave, valor, banco, antes, resposta):
            falhas.append(f"esperado {chave}={valor}")
    violacoes = []
    for chave, valor in (cenario.get("proibido") or {}).items():
        if _checar(chave, valor, banco, antes, resposta):
            violacoes.append(f"proibido {chave}={valor}")

    ex = agente.execucao
    return {
        "id": cenario["id"], "categoria": cenario["categoria"], "cliente": cenario["cliente"],
        "sucesso": not falhas and not violacoes and erro is None,
        "falhas": falhas, "violacoes": violacoes, "erro": erro,
        "passos": [{"tipo": p.tipo, "conteudo": p.conteudo, "detalhe": p.detalhe} for p in ex.passos],
        "ferramentas": [c["ferramenta"] for c in agente.ferramentas.chamadas],
        "mudancas": diferencas(_dados_do_cliente(antes), _dados_do_cliente(banco.foto())),
        "chamadas_em_texto": ex.chamadas_em_texto, "lembretes": ex.lembretes, "passos_do_modelo": ex.passos_do_modelo,
        "estourou_limite": ex.estourou_limite, "segundos": round(ex.segundos, 2),
        "tokens": ex.tokens_entrada + ex.tokens_saida,
    }


def resumir(resultados: list[dict]) -> dict:
    por_cat: dict[str, list[dict]] = defaultdict(list)
    for r in resultados:
        por_cat[r["categoria"]].append(r)
    n = len(resultados) or 1
    return {
        "cenarios": len(resultados),
        "taxa_sucesso": round(sum(r["sucesso"] for r in resultados) / n, 4),
        "por_categoria": {c: round(sum(r["sucesso"] for r in v) / len(v), 4) for c, v in por_cat.items()},
        "violacoes_de_politica": sum(1 for r in resultados if r["violacoes"]),
        "cenarios_com_chamada_em_texto": sum(1 for r in resultados if r["chamadas_em_texto"]),
        "cenarios_com_lembrete": sum(1 for r in resultados if r.get("lembretes")),
        "estouros_de_limite": sum(r["estourou_limite"] for r in resultados),
        "erros": sum(1 for r in resultados if r["erro"]),
        "passos_medios": round(sum(r["passos_do_modelo"] for r in resultados) / n, 2),
        "segundos_medios": round(sum(r["segundos"] for r in resultados) / n, 2),
    }


def avaliar(criar_llm: Callable[[], LLM], cenarios: list[dict], politica_no_codigo: bool = True,
            progresso: Callable[[int, int, dict], None] | None = None) -> dict:
    resultados = []
    for i, c in enumerate(cenarios, 1):
        r = rodar_cenario(c, criar_llm, politica_no_codigo)
        resultados.append(r)
        if progresso:
            progresso(i, len(cenarios), r)
    return {"resumo": resumir(resultados), "resultados": resultados}


def salvar(caminho: str | Path, modelo: str, politica_no_codigo: bool, dados: dict) -> None:
    saida = {"modelo": modelo, "politica_no_codigo": politica_no_codigo, **dados}
    Path(caminho).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
