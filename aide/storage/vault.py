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


def escrever(caminho: Path, titulo: str, corpo: str, tags: str | None,
             criada_em: datetime) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        SEPARADOR,
        f"title: {titulo}",
        f"created: {criada_em.isoformat(timespec='minutes')}",
    ]
    if tags:
        frontmatter.append(f"tags: [{tags}]")
    frontmatter.append(SEPARADOR)
    caminho.write_text("\n".join(frontmatter) + "\n\n" + corpo.strip() + "\n")


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
