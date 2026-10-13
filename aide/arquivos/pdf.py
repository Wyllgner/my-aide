"""Montar um PDF a partir de páginas de outros.

Uma operação só cobre organizar e juntar: a página diz que páginas quer e em
que ordem, cada uma como (arquivo, página). Reordenar é trocar a ordem,
excluir é não pedir, inserir e juntar é pedir de outro arquivo.
"""

from __future__ import annotations

from pathlib import Path

# o PDF pode ter lixo antes da marca; a especificação tolera até 1 KB
CABECA = 1024
MAXIMO_DE_PAGINAS = 5000


class PdfInvalido(ValueError):
    """O arquivo não é PDF, está protegido ou o pedido não fecha com ele."""


def parece_pdf(inicio: bytes) -> bool:
    return b"%PDF-" in inicio[:CABECA]


def _abrir(caminho: Path, nome: str):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    with caminho.open("rb") as f:
        if not parece_pdf(f.read(CABECA)):
            raise PdfInvalido(f"{nome} não é um PDF")
    try:
        leitor = PdfReader(caminho)
        if leitor.is_encrypted:
            raise PdfInvalido(f"{nome} está protegido por senha")
        leitor.pages[0]  # o índice de páginas só é lido aqui
    except PdfInvalido:
        raise
    except (PdfReadError, IndexError, ValueError, KeyError, TypeError) as erro:
        raise PdfInvalido(f"{nome} está corrompido ou vazio") from erro
    return leitor


def montar(fontes: list[Path], paginas: list[tuple[int, int]], destino: Path) -> int:
    """Escreve em `destino` as `paginas` pedidas, na ordem. Página contada do
    zero, como o índice do arquivo em `fontes`. Devolve quantas saíram."""
    from pypdf import PdfWriter

    if not paginas:
        raise PdfInvalido("nenhuma página para montar")
    if len(paginas) > MAXIMO_DE_PAGINAS:
        raise PdfInvalido(f"mais de {MAXIMO_DE_PAGINAS} páginas")
    leitores = [_abrir(caminho, f"o arquivo {i + 1}") for i, caminho in enumerate(fontes)]
    escritor = PdfWriter()
    for arquivo, pagina in paginas:
        if not 0 <= arquivo < len(leitores):
            raise PdfInvalido(f"arquivo {arquivo + 1} não foi enviado")
        leitor = leitores[arquivo]
        if not 0 <= pagina < len(leitor.pages):
            raise PdfInvalido(f"o arquivo {arquivo + 1} não tem a página {pagina + 1}")
        escritor.add_page(leitor.pages[pagina])
    with destino.open("wb") as saida:
        escritor.write(saida)
    return len(paginas)
