"""Linha de comando: avaliar um modelo, gerar o relatório e conversar com o agente."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import relatorio
from .agente import Agente
from .avaliacao import avaliar, carregar_cenarios, salvar
from .banco import Banco
from .llm import ClienteOpenAI


def _avaliar(args: argparse.Namespace) -> int:
    cenarios = carregar_cenarios(args.cenarios)
    if args.ids:
        cenarios = [c for c in cenarios if c["id"] in args.ids]
    politica = not args.politica_so_no_prompt
    print(f"Modelo {args.modelo} · {'política no código' if politica else 'política só no prompt'} · {len(cenarios)} cenários")

    def progresso(i: int, total: int, r: dict) -> None:
        marca = "ok   " if r["sucesso"] else "FALHA"
        motivo = "; ".join(r["falhas"] + r["violacoes"] + ([r["erro"]] if r["erro"] else []))
        print(f"[{i:>2}/{total}] {r['id']:<6} {marca} {r['segundos']:>5.1f}s  {','.join(r['ferramentas'])}  {motivo}", flush=True)

    dados = avaliar(lambda: ClienteOpenAI(args.modelo, args.url), cenarios, politica, progresso)
    salvar(args.saida, args.modelo, politica, dados)
    r = dados["resumo"]
    print(f"\nTarefas resolvidas: {r['taxa_sucesso']:.0%} · violações de política: {r['violacoes_de_politica']}")
    for cat, taxa in r["por_categoria"].items():
        print(f"  {cat:<16} {taxa:.0%}")
    return 0


def _relatorio(args: argparse.Namespace) -> int:
    execucoes = [json.loads(Path(c).read_text(encoding="utf-8")) for c in args.execucoes]
    Path(args.html).parent.mkdir(parents=True, exist_ok=True)
    Path(args.html).write_text(relatorio.gerar(execucoes), encoding="utf-8")
    print(f"Relatório salvo em {args.html}")
    return 0


def _conversar(args: argparse.Namespace) -> int:
    agente = Agente(ClienteOpenAI(args.modelo, args.url), Banco.inicial(), args.cliente)
    print(f"Conversando como {agente.banco.cliente(args.cliente).nome}. Linha vazia para sair.")
    while True:
        try:
            texto = input("você> ").strip()
        except EOFError:
            break
        if not texto:
            break
        inicio = len(agente.ferramentas.chamadas)
        resposta = agente.responder(texto)
        for c in agente.ferramentas.chamadas[inicio:]:
            print(f"   [ferramenta] {c['ferramenta']}({json.dumps(c['argumentos'], ensure_ascii=False)})")
        print(f"aura> {resposta}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agente-banco", description="Agente de atendimento bancário com ferramentas.")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("avaliar", help="roda os cenários contra um modelo")
    p.add_argument("--modelo", default="qwen2.5:3b")
    p.add_argument("--url", default="http://localhost:11434/v1", help="URL base compatível com a OpenAI")
    p.add_argument("--saida", required=True)
    p.add_argument("--politica-so-no-prompt", action="store_true", help="desliga as verificações nas ferramentas")
    p.add_argument("--ids", nargs="*", help="só estes cenários")
    p.add_argument("--cenarios", help="YAML de cenários (padrão: o embutido)")
    p.set_defaults(func=_avaliar)

    p = sub.add_parser("relatorio", help="gera o relatório HTML a partir de uma ou mais avaliações")
    p.add_argument("execucoes", nargs="+")
    p.add_argument("--html", required=True)
    p.set_defaults(func=_relatorio)

    p = sub.add_parser("conversar", help="conversa com o agente no terminal")
    p.add_argument("--modelo", default="qwen2.5:3b")
    p.add_argument("--url", default="http://localhost:11434/v1")
    p.add_argument("--cliente", default="c1", choices=["c1", "c2"])
    p.set_defaults(func=_conversar)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
