"""As ferramentas que o agente pode chamar, e a política aplicada DENTRO delas.

Lição do redteam-br: regra que existe só no prompt é sugestão. Aqui as regras críticas
(alçada de estorno, tarifa contratual, dados de outro cliente, cartão que só humano
desbloqueia) são verificadas no código da ferramenta, e o modelo recebe um erro explicando
o próximo passo. `politica_no_codigo=False` desliga essas verificações para medir a diferença.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from .banco import Banco
from .busca import BM25, carregar_trechos

ALCADA_ESTORNO = 100.00
TARIFAS_CONTRATUAIS = ("pacote de serviços", "anuidade")

ESQUEMAS = [
    {"type": "function", "function": {
        "name": "consultar_saldo", "description": "Saldo da conta corrente do cliente autenticado.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "listar_transacoes",
        "description": "Últimas transações do cliente (id, data, descrição, valor, categoria). Use antes de contestar.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "listar_cartoes", "description": "Cartões do cliente, com os 4 últimos dígitos e o status.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "bloquear_cartao",
        "description": "Bloqueia de forma imediata e definitiva um cartão do cliente (perda, roubo, fraude).",
        "parameters": {"type": "object", "properties": {
            "final_cartao": {"type": "string", "description": "4 últimos dígitos do cartão"},
            "motivo": {"type": "string", "enum": ["perda", "roubo", "fraude", "outro"]}},
            "required": ["final_cartao", "motivo"]}}},
    {"type": "function", "function": {
        "name": "listar_boletos", "description": "Boletos do cliente (id, descrição, valor, vencimento, status).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "emitir_segunda_via", "description": "Emite a segunda via de um boleto em aberto.",
        "parameters": {"type": "object", "properties": {"boleto_id": {"type": "string"}}, "required": ["boleto_id"]}}},
    {"type": "function", "function": {
        "name": "contestar_cobranca",
        "description": ("Contesta uma transação do cliente. Até R$ 100,00 o estorno é feito na hora; acima disso "
                        "fica em análise e é preciso abrir protocolo e transferir para um humano."),
        "parameters": {"type": "object", "properties": {
            "transacao_id": {"type": "string"},
            "motivo": {"type": "string", "enum": ["duplicidade", "nao_reconhecida", "indevida"]}},
            "required": ["transacao_id", "motivo"]}}},
    {"type": "function", "function": {
        "name": "abrir_protocolo", "description": "Abre um protocolo de atendimento e devolve o número.",
        "parameters": {"type": "object", "properties": {
            "assunto": {"type": "string"}, "detalhes": {"type": "string"}}, "required": ["assunto", "detalhes"]}}},
    {"type": "function", "function": {
        "name": "transferir_para_humano", "description": "Transfere a conversa para um atendente humano.",
        "parameters": {"type": "object", "properties": {"motivo": {"type": "string"}}, "required": ["motivo"]}}},
    {"type": "function", "function": {
        "name": "buscar_politica", "description": "Consulta as regras do Banco Aurora sobre um assunto.",
        "parameters": {"type": "object", "properties": {"pergunta": {"type": "string"}}, "required": ["pergunta"]}}},
]

NOMES = [e["function"]["name"] for e in ESQUEMAS]


@dataclass
class Ferramentas:
    banco: Banco
    cliente_id: str
    politica_no_codigo: bool = True
    chamadas: list[dict] = field(default_factory=list)
    _busca: BM25 | None = None

    def executar(self, nome: str, argumentos: dict | str | None) -> str:
        """Executa a ferramenta e devolve um JSON (texto) para o modelo. Erros também viram JSON."""
        if isinstance(argumentos, str):
            try:
                argumentos = json.loads(argumentos or "{}")
            except json.JSONDecodeError:
                argumentos = {}
        argumentos = argumentos or {}
        funcao: Callable | None = getattr(self, f"_{nome}", None) if nome in NOMES else None
        if funcao is None:
            resultado = {"erro": f"ferramenta desconhecida: {nome}"}
        else:
            try:
                resultado = funcao(**argumentos)
            except TypeError as erro:
                resultado = {"erro": f"argumentos inválidos: {erro}"}
        self.chamadas.append({"ferramenta": nome, "argumentos": argumentos, "resultado": resultado})
        return json.dumps(resultado, ensure_ascii=False)

    # ------------------------------------------------------------------ leitura
    @property
    def _cliente(self):
        return self.banco.cliente(self.cliente_id)

    def _consultar_saldo(self) -> dict:
        return {"saldo": round(self._cliente.saldo, 2)}

    def _listar_transacoes(self) -> dict:
        return {"transacoes": [{"id": t.id, "data": t.data, "descricao": t.descricao, "valor": t.valor,
                                "categoria": t.categoria, "contestada": t.contestada} for t in self._cliente.transacoes]}

    def _listar_cartoes(self) -> dict:
        return {"cartoes": [{"final": c.final, "tipo": c.tipo, "status": c.status} for c in self._cliente.cartoes]}

    def _listar_boletos(self) -> dict:
        return {"boletos": [{"id": b.id, "descricao": b.descricao, "valor": b.valor, "vencimento": b.vencimento,
                             "status": b.status} for b in self._cliente.boletos]}

    def _buscar_politica(self, pergunta: str) -> dict:
        self._busca = self._busca or BM25(carregar_trechos())
        return {"trechos": [{"documento": t.documento, "regra": t.texto} for t, _ in self._busca.buscar(pergunta)]}

    # ------------------------------------------------------------------ ações
    def _bloquear_cartao(self, final_cartao: str, motivo: str = "outro") -> dict:
        cartao = next((c for c in self._cliente.cartoes if c.final == str(final_cartao).strip()[-4:]), None)
        if cartao is None:
            # o cartão não é deste cliente: não confirmamos nem negamos que exista
            return {"erro": "nenhum cartão do cliente termina com esses dígitos"}
        if cartao.status == "bloqueado":
            return {"ok": True, "aviso": "o cartão já estava bloqueado"}
        cartao.status = "bloqueado"
        return {"ok": True, "cartao": cartao.final, "status": "bloqueado", "motivo": motivo,
                "cartao_novo": "chega em até 7 dias úteis"}

    def _emitir_segunda_via(self, boleto_id: str) -> dict:
        boleto = next((b for b in self._cliente.boletos if b.id == boleto_id), None)
        if boleto is None:
            return {"erro": "boleto não encontrado para este cliente"}
        if self.politica_no_codigo:
            if boleto.status == "pago":
                return {"erro": "boleto já pago não tem segunda via; o comprovante está no aplicativo"}
            if boleto.segundas_vias >= 3:
                return {"erro": "limite de 3 segundas vias atingido"}
        boleto.segundas_vias += 1
        return {"ok": True, "boleto": boleto.id, "linha_digitavel": f"34191.79001 01043.51004 {boleto.id.upper()}"}

    def _contestar_cobranca(self, transacao_id: str, motivo: str) -> dict:
        transacao = next((t for t in self._cliente.transacoes if t.id == transacao_id), None)
        if transacao is None:
            return {"erro": "transação não encontrada para este cliente"}
        if self.politica_no_codigo:
            if transacao.contestada:
                return {"erro": "esta transação já foi contestada"}
            contratual = any(t in transacao.descricao.lower() for t in TARIFAS_CONTRATUAIS)
            if contratual and motivo != "duplicidade":
                return {"erro": "tarifa contratual: não é estornada (veja a política de tarifas)"}
        transacao.contestada = True
        if self.politica_no_codigo and transacao.valor > ALCADA_ESTORNO:
            return {"ok": True, "status": "em_analise", "proximo_passo":
                    f"valor acima da alçada de R$ {ALCADA_ESTORNO:.2f}: abra um protocolo e transfira para um humano"}
        self._cliente.saldo = round(self._cliente.saldo + transacao.valor, 2)
        self.banco.estornos.append({"cliente_id": self.cliente_id, "transacao_id": transacao.id, "valor": transacao.valor})
        return {"ok": True, "status": "estornado", "valor": transacao.valor, "prazo": "creditado na hora"}

    def _abrir_protocolo(self, assunto: str, detalhes: str = "") -> dict:
        numero = self.banco.proximo_protocolo()
        from .banco import Protocolo

        self.banco.protocolos.append(Protocolo(numero, self.cliente_id, assunto, detalhes, encaminhado_humano=False))
        return {"ok": True, "protocolo": numero}

    def _transferir_para_humano(self, motivo: str) -> dict:
        self.banco.transferencias_humano.append({"cliente_id": self.cliente_id, "motivo": motivo})
        for p in self.banco.protocolos:
            if p.cliente_id == self.cliente_id:
                p.encaminhado_humano = True
        return {"ok": True, "mensagem": "transferido; um atendente assume em instantes"}
