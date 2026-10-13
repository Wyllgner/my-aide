"""Converter documento em PDF pelo LibreOffice desta máquina.

Cada conversão roda com um perfil do LibreOffice só dela, numa pasta
temporária: o perfil de quem usa o LibreOffice no dia a dia nunca é tocado, e
duas conversões não disputam a mesma trava. Uma de cada vez, com prazo: o
LibreOffice travado num arquivo estranho não pode segurar o servidor.

Sem rede, quando o sistema deixa (`unshare -rn`): um .docx pode apontar uma
imagem para um endereço de fora, e abrir o documento não pode avisar ninguém
que ele foi aberto. Sem namespaces de usuário, converte assim mesmo e deixa
no log que foi sem isolamento.
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


@functools.cache
def _isolamento() -> tuple[str, ...]:
    unshare = shutil.which("unshare")
    if unshare and subprocess.run([unshare, "-rn", "true"], capture_output=True, check=False).returncode == 0:
        return (unshare, "-rn")
    log.warning("unshare -rn indisponível: o LibreOffice converte com acesso à rede")
    return ()


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
    perfil = entrada.parent / f"perfil-{entrada.stem}"
    saida.mkdir(exist_ok=True)
    comando = [*_isolamento(), soffice, "--headless", "--norestore", "--nolockcheck",
               "--nodefault", f"-env:UserInstallation={perfil.as_uri()}",
               "--convert-to", "pdf", "--outdir", str(saida), str(arquivo)]
    with _uma_por_vez:
        # sessão própria: no prazo estourado morre o grupo inteiro, não só o
        # lançador (o soffice.bin de verdade é filho dele)
        processo = subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    start_new_session=True,
                                    env={**os.environ, "HOME": str(perfil)})
        try:
            _, erro = processo.communicate(timeout=PRAZO)
        except subprocess.TimeoutExpired:
            os.killpg(processo.pid, signal.SIGKILL)
            processo.wait()
            raise ConversaoFalhou(f"{nome} demorou mais de {PRAZO} s para converter") from None
    resultado = saida / (arquivo.stem + ".pdf")
    if processo.returncode != 0 or not resultado.is_file() or not resultado.stat().st_size:
        log.info("conversão de %s falhou: %s", nome, erro.decode(errors="replace")[-500:])
        raise ConversaoFalhou(f"o LibreOffice não conseguiu converter {nome}")
    return resultado
