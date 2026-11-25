import pytest

from agente_banco.avaliacao import carregar_cenarios
from agente_banco.cli import main


@pytest.mark.parametrize("conteudo", ["", "# só comentário\n", "chave: valor\n"])
def test_yaml_de_cenarios_vazio_ou_que_nao_e_lista_e_rejeitado(tmp_path, conteudo):
    arquivo = tmp_path / "cenarios.yaml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match="vazio ou não é uma lista"):
        carregar_cenarios(arquivo)


def test_cli_cenarios_vazios_devolve_2_com_mensagem_clara(tmp_path, capsys):
    arquivo = tmp_path / "vazio.yaml"
    arquivo.write_text("", encoding="utf-8")
    assert main(["avaliar", "--saida", str(tmp_path / "x.json"), "--cenarios", str(arquivo)]) == 2
    erro = capsys.readouterr().err
    assert "vazio ou não é uma lista" in erro and "NoneType" not in erro
