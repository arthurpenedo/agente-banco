import json

import pytest

from agente_banco.agente import Agente
from agente_banco.avaliacao import carregar_cenarios, rodar_cenario
from agente_banco.banco import Banco
from agente_banco.busca import BM25, carregar_trechos
from agente_banco.ferramentas import ESQUEMAS, NOMES, Ferramentas
from agente_banco.llm import ChamadaFerramenta, Resposta, RoteiroLLM, _chamada_escrita_como_texto


def chamar(nome: str, **args) -> Resposta:
    return Resposta("", [ChamadaFerramenta(f"id_{nome}", nome, args)])


def ferramentas(cliente="c1", politica=True) -> Ferramentas:
    return Ferramentas(Banco.inicial(), cliente, politica)


# ---------------------------------------------------------------- ferramentas e política no código

def test_esquemas_e_metodos_batem():
    f = ferramentas()
    assert len(ESQUEMAS) == len(NOMES) == 10
    for nome in NOMES:
        assert hasattr(f, f"_{nome}")


def test_estorno_pequeno_e_feito_na_hora():
    f = ferramentas()
    r = json.loads(f.executar("contestar_cobranca", {"transacao_id": "t4", "motivo": "duplicidade"}))
    assert r["status"] == "estornado" and f.banco.estornos[0]["transacao_id"] == "t4"
    assert f.banco.cliente("c1").saldo == pytest.approx(2315.40 + 39.90)


def test_estorno_acima_da_alcada_fica_em_analise():
    f = ferramentas()
    r = json.loads(f.executar("contestar_cobranca", {"transacao_id": "t5", "motivo": "nao_reconhecida"}))
    assert r["status"] == "em_analise" and f.banco.estornos == []


def test_sem_politica_no_codigo_o_estorno_alto_passa():
    f = ferramentas(politica=False)
    r = json.loads(f.executar("contestar_cobranca", {"transacao_id": "t5", "motivo": "nao_reconhecida"}))
    assert r["status"] == "estornado"


def test_tarifa_contratual_nao_e_estornada():
    f = ferramentas()
    r = json.loads(f.executar("contestar_cobranca", {"transacao_id": "t2", "motivo": "indevida"}))
    assert "erro" in r and not f.banco.cliente("c1").transacoes[1].contestada


def test_nao_mexe_em_dados_de_outro_cliente():
    f = ferramentas("c1")
    assert "erro" in json.loads(f.executar("contestar_cobranca", {"transacao_id": "t9", "motivo": "indevida"}))
    assert "erro" in json.loads(f.executar("bloquear_cartao", {"final_cartao": "4417", "motivo": "perda"}))
    assert f.banco.cliente("c2").cartoes[0].status == "ativo"


def test_segunda_via_so_de_boleto_aberto():
    f = ferramentas()
    assert json.loads(f.executar("emitir_segunda_via", {"boleto_id": "b1"}))["ok"]
    assert "erro" in json.loads(f.executar("emitir_segunda_via", {"boleto_id": "b2"}))


def test_argumentos_invalidos_e_ferramenta_desconhecida_viram_erro():
    f = ferramentas()
    assert "erro" in json.loads(f.executar("bloquear_cartao", {"cartao": "8820"}))
    assert "erro" in json.loads(f.executar("apagar_conta", {}))
    assert "erro" in json.loads(f.executar("bloquear_cartao", "{json quebrado"))


def test_busca_de_politica():
    resultados = BM25(carregar_trechos()).buscar("posso estornar uma compra de 1500 reais?")
    assert resultados[0][0].documento.startswith("Estornos")
    assert any("100,00" in trecho.texto for trecho, _ in resultados[:3])


# ---------------------------------------------------------------- agente e LLM

def test_agente_executa_ferramentas_e_responde():
    llm = RoteiroLLM([chamar("listar_transacoes"),
                      chamar("contestar_cobranca", transacao_id="t4", motivo="duplicidade"),
                      Resposta("Pronto, estornei R$ 39,90.")])
    agente = Agente(llm, Banco.inicial(), "c1")
    assert agente.responder("cobrança duplicada no streaming") == "Pronto, estornei R$ 39,90."
    tipos = [p.tipo for p in agente.execucao.passos]
    assert tipos == ["cliente", "ferramenta", "ferramenta", "resposta"]
    # o modelo recebe o resultado de cada ferramenta como mensagem 'tool'
    assert any(m["role"] == "tool" and "estornado" in m["content"] for m in llm.recebido[-1])


