"""Os anexos do vault: imagens, áudio, vídeo e PDF que as notas citam.

A lista de tipos é fechada e não tem SVG de propósito. Um SVG pode carregar
script, e servido daqui ele rodaria com o endereço da página — com acesso a
tudo que ela mostra, privado inclusive. HTML, pelo mesmo motivo, também não.

Achar o anexo segue o Obsidian: `![[foto.png]]` é o nome do arquivo em qualquer
pasta, a mesma pasta da nota primeiro; com pasta na frente, vale o caminho.
"""

from __future__ import annotations

import json
import os
import posixpath
from dataclasses import dataclass
from datetime import datetime
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


# a pasta onde cai o anexo colado ou arrastado, quando o vault não diz outra
# no .obsidian/app.json: uma "anexos" ao lado da nota, como "./anexos" no Obsidian
PASTA_PADRAO = "./anexos"


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


# ---------- receber um anexo pela página ----------


def pasta_para(vault_dir: Path, nota: str) -> str:
    """A pasta (no vault, "" é a raiz) onde guardar um anexo da nota `nota`.

    Segue a "pasta de anexos" do Obsidian (`attachmentFolderPath` em
    `.obsidian/app.json`): "/" é a raiz, "./" a pasta da nota, "./x" uma
    subpasta dela e "x" uma pasta fixa do vault. Sem a configuração, vale
    `PASTA_PADRAO`.
    """
    pedido = PASTA_PADRAO
    try:
        configurado = json.loads((vault_dir / ".obsidian" / "app.json").read_text())
        if isinstance(configurado.get("attachmentFolderPath"), str):
            pedido = configurado["attachmentFolderPath"] or "/"
    except (OSError, ValueError, AttributeError):
        pass
    da_nota = nota.rpartition("/")[0]
    if pedido.startswith("./") or pedido == ".":
        pedido = posixpath.join(da_nota, pedido[2:])
    pasta = posixpath.normpath(pedido).strip("/")
    return "" if pasta == "." else pasta


def nome_para(nome: str, tipo_mime: str, agora: datetime) -> str:
    """O nome do arquivo: o original, limpo, ou "Captura <data hora>" para o
    que veio da área de transferência (sem nome). A extensão tem de ser da
    lista; senão ValueError — SVG e HTML continuam de fora."""
    base, ponto, extensao = nome.rpartition(".")
    extensao = f".{extensao.lower()}" if ponto else ""
    if extensao not in TIPOS:
        por_tipo = [e for e, t in TIPOS.items() if t == tipo_mime.split(";")[0].strip().lower()]
        if not por_tipo:
            raise ValueError("tipo de arquivo não aceito")
        extensao, base = por_tipo[0], (nome if not ponto else base)
    if extensao == ".jpeg":
        extensao = ".jpg"
    base = vault.nome_de_arquivo(base) if base.strip() else ""
    if not base or base == "Sem título":
        base = f"Captura {agora.strftime('%Y-%m-%d %H%M%S')}"
    return base + extensao


def reservar(pasta: Path, nome: str):
    """Abre para escrita um arquivo novo `nome` em `pasta`, sem passar por
    cima de nenhum: repetido vira "nome 2.png". Devolve (caminho, arquivo)."""
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    base, _, extensao = nome.rpartition(".")
    caminho, contador = pasta / nome, 2
    while True:
        try:
            arquivo = caminho.open("xb")
        except FileExistsError:
            caminho = pasta / f"{base} {contador}.{extensao}"
            contador += 1
            continue
        caminho.chmod(0o600)
        return caminho, arquivo


def link_para(vault_dir: Path, nota: str, caminho: str) -> str:
    """O `![[...]]` que a nota escreve: o nome curto, se ele leva ao anexo a
    partir da nota; senão o caminho."""
    curto = caminho.rpartition("/")[2]
    alvo = curto if indice(vault_dir).resolver(curto, nota) == caminho else caminho
    return f"![[{alvo}]]"
