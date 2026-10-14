"""Converter documento em PDF pelo LibreOffice desta máquina, e PDF em
imagens (pdftoppm) ou em Word (LibreOffice ou pdftotext).

Cada conversão roda com um perfil do LibreOffice só dela, numa pasta
temporária: o perfil de quem usa o LibreOffice no dia a dia nunca é tocado, e
duas conversões não disputam a mesma trava. Uma de cada vez, com prazo: o
LibreOffice travado num arquivo estranho não pode segurar o servidor.

Numa caixa, quando o sistema deixa. Um documento pode apontar uma imagem para
um endereço de fora — abrir não pode avisar ninguém — ou para um arquivo desta
máquina, e o LibreOffice embute a imagem no PDF: uma foto da sua pasta
pessoal iria junto no arquivo que você devolve a quem mandou o documento. Com
o `bwrap`, o conversor só enxerga o sistema (só leitura), as suas fontes e a
pasta temporária da conversão; sem rede, sem /home. Sem bwrap, `unshare -rn`
ao menos corta a rede; sem nenhum dos dois, converte e deixa no log.

As macros ficam desligadas no perfil de cada conversão, não só no nível alto
que o LibreOffice já traz.
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

PRAZO = 120
# PDF → imagens: 150 dpi lê bem na tela e imprime sem serrilhado; o limite de
# páginas segura o .zip (uma A4 dá uns 200 KB)
DPI = 150
MAXIMO_DE_IMAGENS = 300
# Uma página de 200 x 200 polegadas a 150 dpi são 30000 x 30000 px, uns 2,7 GB
# de memória: a resolução desce até a maior página caber em PIXELS_POR_PAGINA
# (uma A0 a 150 dpi tem 70 milhões) e o documento todo em PIXELS_NO_TOTAL.
# Abaixo de DPI_MINIMO a imagem não se lê, e aí é recusa
PIXELS_POR_PAGINA = 50_000_000
PIXELS_NO_TOTAL = 1_500_000_000
DPI_MINIMO = 36

# a extensão diz o filtro ao LibreOffice; o conteúdo tem de ser da mesma família
ZIP, OLE = b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
FAMILIAS = {
    **dict.fromkeys(("docx", "xlsx", "pptx", "odt", "ods", "odp"), "zip"),
    **dict.fromkeys(("doc", "xls", "ppt"), "ole"),
    "rtf": "rtf",
    "txt": "texto",
}
DOCUMENTOS = frozenset(FAMILIAS)

_uma_por_vez = threading.Lock()


class ConversaoFalhou(ValueError):
    """O arquivo não é o que diz ser, ou o LibreOffice não deu conta dele."""


def extensao(nome: str) -> str:
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


def confere(caminho: Path, nome: str) -> str:
    """A extensão de `nome`, se o conteúdo de `caminho` for da família dela."""
    ext = extensao(nome)
    if ext not in DOCUMENTOS:
        raise ConversaoFalhou(f"{nome}: não sei converter .{ext or '?'}")
    with caminho.open("rb") as f:
        inicio = f.read(8192)
    familia = FAMILIAS[ext]
    certo = {
        "zip": inicio.startswith(ZIP),
        "ole": inicio.startswith(OLE),
        "rtf": inicio.lstrip().startswith(b"{\\rtf"),
        "texto": b"\x00" not in inicio,
    }[familia]
    if not certo:
        raise ConversaoFalhou(f"{nome} não é o que a extensão diz")
    return ext


# fontes não são segredo e mudam como o documento sai: o conversor vê as suas
FONTES_DO_USUARIO = ("~/.fonts", "~/.local/share/fonts")


def _caixa(pasta: Path) -> list[str]:
    """O bwrap que só deixa ver o sistema, as fontes e `pasta`."""
    comando = [shutil.which("bwrap") or "bwrap", "--unshare-all", "--die-with-parent",
               "--new-session",
               "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    # o cache de fontes do sistema: sem ele cada conversão reconstrói o cache
    # e leva o dobro do tempo
    for fonte in (*FONTES_DO_USUARIO, "/var/cache/fontconfig"):
        caminho = Path(fonte).expanduser()
        if caminho.is_dir():
            comando += ["--ro-bind", str(caminho), str(caminho)]
    return [*comando, "--bind", str(pasta), str(pasta), "--chdir", str(pasta)]


@functools.cache
def _isolamento() -> str:
    """'bwrap', 'unshare' ou '' — o mais fechado que esta máquina permite."""
    if shutil.which("bwrap"):
        teste = subprocess.run([*_caixa(Path("/usr")), "true"], capture_output=True, check=False)
        if teste.returncode == 0:
            return "bwrap"
    unshare = shutil.which("unshare")
    if unshare and subprocess.run([unshare, "-rn", "true"], capture_output=True,
                                  check=False).returncode == 0:
        log.warning("bwrap indisponível: o conversor roda sem rede, mas vê os seus arquivos")
        return "unshare"
    log.warning("bwrap e unshare indisponíveis: o conversor roda sem isolamento nenhum")
    return ""


def _prefixo(pasta: Path) -> list[str]:
    modo = _isolamento()
    if modo == "bwrap":
        return _caixa(pasta)
    if modo == "unshare":
        return [shutil.which("unshare") or "unshare", "-rn"]
    return []


# o perfil de cada conversão nasce com as macros desligadas de vez
MACROS_DESLIGADAS = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


def para_pdf(entrada: Path, nome: str, saida: Path) -> Path:
    """Converte `entrada` (que se chama `nome` para quem mandou) e devolve o
    PDF dentro da pasta `saida`."""
    soffice = shutil.which("soffice")
    if not soffice:
        raise ConversaoFalhou("o LibreOffice não está instalado nesta máquina")
    ext = confere(entrada, nome)
    # o LibreOffice escolhe o filtro pela extensão do arquivo em disco
    arquivo = entrada.with_suffix("." + ext)
    entrada.rename(arquivo)
    return _libreoffice(soffice, arquivo, "pdf", "pdf", nome, saida)


def _libreoffice(soffice: str, arquivo: Path, formato: str, ext: str, nome: str, saida: Path,
                 filtro: str | None = None) -> Path:
    """`arquivo` convertido para `formato` em `saida`, com perfil próprio."""
    perfil = arquivo.parent / f"perfil-{arquivo.stem}"
    (perfil / "user").mkdir(parents=True, exist_ok=True)
    (perfil / "user" / "registrymodifications.xcu").write_text(MACROS_DESLIGADAS)
    saida.mkdir(parents=True, exist_ok=True)
    comando = [soffice, "--headless", "--norestore", "--nolockcheck",
               "--nodefault", f"-env:UserInstallation={perfil.as_uri()}",
               *([f"--infilter={filtro}"] if filtro else []),
               "--convert-to", formato, "--outdir", str(saida), str(arquivo)]
    ok = _rodar(comando, nome, arquivo.parent, {"HOME": str(perfil)})
    resultado = saida / f"{arquivo.stem}.{ext}"
    if not ok or not resultado.is_file() or not resultado.stat().st_size:
        raise ConversaoFalhou(f"o LibreOffice não conseguiu converter {nome}")
    return resultado


def _rodar(comando: list[str], nome: str, pasta: Path, ambiente: dict | None = None) -> bool:
    """Roda na caixa que só vê `pasta` (quando dá), um de cada vez e com
    prazo. Devolve se terminou bem; o motivo da falha vai para o log, não
    para a tela."""
    with _uma_por_vez:
        # sessão própria: no prazo estourado morre o grupo inteiro, não só o
        # lançador (o soffice.bin de verdade é filho dele)
        processo = subprocess.Popen([*_prefixo(pasta), *comando], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, start_new_session=True,
                                    env={**os.environ, **(ambiente or {})})
        try:
            _, erro = processo.communicate(timeout=PRAZO)
        except subprocess.TimeoutExpired:
            os.killpg(processo.pid, signal.SIGKILL)
            processo.wait()
            raise ConversaoFalhou(f"{nome} demorou mais de {PRAZO} s para converter") from None
    if processo.returncode != 0:
        # sem o nome do arquivo: o log do sistema guarda por semanas, e nome
        # de documento pode ser sensível ("exame", "processo"…)
        log.info("conversão falhou (%s): %s", Path(comando[0]).name,
                 erro.decode(errors="replace")[-500:])
    return processo.returncode == 0


def resolucao(paginas, nome: str) -> int:
    """O dpi para desenhar `paginas` (do pypdf) sem estourar a memória."""
    areas = []
    for pagina in paginas:
        caixa = pagina.cropbox  # o pdftoppm desenha a cropbox
        unidade = float(pagina.user_unit or 1)
        areas.append(abs(float(caixa.width) * float(caixa.height)) * unidade ** 2 / 72 ** 2)
    maior, total = max(areas, default=0), sum(areas)
    dpi = float(DPI)
    if maior:
        dpi = min(dpi, (PIXELS_POR_PAGINA / maior) ** 0.5, (PIXELS_NO_TOTAL / total) ** 0.5)
    if dpi < DPI_MINIMO:
        raise ConversaoFalhou(f"as páginas de {nome} são grandes demais para virar imagem")
    return int(dpi)


def para_imagens(entrada: Path, nome: str, saida: Path) -> list[Path]:
    """Cada página de `entrada` como PNG em `saida`, na ordem das páginas."""
    from aide.arquivos import pdf

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise ConversaoFalhou("o pdftoppm (poppler-utils) não está instalado nesta máquina")
    leitor = pdf.abrir(entrada, nome)
    if len(leitor.pages) > MAXIMO_DE_IMAGENS:
        raise ConversaoFalhou(f"{nome} tem mais de {MAXIMO_DE_IMAGENS} páginas")
    dpi = resolucao(leitor.pages, nome)
    saida.mkdir(parents=True, exist_ok=True)
    if not _rodar([pdftoppm, "-png", "-r", str(dpi), str(entrada), str(saida / "p")], nome,
                  entrada.parent):
        raise ConversaoFalhou(f"não deu para desenhar as páginas de {nome}")
    # p-1.png … ou p-01.png …: o pdftoppm completa com zeros pelo total
    imagens = sorted(saida.glob("p-*.png"), key=lambda c: int(c.stem.rsplit("-", 1)[1]))
    if not imagens:
        raise ConversaoFalhou(f"não deu para desenhar as páginas de {nome}")
    return imagens


WORD = "docx:MS Word 2007 XML"
MODOS_WORD = ("aparencia", "texto")


def para_word(entrada: Path, nome: str, saida: Path, modo: str = "aparencia") -> Path:
    """O PDF como .docx. Dois jeitos, porque nenhum serve para tudo:

    - "aparencia": o LibreOffice importa o PDF como desenho; fica igual ao
      original, mas cada linha é uma caixa de texto — bom para retocar.
    - "texto": só o texto, corrido, pelo pdftotext; perde imagens e
      diagramação, mas edita como um documento qualquer.

    Nenhum dos dois lê PDF escaneado: ali o texto é foto."""
    from aide.arquivos import pdf

    if modo not in MODOS_WORD:
        raise ConversaoFalhou(f"modo desconhecido: {modo}")
    soffice = shutil.which("soffice")
    if not soffice:
        raise ConversaoFalhou("o LibreOffice não está instalado nesta máquina")
    pdf.abrir(entrada, nome)
    if modo == "aparencia":
        arquivo = entrada.with_suffix(".pdf")
        entrada.rename(arquivo)
        return _libreoffice(soffice, arquivo, WORD, "docx", nome, saida, "writer_pdf_import")

    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise ConversaoFalhou("o pdftotext (poppler-utils) não está instalado nesta máquina")
    texto = entrada.with_suffix(".txt")
    if (not _rodar([pdftotext, "-enc", "UTF-8", str(entrada), str(texto)], nome, entrada.parent)
            or not texto.is_file()):
        raise ConversaoFalhou(f"não deu para tirar o texto de {nome}")
    conteudo = texto.read_text(encoding="utf-8", errors="replace")
    if not conteudo.strip():
        raise ConversaoFalhou(f"{nome} não tem texto para tirar: parece ser imagem escaneada")
    # o \f que separa as páginas vira linha em branco, não um caractere estranho
    texto.write_text(conteudo.replace("\f", "\n\n"), encoding="utf-8")
    return _libreoffice(soffice, texto, WORD, "docx", nome, saida, "Text (encoded):UTF8")
