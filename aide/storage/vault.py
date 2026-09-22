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


def slugify(texto: str, tamanho: int = 60) -> str:
    normal = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^\w\s-]", "", normal).strip().lower()
    return re.sub(r"[\s_-]+", "-", limpo)[:tamanho].strip("-") or "nota"


def caminho_para(vault_dir: Path, titulo: str, criada_em: datetime) -> Path:
    """Uma pasta por mês evita um diretório com milhares de arquivos."""
    pasta = vault_dir / criada_em.strftime("%Y-%m")
    base = f"{criada_em.strftime('%Y-%m-%d')}-{slugify(titulo)}"
    caminho = pasta / f"{base}.md"
    contador = 2
    while caminho.exists():
        caminho = pasta / f"{base}-{contador}.md"
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
             criada_em: datetime) -> None:
    # nota é texto puro com a sua vida dentro; nasce só sua
    caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    frontmatter = [
        SEPARADOR,
        f"title: {titulo}",
        f"created: {criada_em.isoformat(timespec='minutes')}",
    ]
    if tags:
        frontmatter.append(f"tags: [{tags}]")
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


def corpo_de(caminho: Path) -> str:
    return ler(caminho)[1]
