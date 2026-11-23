from agente_banco.cli import main


def test_ids_inexistentes_devolvem_2_sem_gravar_saida(capsys, tmp_path):
    saida = tmp_path / "x.json"
    assert main(["avaliar", "--saida", str(saida), "--ids", "zzz"]) == 2
    assert "zzz" in capsys.readouterr().err
    assert not saida.exists()


def test_relatorio_com_arquivo_ausente_devolve_2(capsys, tmp_path):
    assert main(["relatorio", str(tmp_path / "nao-existe.json"), "--html", str(tmp_path / "o.html")]) == 2
    assert "não consegui ler" in capsys.readouterr().err


def test_relatorio_com_json_quebrado_devolve_2(capsys, tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{nao é json", encoding="utf-8")
    assert main(["relatorio", str(ruim), "--html", str(tmp_path / "o.html")]) == 2
