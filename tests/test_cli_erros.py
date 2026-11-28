from agente_banco.cli import main


def test_ids_inexistentes_devolvem_2_sem_gravar_saida(capsys, tmp_path):
    saida = tmp_path / "x.json"
    assert main(["avaliar", "--saida", str(saida), "--ids", "zzz"]) == 2
    assert "zzz" in capsys.readouterr().err
    assert not saida.exists()


def test_cenarios_ausentes_e_ids_vazio_devolvem_2(capsys, tmp_path):
    saida = tmp_path / "x.json"
    assert main(["avaliar", "--saida", str(saida), "--cenarios", str(tmp_path / "nao.yaml")]) == 2
    assert "cenários" in capsys.readouterr().err
    assert main(["avaliar", "--saida", str(saida), "--ids"]) == 2
    assert "--ids" in capsys.readouterr().err
    assert not saida.exists()


def test_relatorio_com_arquivo_ausente_devolve_2(capsys, tmp_path):
    assert main(["relatorio", str(tmp_path / "nao-existe.json"), "--html", str(tmp_path / "o.html")]) == 2
    assert "não consegui ler" in capsys.readouterr().err


def test_relatorio_com_json_quebrado_devolve_2(capsys, tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{nao é json", encoding="utf-8")
    assert main(["relatorio", str(ruim), "--html", str(tmp_path / "o.html")]) == 2


def test_relatorio_com_json_valido_mas_sem_resumo_ou_aninhado_demais_devolve_2(capsys, tmp_path):
    for nome, conteudo, trecho in (("vazio", "{}", "não é uma avaliação salva"),
                                   ("lista", "[1]", "não é uma avaliação salva"),
                                   ("fundo", "[" * 5000, "não consegui ler")):
        arq = tmp_path / f"{nome}.json"
        arq.write_text(conteudo, encoding="utf-8")
        assert main(["relatorio", str(arq), "--html", str(tmp_path / "o.html")]) == 2
        assert trecho in capsys.readouterr().err
    assert not (tmp_path / "o.html").exists()


def test_saida_e_html_apontando_para_pasta_devolvem_2(capsys, tmp_path):
    assert main(["avaliar", "--saida", str(tmp_path)]) == 2
    assert "--saida" in capsys.readouterr().err
    exec_ok = tmp_path / "e.json"
    exec_ok.write_text("{}", encoding="utf-8")
    assert main(["relatorio", str(exec_ok), "--html", str(tmp_path)]) == 2
    assert "--html" in capsys.readouterr().err


def test_saida_e_html_dentro_de_arquivo_devolvem_2_antes_de_rodar_o_modelo(capsys, tmp_path):
    arq = tmp_path / "arq.txt"
    arq.write_text("x", encoding="utf-8")
    assert main(["avaliar", "--saida", str(arq / "x.json")]) == 2
    assert "passa por um arquivo" in capsys.readouterr().err
    exec_ok = tmp_path / "e.json"
    exec_ok.write_text("{}", encoding="utf-8")
    assert main(["relatorio", str(exec_ok), "--html", str(arq / "o.html")]) == 2
    assert "passa por um arquivo" in capsys.readouterr().err