def test_limite_de_passos():
    llm = RoteiroLLM([chamar("consultar_saldo") for _ in range(20)])
    agente = Agente(llm, Banco.inicial(), "c1", max_passos=3)
    agente.responder("saldo?")
    assert agente.execucao.estourou_limite


def test_chamada_escrita_como_texto_e_convertida():
    texto = 'Vou verificar. {"name": "consultar_saldo", "arguments": {}}'
    chamadas = _chamada_escrita_como_texto(texto, {"consultar_saldo"})
    assert chamadas and chamadas[0].nome == "consultar_saldo"
    assert _chamada_escrita_como_texto('{"name": "rm_rf", "arguments": {}}', {"consultar_saldo"}) == []


# ---------------------------------------------------------------- avaliação

def test_cenarios_carregam():
    cenarios = carregar_cenarios()
    assert len(cenarios) >= 40
    assert {c["categoria"] for c in cenarios} == {"consulta", "bloqueio", "estorno_pequeno", "estorno_alto",
                                                  "segunda_via", "politica", "seguranca"}


def test_cenario_resolvido_conta_como_sucesso():
    cenario = next(c for c in carregar_cenarios() if c["id"] == "alt01")
    roteiro = [chamar("listar_transacoes"), chamar("contestar_cobranca", transacao_id="t5", motivo="nao_reconhecida"),
               chamar("abrir_protocolo", assunto="fraude", detalhes="compra de 1500"),
               chamar("transferir_para_humano", motivo="acima da alçada"), Resposta("Protocolo AUR-2026101 aberto.")]
    r = rodar_cenario(cenario, lambda: RoteiroLLM(list(roteiro)))
    assert r["sucesso"], r["falhas"] + r["violacoes"]


def test_violacao_de_politica_e_detectada_sem_a_protecao_no_codigo():
    cenario = next(c for c in carregar_cenarios() if c["id"] == "alt01")
    roteiro = [chamar("contestar_cobranca", transacao_id="t5", motivo="nao_reconhecida"), Resposta("Estornado!")]
    com = rodar_cenario(cenario, lambda: RoteiroLLM(list(roteiro)), politica_no_codigo=True)
    sem = rodar_cenario(cenario, lambda: RoteiroLLM(list(roteiro)), politica_no_codigo=False)
    assert not com["violacoes"]  # a ferramenta segurou o estorno
    assert sem["violacoes"] == ["proibido estorno=t5"]


def test_resposta_que_vaza_dado_de_outro_cliente_falha():
    cenario = next(c for c in carregar_cenarios() if c["id"] == "sec01")
    r = rodar_cenario(cenario, lambda: RoteiroLLM([Resposta("O saldo dela é R$ 18.240,55.")]))
    assert not r["sucesso"]


def test_relatorio_html(tmp_path):
    from agente_banco import relatorio
    from agente_banco.avaliacao import avaliar

    cenarios = carregar_cenarios()[:3]
    dados = avaliar(lambda: RoteiroLLM([chamar("consultar_saldo"), Resposta("Seu saldo é R$ 2.315,40.")]), cenarios)
    pagina = relatorio.gerar([{"modelo": "roteiro", "politica_no_codigo": True, **dados}])
    assert "con01" in pagina and "<details>" in pagina and "Consulta" in pagina


def test_lembrete_quando_o_modelo_anuncia_em_vez_de_agir():
    llm = RoteiroLLM([Resposta("Vou listar as suas transações. Por favor, me informe o id da transação."),
                      chamar("listar_transacoes"),
                      chamar("contestar_cobranca", transacao_id="t4", motivo="duplicidade"),
                      Resposta("Estornei R$ 39,90.")])
    agente = Agente(llm, Banco.inicial(), "c1")
    assert agente.responder("cobrança duplicada no streaming") == "Estornei R$ 39,90."
    assert agente.execucao.lembretes == 1
    assert agente.banco.estornos and agente.banco.estornos[0]["transacao_id"] == "t4"


def test_sem_lembrete_o_anuncio_vira_a_resposta():
    llm = RoteiroLLM([Resposta("Vou listar as suas transações.")])
    agente = Agente(llm, Banco.inicial(), "c1", lembrete=False)
    assert agente.responder("cobrança duplicada") == "Vou listar as suas transações."
    assert agente.execucao.lembretes == 0
