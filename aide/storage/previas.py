"""As prévias em PNG dos desenhos, para `![[Planta.excalidraw]]` numa nota.

Quem desenha é o navegador (o Excalidraw só exporta lá), então a imagem vem
da página depois de salvar. Ela fica num cache fora do vault, em
`data/previas-desenho/`: o vault é o seu caderno, e um PNG por desenho ao lado
de cada arquivo seria sujeira no Obsidian e no git.

Cada prévia leva no nome a assinatura do texto do desenho que ela mostra. Uma
imagem nunca aparece para outra versão: desenho mexido no Obsidian fica "sem
prévia" até ser aberto aqui, em vez de mostrar o desenho velho. E a página não
consegue pendurar uma imagem qualquer num desenho — a assinatura que ela manda
tem de ser a do arquivo que está no disco.

Cache, e não dado seu: não entra na auditoria e pode ser apagado a qualquer
hora; o pior que acontece é a nota mostrar "abrir para gerar a prévia".
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path

PASTA = "previas-desenho"
# um PNG de até 1600 px de lado; com fotos dentro passa de 1 MB, não de 8
TAMANHO_MAXIMO = 8 * 1024 * 1024
ASSINATURA = re.compile(r"[0-9a-f]{32}")
PNG = b"\x89PNG\r\n\x1a\n"

# (caminho absoluto) -> (mtime_ns, tamanho, assinatura): ler 20 MB a cada
# prévia de nota não precisa, o arquivo só muda quando o mtime muda
_CACHE: dict[Path, tuple[int, int, str]] = {}
_TRAVA = threading.Lock()


class PreviaInvalida(ValueError):
    """O que veio não é um PNG que aceitamos guardar."""


def assinatura(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()[:32]


def assinatura_do_arquivo(arquivo: Path) -> str:
    estado = arquivo.stat()
    marca = (estado.st_mtime_ns, estado.st_size)
    with _TRAVA:
        guardada = _CACHE.get(arquivo)
    if guardada and guardada[:2] == marca:
        return guardada[2]
    resultado = assinatura(arquivo.read_bytes())
    with _TRAVA:
        _CACHE[arquivo] = (*marca, resultado)
    return resultado


def _pasta(data_dir: Path) -> Path:
    return Path(data_dir) / PASTA


def _prefixo(caminho: str) -> str:
    # o caminho do desenho vira hash: nome de arquivo sem barra nem acento, e
    # o nome do desenho não fica exposto na listagem da pasta de cache
    return hashlib.sha256(caminho.encode("utf-8")).hexdigest()[:32]


def _arquivo(data_dir: Path, caminho: str, assinatura_: str) -> Path:
    if not ASSINATURA.fullmatch(assinatura_):
        raise PreviaInvalida("assinatura inválida")
    return _pasta(data_dir) / f"{_prefixo(caminho)}-{assinatura_}.png"


def achar(data_dir: Path, caminho: str, assinatura_: str) -> Path | None:
    arquivo = _arquivo(data_dir, caminho, assinatura_)
    return arquivo if arquivo.is_file() and not arquivo.is_symlink() else None


def guardar(data_dir: Path, caminho: str, assinatura_: str, png: bytes) -> Path:
    """Grava de uma vez (arquivo ao lado e troca) e tira as prévias velhas do
    mesmo desenho."""
    if len(png) > TAMANHO_MAXIMO:
        raise PreviaInvalida("prévia grande demais")
    if not png.startswith(PNG):
        raise PreviaInvalida("a prévia tem de ser PNG")
    destino = _arquivo(data_dir, caminho, assinatura_)
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as saida:
            saida.write(png)
        os.chmod(temporario, 0o600)
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    for velha in _pasta(data_dir).glob(f"{_prefixo(caminho)}-*.png"):
        if velha != destino:
            velha.unlink(missing_ok=True)
    return destino


def limpar(data_dir: Path, caminho: str) -> None:
    """O desenho foi apagado ou mudou de lugar: as prévias dele saem."""
    pasta = _pasta(data_dir)
    if pasta.is_dir():
        for velha in pasta.glob(f"{_prefixo(caminho)}-*.png"):
            velha.unlink(missing_ok=True)


def podar(data_dir: Path, vivos: Iterable[str]) -> None:
    """Tira as prévias de desenhos que não existem mais (pasta inteira na
    lixeira, desenho apagado no Obsidian)."""
    pasta = _pasta(data_dir)
    if not pasta.is_dir():
        return
    prefixos = {_prefixo(c) for c in vivos}
    for arquivo in pasta.glob("*.png"):
        if arquivo.name.partition("-")[0] not in prefixos:
            arquivo.unlink(missing_ok=True)
