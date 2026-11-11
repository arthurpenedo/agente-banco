import httpx
import pytest

from agente_banco import llm
from agente_banco.llm import ClienteOpenAI

FERRAMENTAS = [{"type": "function", "function": {"name": "saldo", "parameters": {}}}]


def _cliente_falso(monkeypatch, respostas):
    """Troca httpx.post por uma fila de respostas (dict = sucesso, Exception = erro)."""
    chamadas = []

    def falso(url, json, headers, timeout):
        chamadas.append((url, json, headers))
        item = respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(200, json=item, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return chamadas


def test_resposta_com_tool_call_e_tokens(monkeypatch):
    dados = {"choices": [{"message": {"content": "", "tool_calls": [
        {"id": "c1", "function": {"name": "saldo", "arguments": '{"conta": "1"}'}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4}}
    chamadas = _cliente_falso(monkeypatch, [dados])
    r = ClienteOpenAI("m", chave="segredo").conversar([{"role": "user", "content": "oi"}], FERRAMENTAS)
    assert r.chamadas[0].nome == "saldo" and r.chamadas[0].argumentos == {"conta": "1"}
    assert (r.tokens_entrada, r.tokens_saida) == (10, 4) and not r.chamada_em_texto
    assert chamadas[0][2] == {"Authorization": "Bearer segredo"}


def test_argumentos_invalidos_viram_dict_vazio(monkeypatch):
    dados = {"choices": [{"message": {"tool_calls": [{"function": {"name": "saldo", "arguments": "{quebrado"}}]}}]}
    _cliente_falso(monkeypatch, [dados])
    r = ClienteOpenAI("m").conversar([], FERRAMENTAS)
    assert r.chamadas[0].argumentos == {} and r.chamadas[0].id.startswith("c_")


def test_chamada_escrita_como_texto(monkeypatch):
    texto = 'Vou consultar: {"name": "saldo", "arguments": {"conta": "9"}}'
    _cliente_falso(monkeypatch, [{"choices": [{"message": {"content": texto}}]}])
    r = ClienteOpenAI("m").conversar([], FERRAMENTAS)
    assert r.chamada_em_texto and r.texto == "" and r.chamadas[0].argumentos == {"conta": "9"}


def test_texto_com_ferramenta_desconhecida_e_ignorado():
    assert llm._chamada_escrita_como_texto('{"name": "apagar", "arguments": {}}', {"saldo"}) == []


def test_tenta_tres_vezes_e_depois_falha(monkeypatch):
    erro = httpx.ConnectError("sem rede")
    _cliente_falso(monkeypatch, [erro, erro, erro])
    with pytest.raises(httpx.ConnectError):
        ClienteOpenAI("m").conversar([], FERRAMENTAS)


def test_recupera_na_segunda_tentativa(monkeypatch):
    ok = {"choices": [{"message": {"content": "olá"}}]}
    _cliente_falso(monkeypatch, [httpx.ConnectError("x"), ok])
    assert ClienteOpenAI("m").conversar([], FERRAMENTAS).texto == "olá"
