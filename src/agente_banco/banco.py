"""O Banco Aurora (fictício): estado em memória que as ferramentas leem e alteram.

Cada cenário de avaliação começa de um banco novo, criado por `Banco.inicial()`, e
termina comparando o estado final com o esperado (cartão bloqueado? estorno lançado?
protocolo aberto?). É isso que torna a avaliação objetiva: não importa se a resposta
"soou bem", importa o que o agente de fato fez.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field


@dataclass
class Cartao:
    id: str
    final: str
    tipo: str  # credito ou debito
    status: str = "ativo"  # ativo, bloqueado


@dataclass
class Transacao:
    id: str
    data: str
    descricao: str
    valor: float
    categoria: str  # compra, tarifa, pix, saque
    contestada: bool = False


@dataclass
class Boleto:
    id: str
    descricao: str
    valor: float
    vencimento: str
    status: str = "aberto"  # aberto, pago
    segundas_vias: int = 0


@dataclass
class Cliente:
    id: str
    nome: str
    saldo: float
    cartoes: list[Cartao]
    transacoes: list[Transacao]
    boletos: list[Boleto]


@dataclass
class Protocolo:
    id: str
    cliente_id: str
    assunto: str
    detalhes: str
    encaminhado_humano: bool


@dataclass
class Banco:
    clientes: dict[str, Cliente]
    protocolos: list[Protocolo] = field(default_factory=list)
    estornos: list[dict] = field(default_factory=list)
    transferencias_humano: list[dict] = field(default_factory=list)

    @classmethod
    def inicial(cls) -> Banco:
        joao = Cliente(
            id="c1", nome="João Pereira", saldo=2315.40,
            cartoes=[Cartao("k1", "8820", "credito"), Cartao("k2", "1934", "debito")],
            transacoes=[
                Transacao("t1", "2026-10-01", "Supermercado Bom Preço", 287.35, "compra"),
                Transacao("t2", "2026-10-02", "Tarifa pacote de serviços", 24.90, "tarifa"),
                Transacao("t3", "2026-10-03", "Streaming Mais", 39.90, "compra"),
                Transacao("t4", "2026-10-03", "Streaming Mais", 39.90, "compra"),  # cobrança duplicada
                Transacao("t5", "2026-10-05", "Eletrônicos Global (internacional)", 1500.00, "compra"),
                Transacao("t6", "2026-10-06", "Tarifa de saque extra", 7.50, "tarifa"),
            ],
            boletos=[
                Boleto("b1", "Fatura cartão de crédito final 8820", 1284.90, "2026-10-15"),
                Boleto("b2", "Seguro residencial", 89.00, "2026-10-20", status="pago"),
            ],
        )
        ana = Cliente(
            id="c2", nome="Ana Lima", saldo=18240.55,
            cartoes=[Cartao("k3", "4417", "credito"), Cartao("k4", "5520", "credito", status="bloqueado")],
            transacoes=[
                Transacao("t7", "2026-10-02", "Farmácia Saúde", 64.20, "compra"),
                Transacao("t8", "2026-10-04", "Tarifa de anuidade", 42.00, "tarifa"),
                Transacao("t9", "2026-10-06", "Pix para Loja Exemplo", 350.00, "pix"),
            ],
            boletos=[Boleto("b3", "Condomínio Jardim", 640.00, "2026-10-20")],
        )
        return cls(clientes={c.id: c for c in (joao, ana)})

    def cliente(self, cliente_id: str) -> Cliente:
        return self.clientes[cliente_id]

    def proximo_protocolo(self) -> str:
        return f"AUR-{2026100 + len(self.protocolos) + 1}"

    def foto(self) -> dict:
        """Cópia serializável do estado, para comparar antes e depois."""
        return copy.deepcopy(asdict(self))


def diferencas(antes: dict, depois: dict, caminho: str = "") -> list[str]:
    """Lista legível do que mudou entre duas fotos do banco (usada no relatório)."""
    mudancas = []
    if isinstance(antes, dict) and isinstance(depois, dict):
        for chave in sorted(set(antes) | set(depois)):
            mudancas += diferencas(antes.get(chave), depois.get(chave), f"{caminho}.{chave}".strip("."))
    elif isinstance(antes, list) and isinstance(depois, list):
        for i in range(max(len(antes), len(depois))):
            a = antes[i] if i < len(antes) else None
            d = depois[i] if i < len(depois) else None
            mudancas += diferencas(a, d, f"{caminho}[{i}]")
    elif antes != depois:
        mudancas.append(f"{caminho}: {antes!r} -> {depois!r}")
    return mudancas
