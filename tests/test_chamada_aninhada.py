from agente_banco.llm import _chamada_escrita_como_texto


def test_argumentos_com_objeto_aninhado_sao_lidos():
    texto = '{"name": "consultar", "arguments": {"n": 2, "filtro": {"cliente": "c1"}}}'
    chamadas = _chamada_escrita_como_texto(texto, {"consultar"})
    assert len(chamadas) == 1
    assert chamadas[0].argumentos == {"n": 2, "filtro": {"cliente": "c1"}}


def test_argumentos_simples_continuam_funcionando():
    texto = 'Vou chamar {"name": "consultar", "arguments": {"cliente": "c1"}} agora'
    chamadas = _chamada_escrita_como_texto(texto, {"consultar"})
    assert [c.argumentos for c in chamadas] == [{"cliente": "c1"}]
