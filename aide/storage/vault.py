"""Vault: as notas em markdown.

O arquivo é a fonte da verdade — legível sem o projeto, versionável em git.
O SQLite é índice: se ele sumir, dá para reconstruir a partir dos arquivos.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

SEPARADOR = "---"
LIXEIRA = ".trash"


INBOX = "Inbox"
# o que o Windows, o macOS ou o Obsidian não aceitam num nome de arquivo, ou
# que o Obsidian lê como sintaxe de link: [[a#b]], [[a^b]], [[a|b]]
PROIBIDOS = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
TAMANHO_NOME = 100


def nome_de_arquivo(titulo: str) -> str:
    """'Reunião: orçamento' -> 'Reunião orçamento'. O título vira o nome do
    arquivo, com acento e espaço, como no Obsidian: é isso que deixa um
    [[Reunião orçamento]] achar a nota."""
    limpo = re.sub(r"\s+", " ", PROIBIDOS.sub(" ", unicodedata.normalize("NFC", titulo)))
    # ponto na frente esconderia o arquivo; no fim, o Windows tira sozinho
    limpo = limpo.strip(" .")[:TAMANHO_NOME].strip(" .")
    return limpo or "Sem título"


def caminho_para(vault_dir: Path, titulo: str) -> Path:
    """`Inbox/Título.md`. As notas do assessor caem numa pasta só, e você as
    leva para onde quiser pela página; repetido vira `Título 2.md`."""
    pasta = vault_dir / INBOX
    base = nome_de_arquivo(titulo)
    caminho = pasta / f"{base}.md"
    contador = 2
    while caminho.exists():
        caminho = pasta / f"{base} {contador}.md"
        contador += 1
    return caminho


def para_lixeira(vault_dir: Path, caminho: Path) -> Path | None:
    """Tira o arquivo do vault sem destruí-lo, e devolve onde ele foi parar.

    Apagar uma nota tem de ser um ato completo: enquanto o arquivo ficava no
    vault com a linha marcada como apagada, ele não aparecia em lugar nenhum e
    nem a reindexação o alcançava, porque ela varre as linhas. Com o arquivo
    fora, vale uma regra só: o que está no vault é nota viva.

    Não é destruição. O texto continua legível em `vault/.trash/`, e voltar é um
    `mv`. O que deixa de existir é o meio-caminho.
    """
    if not caminho.exists():
        return None
    destino = vault_dir / LIXEIRA / caminho.name
    contador = 2
    while destino.exists():
        destino = vault_dir / LIXEIRA / f"{caminho.stem}-{contador}{caminho.suffix}"
        contador += 1
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    caminho.replace(destino)
    return destino


def arquivos(vault_dir: Path) -> list[Path]:
    """Todo markdown do vault, menos a lixeira. Ordem estável, para o relato
    de uma reindexação sair igual duas vezes."""
    if not vault_dir.exists():
        return []
    return sorted(p for p in vault_dir.rglob("*.md")
                  if LIXEIRA not in p.relative_to(vault_dir).parts)


def escrever(caminho: Path, titulo: str, corpo: str, tags: str | None,
             criada_em: datetime, privada: bool = False) -> None:
    # nota é texto puro com a sua vida dentro; nasce só sua
    caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    frontmatter = [
        SEPARADOR,
        f"title: {titulo}",
        f"created: {criada_em.isoformat(timespec='minutes')}",
    ]
    if tags:
        frontmatter.append(f"tags: [{tags}]")
    if privada:
        # no arquivo, e não só no banco: o arquivo é a fonte da verdade, e uma
        # reindexação a partir dele não pode desfazer o privado
        frontmatter.append("private: true")
    frontmatter.append(SEPARADOR)
    caminho.write_text("\n".join(frontmatter) + "\n\n" + corpo.strip() + "\n")
    caminho.chmod(0o600)


def acrescentar(caminho: Path, texto: str, quando: datetime) -> None:
    with caminho.open("a") as arquivo:
        arquivo.write(f"\n\n_{quando.strftime('%d/%m/%Y %H:%M')}_\n\n{texto.strip()}\n")


def ler(caminho: Path) -> tuple[dict[str, str], str]:
    """Devolve (frontmatter, corpo). Arquivo sem frontmatter também serve."""
    texto = caminho.read_text()
    if not texto.startswith(SEPARADOR):
        return {}, texto.strip()

    partes = texto.split(SEPARADOR, 2)
    if len(partes) < 3:
        return {}, texto.strip()

    meta = {}
    for linha in partes[1].strip().splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            meta[chave.strip()] = valor.strip()
    return meta, partes[2].strip()


def privada(meta: dict[str, str]) -> bool:
    """`private: true` no frontmatter. Qualquer outra coisa é nota normal."""
    return meta.get("private", "").strip().lower() in ("true", "yes", "sim", "1")


def corpo_de(caminho: Path) -> str:
    return ler(caminho)[1]
