"""Montar um PDF a partir de páginas de outros.

Uma operação só cobre organizar e juntar: a página diz que páginas quer e em
que ordem, cada uma como (arquivo, página). Reordenar é trocar a ordem,
excluir é não pedir, inserir e juntar é pedir de outro arquivo.

Uma fonte também pode ser imagem (.jpg, .png): ela é uma página só, do
tamanho da página que vem antes dela no resultado — inserida no meio de um
contrato em A4, vira uma folha A4 com a foto centralizada.
"""

from __future__ import annotations

import io
from pathlib import Path

# o PDF pode ter lixo antes da marca; a especificação tolera até 1 KB
CABECA = 1024
MAXIMO_DE_PAGINAS = 5000
# foto de celular tem uns 12 milhões de pixels; acima disto é bomba de
# descompressão, não foto
MAXIMO_DE_PIXELS = 80_000_000
A4 = (595.28, 841.89)
MARGEM = 24


class PdfInvalido(ValueError):
    """O arquivo não é PDF, está protegido ou o pedido não fecha com ele."""


def parece_pdf(inicio: bytes) -> bool:
    return b"%PDF-" in inicio[:CABECA]


def tipo_de(caminho: Path) -> str | None:
    """'pdf', 'imagem' ou None, pelo conteúdo e nunca pelo nome."""
    with caminho.open("rb") as f:
        inicio = f.read(CABECA)
    if inicio.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        return "imagem"
    if parece_pdf(inicio):
        return "pdf"
    return None


def _tamanho(pagina) -> tuple[float, float]:
    """Largura e altura como a página aparece, já com o giro dela."""
    largura, altura = float(pagina.mediabox.width), float(pagina.mediabox.height)
    return (altura, largura) if (pagina.rotation or 0) % 180 else (largura, altura)


def _abrir_imagem(caminho: Path, nome: str):
    """Só JPEG e PNG, e o tamanho conferido pelo cabeçalho antes de
    decodificar. Sem mexer no MAX_IMAGE_PIXELS global nem em filtro de aviso:
    os dois valem para o processo inteiro, e duas montagens rodam juntas."""
    from PIL import Image, ImageOps

    try:
        with Image.open(caminho, formats=["JPEG", "PNG"]) as aberta:
            largura, altura = aberta.size
            if largura * altura > MAXIMO_DE_PIXELS:
                raise PdfInvalido(f"{nome} é grande demais")
            imagem = ImageOps.exif_transpose(aberta)
            imagem.load()
    except PdfInvalido:
        raise
    except Image.DecompressionBombError:
        raise PdfInvalido(f"{nome} é grande demais") from None
    except (OSError, ValueError, SyntaxError) as erro:
        raise PdfInvalido(f"{nome} não é uma imagem que dê para abrir") from erro
    if imagem.mode in ("RGBA", "LA", "PA") or "transparency" in imagem.info:
        # o fundo transparente vira papel branco, não preto
        fundo = Image.new("RGB", imagem.size, "white")
        fundo.paste(imagem, mask=imagem.convert("RGBA").getchannel("A"))
        return fundo
    return imagem.convert("L" if imagem.mode in ("1", "L", "I;16") else "RGB")


def pagina_de_imagem(caminho: Path, nome: str, tamanho: tuple[float, float] | None):
    """Uma página do `tamanho` pedido com a imagem centralizada e inteira.
    Sem tamanho, A4 deitada ou em pé conforme a imagem."""
    from pypdf import PageObject, PdfReader, Transformation

    imagem = _abrir_imagem(caminho, nome)
    bruto = io.BytesIO()
    imagem.save(bruto, "PDF", resolution=72.0, quality=92)
    origem = PdfReader(bruto).pages[0]
    largura_img, altura_img = _tamanho(origem)
    if tamanho is None:
        tamanho = (A4[1], A4[0]) if largura_img > altura_img else A4
    largura, altura = tamanho
    escala = min((largura - 2 * MARGEM) / largura_img, (altura - 2 * MARGEM) / altura_img)
    pagina = PageObject.create_blank_page(width=largura, height=altura)
    pagina.merge_transformed_page(origem, Transformation().scale(escala).translate(
        (largura - largura_img * escala) / 2, (altura - altura_img * escala) / 2))
    return pagina


def abrir(caminho: Path, nome: str):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    with caminho.open("rb") as f:
        if not parece_pdf(f.read(CABECA)):
            raise PdfInvalido(f"{nome} não é um PDF")
    try:
        leitor = PdfReader(caminho)
        # protegido só contra edição (a senha de abertura é vazia) abre em
        # qualquer leitor, e aqui também; com senha de abertura de verdade, não
        if leitor.is_encrypted and not leitor.decrypt(""):
            raise PdfInvalido(f"{nome} está protegido por senha")
        leitor.pages[0]  # o índice de páginas só é lido aqui
    except PdfInvalido:
        raise
    except (PdfReadError, IndexError, ValueError, KeyError, TypeError) as erro:
        raise PdfInvalido(f"{nome} está corrompido ou vazio") from erro
    return leitor


def montar(fontes: list[Path], paginas: list[tuple[int, int]], destino: Path,
           imagem_na_vizinha: bool = True) -> int:
    """Escreve em `destino` as `paginas` pedidas, na ordem. Página contada do
    zero, como o índice do arquivo em `fontes`; imagem tem só a página 0.
    Devolve quantas saíram.

    `imagem_na_vizinha`: a imagem toma o tamanho da página de antes, como
    quem insere uma foto num contrato. Sem isso, cada imagem vira uma A4 na
    orientação dela — um álbum de fotos deitadas e em pé."""
    from pypdf import PdfWriter

    if not paginas:
        raise PdfInvalido("nenhuma página para montar")
    if len(paginas) > MAXIMO_DE_PAGINAS:
        raise PdfInvalido(f"mais de {MAXIMO_DE_PAGINAS} páginas")
    leitores = []
    for i, caminho in enumerate(fontes):
        nome = f"o arquivo {i + 1}"
        tipo = tipo_de(caminho)
        if tipo is None:
            raise PdfInvalido(f"{nome} não é um PDF nem uma imagem .jpg ou .png")
        leitores.append(abrir(caminho, nome) if tipo == "pdf" else None)
    for arquivo, pagina in paginas:
        if not 0 <= arquivo < len(leitores):
            raise PdfInvalido(f"arquivo {arquivo + 1} não foi enviado")
        total = len(leitores[arquivo].pages) if leitores[arquivo] else 1
        if not 0 <= pagina < total:
            raise PdfInvalido(f"o arquivo {arquivo + 1} não tem a página {pagina + 1}")

    # a imagem que abre o resultado toma o tamanho da primeira página de PDF
    primeira_de_pdf = next((_tamanho(leitores[a].pages[p]) for a, p in paginas if leitores[a]), None)
    escritor = PdfWriter()
    for arquivo, pagina in paginas:
        leitor = leitores[arquivo]
        if leitor:
            escritor.add_page(leitor.pages[pagina])
        else:
            vizinha = None
            if imagem_na_vizinha:
                vizinha = _tamanho(escritor.pages[-1]) if escritor.pages else primeira_de_pdf
            escritor.add_page(pagina_de_imagem(fontes[arquivo], f"o arquivo {arquivo + 1}", vizinha))
    with destino.open("wb") as saida:
        escritor.write(saida)
    return len(paginas)
