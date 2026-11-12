import json

import pytest

from agente_banco.avaliacao import (
    _checar,
    avaliar,
    carregar_cenarios,
    rodar_cenario,
    salvar,
)
from agente_banco.banco import Banco


def test_ids_repetidos_dao_erro(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("- {id: a, categoria: x, cliente: c1, turnos: [oi]}\n- {id: a, categoria: x, cliente: c1, turnos: [oi]}\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="repetidos"):
        carregar_cenarios(f)


def test_checagem_desconhecida_da_erro():
    b = Banco.inicial()
    with pytest.raises(ValueError, match="desconhecida"):
        _checar("nao_existe", 1, b, b.foto(), "")


def test_checagens_no_estado_inicial():
    b = Banco.inicial()
    antes = b.foto()
    assert not _checar("cartao", {"final": "0000", "status": "bloqueado"}, b, antes, "")
    assert not _checar("transacao_contestada", "t999", b, antes, "")
    assert not _checar("estorno", "t999", b, antes, "")
    assert _checar("sem_estorno", "t999", b, antes, "")
    assert _checar("protocolo", False, b, antes, "")
    assert not _checar("protocolo", True, b, antes, "")
    assert _checar("humano", False, b, antes, "")
    assert not _checar("segunda_via", "b999", b, antes, "")
    assert _checar("nenhuma_mudanca", True, b, antes, "")
    assert _checar("resposta_nao_contem", "senha", b, antes, "Tudo certo")
    assert not _checar("resposta_nao_contem", "senha", b, antes, "Sua SENHA é 123")


def test_erro_do_modelo_vira_falha_do_cenario():
    class Quebrado:
        def __getattr__(self, nome):
            raise RuntimeError("modelo fora do ar")

    cenario = {"id": "x", "categoria": "consulta", "cliente": "c1", "turnos": ["saldo?"], "esperado": {}}
    r = rodar_cenario(cenario, lambda: Quebrado())
    assert not r["sucesso"]
    assert r["erro"].startswith("RuntimeError")


def test_avaliar_chama_progresso_e_salvar_grava_json(tmp_path):
    class Mudo:
        pass

    cenarios = [{"id": "x", "categoria": "consulta", "cliente": "c1", "turnos": [], "esperado": {}}]
    vistos = []
    dados = avaliar(lambda: Mudo(), cenarios, progresso=lambda i, n, r: vistos.append((i, n, r["id"])))
    assert vistos == [(1, 1, "x")]
    assert dados["resumo"]["cenarios"] == 1
    salvar(tmp_path / "s.json", "modelo-x", True, dados)
    lido = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert lido["modelo"] == "modelo-x" and lido["politica_no_codigo"] is True
