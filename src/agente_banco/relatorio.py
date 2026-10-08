"""Relatório HTML: taxa de sucesso por modelo/configuração, por categoria, e o rastro de cada cenário."""

from __future__ import annotations

import html
import json
from datetime import date

_CSS = """
:root{--fundo:#f7f7f8;--cartao:#fff;--texto:#1d1d22;--suave:#5c5c66;--borda:#e3e3e8;--bom:#2f9e6e;--ruim:#d9485f;
--medio:#e0a526;--destaque:#4c5fd5;--ferr:#eef1ff}
@media (prefers-color-scheme:dark){:root{--fundo:#141418;--cartao:#1d1d23;--texto:#ececf1;--suave:#a0a0ab;
--borda:#2e2e37;--ferr:#23263a}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1060px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 12px}
.sub{color:var(--suave);margin:0 0 20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.card{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:16px}.rot{color:var(--suave);font-size:13px}
.num{font-size:34px;font-weight:700}.det{font-size:13px;color:var(--suave)}
table{width:100%;border-collapse:collapse;background:var(--cartao);border:1px solid var(--borda);border-radius:12px;overflow:hidden}
th,td{padding:8px 12px;border-bottom:1px solid var(--borda);text-align:left;vertical-align:top}th{font-size:13px;color:var(--suave)}
.ok{color:var(--bom);font-weight:700}.nok{color:var(--ruim);font-weight:700}
details{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:10px 14px;margin:8px 0}
summary{cursor:pointer;font-weight:600}.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;
border:1px solid var(--borda);color:var(--suave);margin-left:6px}.msg{margin:8px 0;padding:8px 12px;border-radius:10px;
border:1px solid var(--borda)}.msg.cliente{background:var(--fundo)}.msg.ferramenta{background:var(--ferr);font:13px/1.45 ui-monospace,Consolas,monospace}
.msg .q{font-size:12px;color:var(--suave);text-transform:uppercase;letter-spacing:.04em}pre{white-space:pre-wrap;margin:0}
.mud{font:13px ui-monospace,Consolas,monospace;color:var(--suave)}footer{margin-top:48px;color:var(--suave);font-size:13px}a{color:var(--destaque)}
"""

_NOMES_CAT = {"consulta": "Consulta", "bloqueio": "Bloqueio de cartão", "estorno_pequeno": "Estorno até R$ 100",
              "estorno_alto": "Estorno acima da alçada", "segunda_via": "Segunda via", "politica": "Regras do banco",
              "seguranca": "Segurança"}


def _rotulo(execucao: dict) -> str:
    return f"{execucao['modelo']} · " + ("política no código" if execucao["politica_no_codigo"] else "política só no prompt")


def _cor(taxa: float) -> str:
    return "var(--bom)" if taxa >= 0.75 else ("var(--medio)" if taxa >= 0.5 else "var(--ruim)")


def _rastro(r: dict) -> str:
    partes = []
    for p in r["passos"]:
        if p["tipo"] == "cliente":
            partes.append(f"<div class='msg cliente'><div class='q'>cliente</div>{html.escape(p['conteudo'])}</div>")
        elif p["tipo"] == "ferramenta":
            det = p.get("detalhe") or {}
            partes.append(f"<div class='msg ferramenta'><div class='q'>ferramenta</div><pre>{html.escape(p['conteudo'])}"
                          f"({html.escape(json.dumps(det.get('argumentos', {}), ensure_ascii=False))})\n→ "
                          f"{html.escape(json.dumps(det.get('resultado', {}), ensure_ascii=False))}</pre></div>")
        else:
            partes.append(f"<div class='msg'><div class='q'>Aura</div>{html.escape(p['conteudo'])}</div>")
    problemas = r["falhas"] + r["violacoes"] + ([r["erro"]] if r["erro"] else [])
    mud = "".join(f"<div>{html.escape(m)}</div>" for m in r["mudancas"]) or "<div>nenhuma</div>"
    estado = "<span class='ok'>sucesso</span>" if r["sucesso"] else "<span class='nok'>falha</span>"
    return (f"<details><summary>{html.escape(r['id'])} {estado}<span class='tag'>{_NOMES_CAT.get(r['categoria'], r['categoria'])}</span>"
            f"<span class='tag'>{r['passos_do_modelo']} passos · {r['segundos']:.0f}s</span></summary>"
            + (f"<p class='nok'>{html.escape('; '.join(problemas))}</p>" if problemas else "")
            + "".join(partes) + f"<div class='mud'><b>mudanças no banco:</b>{mud}</div></details>")


def gerar(execucoes: list[dict]) -> str:
    cards = "".join(
        f"<div class='card'><div class='rot'>{html.escape(_rotulo(e))}</div>"
        f"<div class='num' style='color:{_cor(e['resumo']['taxa_sucesso'])}'>{e['resumo']['taxa_sucesso']:.0%}</div>"
        f"<div class='det'>tarefas resolvidas · {e['resumo']['cenarios']} cenários<br>"
        f"violações de política: {e['resumo']['violacoes_de_politica']} · média de {e['resumo']['passos_medios']} passos, "
        f"{e['resumo']['segundos_medios']:.0f}s por cenário</div></div>" for e in execucoes)
    categorias = list(_NOMES_CAT)
    cab = "".join(f"<th>{html.escape(_rotulo(e))}</th>" for e in execucoes)
    linhas = "".join(
        f"<tr><td>{_NOMES_CAT[c]}</td>" + "".join(
            f"<td style='color:{_cor(e['resumo']['por_categoria'].get(c, 0))};font-weight:600'>"
            f"{e['resumo']['por_categoria'].get(c, 0):.0%}</td>" for e in execucoes) + "</tr>"
        for c in categorias if any(c in e["resumo"]["por_categoria"] for e in execucoes))
    melhor = max(execucoes, key=lambda e: (e["politica_no_codigo"], e["resumo"]["taxa_sucesso"]))
    rastros = "".join(_rastro(r) for r in melhor["resultados"])
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>agente-banco · avaliação</title><style>{_CSS}</style></head>
<body><main><h1>agente-banco · avaliação do agente de atendimento</h1>
<p class="sub">Cada cenário é uma conversa com um cliente do Banco Aurora (fictício). O sucesso é medido pelo <b>estado
final do banco</b> (cartão bloqueado, estorno lançado, protocolo aberto, nenhuma ação indevida), não pelo texto da
resposta. Modelos abertos via Ollama, rodando no GitHub Actions · {date.today():%d/%m/%Y}.</p>
<div class="cards">{cards}</div>
<h2>Por categoria</h2><table><tr><th>Categoria</th>{cab}</tr>{linhas}</table>
<h2>Os cenários, passo a passo</h2>
<p class="sub">Execução: {html.escape(_rotulo(melhor))}. Abra um cenário para ver a conversa, as ferramentas chamadas
e o que mudou no banco.</p>{rastros}
<footer>Gerado pelo <a href="https://github.com/arthurpenedo/agente-banco">agente-banco</a> · banco e clientes fictícios.</footer>
</main></body></html>"""
