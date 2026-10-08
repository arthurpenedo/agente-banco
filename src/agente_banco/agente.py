"""O laço do agente: o modelo decide, as ferramentas executam, até haver uma resposta ao cliente."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .banco import Banco
from .ferramentas import ESQUEMAS, Ferramentas
from .llm import LLM

PROMPT_SISTEMA = """\
Você é a Aura, assistente virtual do Banco Aurora. Responda em português, de forma breve e cordial.
Cliente autenticado nesta conversa: {nome}.

Como trabalhar:
- Use as ferramentas para consultar e agir. Nunca invente saldo, transações, protocolos ou prazos.
- O cliente não conhece ids internos (de transação, boleto ou cartão). NUNCA peça um id ao cliente:
  descubra com listar_transacoes, listar_boletos ou listar_cartoes e siga em frente.
- Não descreva o que vai fazer ("vou consultar...", "vou listar..."): chame a ferramenta. Só responda ao
  cliente depois de agir.
- Antes de contestar uma cobrança, liste as transações para achar o id certo.
- Antes de bloquear um cartão, confirme qual é (pelos 4 últimos dígitos); se o cliente já informou, pode bloquear.
- Em dúvida sobre uma regra, use buscar_politica.
- Estorno acima de R$ 100,00, recomendação de investimento, reclamação formal ou pedido explícito: abra um
  protocolo quando fizer sentido e transfira para um humano.
- Nunca peça senha, CVV ou código de SMS, e nunca fale de dados de outros clientes.
- Ao terminar, diga ao cliente o que foi feito (e o número do protocolo, se houver)."""


LEMBRETE = ("[sistema] Você disse que ia consultar ou pediu um dado interno ao cliente, mas não chamou nenhuma "
            "ferramenta. Chame agora a ferramenta necessária (por exemplo, listar_transacoes ou listar_boletos) e "
            "conclua o pedido do cliente.")

# frases típicas de "anunciar em vez de agir" ou de pedir ao cliente um id que ele não tem
_ANUNCIO_SEM_ACAO = re.compile(
    r"\b(vou|vamos|irei|deixa eu|deixe-me|preciso)\s+(primeiro\s+)?(consultar|listar|verificar|checar|buscar|"
    r"localizar|identificar|do id|de o id|o id|o numero do|o número do)|\b(id|identificador) d[ao] (transa|boleto|cart)"
    r"|informe o id|me (passe|informe|diga) o id|liste os ids?"
    r"|(?:^|\W)(vou|irei) usar a (fun[cç][aã]o|ferramenta)|(?:^|\W)precisamos (primeiro )?(listar|consultar|verificar|buscar)",
    re.IGNORECASE,
)


@dataclass
class Passo:
    tipo: str  # cliente, ferramenta, resposta
    conteudo: str
    detalhe: dict | None = None


@dataclass
class Execucao:
    passos: list[Passo] = field(default_factory=list)
    chamadas_em_texto: int = 0
    lembretes: int = 0
    passos_do_modelo: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    segundos: float = 0.0
    estourou_limite: bool = False

    @property
    def resposta_final(self) -> str:
        return next((p.conteudo for p in reversed(self.passos) if p.tipo == "resposta"), "")


class Agente:
    def __init__(self, llm: LLM, banco: Banco, cliente_id: str, politica_no_codigo: bool = True,
                 max_passos: int = 8, lembrete: bool = True) -> None:
        self.llm = llm
        self.lembrete = lembrete
        self.banco = banco
        self.ferramentas = Ferramentas(banco, cliente_id, politica_no_codigo)
        self.max_passos = max_passos
        nome = banco.cliente(cliente_id).nome
        self.mensagens: list[dict] = [{"role": "system", "content": PROMPT_SISTEMA.format(nome=nome)}]
        self.execucao = Execucao()

    def responder(self, texto_cliente: str) -> str:
        inicio = time.perf_counter()
        self.mensagens.append({"role": "user", "content": texto_cliente})
        self.execucao.passos.append(Passo("cliente", texto_cliente))
        agiu_neste_turno = False
        lembrou = False
        for _ in range(self.max_passos):
            r = self.llm.conversar(self.mensagens, ESQUEMAS)
            self.execucao.passos_do_modelo += 1
            self.execucao.tokens_entrada += r.tokens_entrada
            self.execucao.tokens_saida += r.tokens_saida
            if not r.chamadas and self.lembrete and not agiu_neste_turno and not lembrou \
                    and _ANUNCIO_SEM_ACAO.search(r.texto or ""):
                # o modelo anunciou uma consulta ("vou listar...", "preciso do id...") sem chamar ferramenta:
                # devolvemos uma vez, pedindo a ação em vez da promessa
                lembrou = True
                self.execucao.lembretes += 1
                self.mensagens.append({"role": "assistant", "content": r.texto})
                self.mensagens.append({"role": "user", "content": LEMBRETE})
                continue
            agiu_neste_turno = agiu_neste_turno or bool(r.chamadas)
            if not r.chamadas:
                self.mensagens.append({"role": "assistant", "content": r.texto})
                self.execucao.passos.append(Passo("resposta", r.texto))
                break
            self.execucao.chamadas_em_texto += int(r.chamada_em_texto)
            self.mensagens.append({"role": "assistant", "content": r.texto or "", "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.nome, "arguments": json.dumps(c.argumentos, ensure_ascii=False)}}
                for c in r.chamadas]})
            for c in r.chamadas:
                resultado = self.ferramentas.executar(c.nome, c.argumentos)
                self.mensagens.append({"role": "tool", "tool_call_id": c.id, "content": resultado})
                self.execucao.passos.append(Passo("ferramenta", c.nome, {"argumentos": c.argumentos,
                                                                         "resultado": json.loads(resultado)}))
        else:
            self.execucao.estourou_limite = True
            self.execucao.passos.append(Passo("resposta", "(o agente não chegou a uma resposta no limite de passos)"))
        self.execucao.segundos += time.perf_counter() - inicio
        return self.execucao.resposta_final
