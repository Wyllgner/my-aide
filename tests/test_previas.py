"""O cache de prévias em PNG dos desenhos (data/previas-desenho)."""

import pytest

from aide.storage import previas
from aide.storage.previas import PreviaInvalida

PNG = previas.PNG + b"resto"
A = "a" * 32
B = "b" * 32


def test_guardar_e_achar_so_para_a_mesma_assinatura(tmp_path):
    previas.guardar(tmp_path, "Projetos/Casa.excalidraw", A, PNG)
    achado = previas.achar(tmp_path, "Projetos/Casa.excalidraw", A)
    assert achado.read_bytes() == PNG
    assert achado.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / previas.PASTA).stat().st_mode & 0o777 == 0o700
    assert previas.achar(tmp_path, "Projetos/Casa.excalidraw", B) is None
    assert previas.achar(tmp_path, "Outro.excalidraw", A) is None


def test_nome_no_cache_nao_mostra_o_nome_do_desenho(tmp_path):
    previas.guardar(tmp_path, "Segredos/Plano de fuga.excalidraw", A, PNG)
    nomes = [p.name for p in (tmp_path / previas.PASTA).iterdir()]
    assert nomes and all("fuga" not in n and "Segredos" not in n for n in nomes)


def test_versao_nova_tira_a_velha(tmp_path):
    previas.guardar(tmp_path, "Casa.excalidraw", A, PNG)
    previas.guardar(tmp_path, "Casa.excalidraw", B, PNG)
    assert previas.achar(tmp_path, "Casa.excalidraw", A) is None
    assert len(list((tmp_path / previas.PASTA).glob("*.png"))) == 1


@pytest.mark.parametrize("conteudo", [b"GIF89a", b"<svg onload=alert(1)>", b""])
def test_so_png(tmp_path, conteudo):
    with pytest.raises(PreviaInvalida):
        previas.guardar(tmp_path, "Casa.excalidraw", A, conteudo)


@pytest.mark.parametrize("assinatura", ["", "../../x", "A" * 32, "a" * 31, "a" * 64])
def test_assinatura_so_hex_de_32(tmp_path, assinatura):
    with pytest.raises(PreviaInvalida):
        previas.guardar(tmp_path, "Casa.excalidraw", assinatura, PNG)


def test_grande_demais(tmp_path, monkeypatch):
    monkeypatch.setattr(previas, "TAMANHO_MAXIMO", 10)
    with pytest.raises(PreviaInvalida, match="grande"):
        previas.guardar(tmp_path, "Casa.excalidraw", A, PNG + b"x" * 20)


def test_limpar_e_podar(tmp_path):
    previas.guardar(tmp_path, "Casa.excalidraw", A, PNG)
    previas.guardar(tmp_path, "Planta.excalidraw", A, PNG)
    previas.guardar(tmp_path, "Velho.excalidraw", A, PNG)
    previas.limpar(tmp_path, "Casa.excalidraw")
    assert previas.achar(tmp_path, "Casa.excalidraw", A) is None
    previas.podar(tmp_path, ["Planta.excalidraw"])
    assert previas.achar(tmp_path, "Planta.excalidraw", A) is not None
    assert previas.achar(tmp_path, "Velho.excalidraw", A) is None


def test_assinatura_do_arquivo_acompanha_a_mudanca(tmp_path):
    import os

    arquivo = tmp_path / "x.excalidraw"
    arquivo.write_text("um")
    primeira = previas.assinatura_do_arquivo(arquivo)
    arquivo.write_text("dois")
    os.utime(arquivo, ns=(1, 1))
    assert previas.assinatura_do_arquivo(arquivo) != primeira
    assert previas.assinatura_do_arquivo(arquivo) == previas.assinatura(b"dois")


def test_previa_de_so_da_versao_atual(tmp_path):
    from aide.storage import desenhos

    dados, cofre = tmp_path / "data", tmp_path / "vault"
    cofre.mkdir()
    arquivo = cofre / "Casa.excalidraw"
    arquivo.write_text(desenhos.vazio())
    assert previas.previa_de(dados, cofre, "Casa.excalidraw") is None
    atual = previas.assinatura_do_arquivo(arquivo)
    previas.guardar(dados, "Casa.excalidraw", atual, PNG)
    assert previas.previa_de(dados, cofre, "Casa.excalidraw") == atual
    assert previas.previa_de(dados, cofre, "../fora.excalidraw") is None
    assert previas.previa_de(dados, cofre, "Nada.excalidraw") is None
