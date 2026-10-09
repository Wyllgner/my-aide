"""Os anexos do vault: imagens, áudio, vídeo e PDF que as notas citam.

A lista de tipos é fechada e não tem SVG de propósito. Um SVG pode carregar
script, e servido daqui ele rodaria com o endereço da página — com acesso a
tudo que ela mostra, privado inclusive. HTML, pelo mesmo motivo, também não.

Achar o anexo segue o Obsidian: `![[foto.png]]` é o nome do arquivo em qualquer
pasta, a mesma pasta da nota primeiro; com pasta na frente, vale o caminho.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aide.storage import vault
from aide.storage.links import chave

TIPOS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif", ".bmp": "image/bmp",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".pdf": "application/pdf",
}
EXTENSOES = tuple(TIPOS)
# um vídeo de celular passa disso; o assessor não é lugar de guardar filme
TAMANHO_MAXIMO = 100 * 1024 * 1024


def tipo(caminho: str) -> str:
    return TIPOS[Path(caminho).suffix.lower()]


def resolver(vault_dir: Path, relativo: str) -> Path:
    """Como `vault.resolver`, só que para anexo: mesma recusa de `..`, oculto e
    link simbólico, e só os tipos da lista."""
    return vault.resolver(vault_dir, relativo, extensoes=EXTENSOES)


@dataclass(frozen=True)
class Anexos:
    por_nome: dict[str, tuple[str, ...]]
    por_caminho: dict[str, str]

    def resolver(self, alvo: str, origem: str | None = None) -> str | None:
        # chave() tira ".md"; aqui a extensão faz parte do nome
        procurado = chave(alvo + ".md").strip("/")
        if not procurado:
            return None
        if "/" in procurado:
            if procurado in self.por_caminho:
                return self.por_caminho[procurado]
            sufixo = [c for k, c in self.por_caminho.items() if k.endswith("/" + procurado)]
            return _mais_perto(sufixo, origem)
        return _mais_perto(list(self.por_nome.get(procurado, ())), origem)


def _mais_perto(candidatos: list[str], origem: str | None) -> str | None:
    """Para anexo, perto é estar dentro da pasta da nota, inclusive numa
    subpasta como `anexos/` — onde o Obsidian costuma guardar. Depois, o
    caminho mais curto e a ordem alfabética, para ser sempre o mesmo."""
    if not candidatos:
        return None
    pasta = (origem or "").rpartition("/")[0]
    dentro = pasta + "/" if pasta else ""
    return min(candidatos, key=lambda c: (not c.startswith(dentro), c.count("/"), c.casefold()))


def indice(vault_dir: Path) -> Anexos:
    por_nome: dict[str, list[str]] = {}
    por_caminho: dict[str, str] = {}
    if vault_dir.is_dir():
        for pasta, subpastas, arquivos in os.walk(vault_dir):
            # nada oculto (.trash, .obsidian, .git) e nada atrás de link simbólico
            subpastas[:] = [d for d in subpastas
                            if not d.startswith(".") and not (Path(pasta) / d).is_symlink()]
            for nome in arquivos:
                completo = Path(pasta) / nome
                if (nome.startswith(".") or completo.is_symlink()
                        or completo.suffix.lower() not in TIPOS):
                    continue
                relativo = completo.relative_to(vault_dir).as_posix()
                por_caminho[chave(relativo + ".md")] = relativo
                por_nome.setdefault(chave(nome + ".md"), []).append(relativo)
    return Anexos({k: tuple(v) for k, v in por_nome.items()}, por_caminho)
