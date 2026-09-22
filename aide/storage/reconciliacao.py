"""Pôr o banco de acordo com o vault.

Existe um lugar só porque havia dois: o comando `myaide reindexar` e o job
`reindex_vault` do daemon faziam trabalhos diferentes com o mesmo nome. O
comando reconciliava nos dois sentidos e o job só reindexava linha existente,
então uma nota escrita no editor entrava na busca se você rodasse o comando à
mão e nunca entrava se você esperasse o daemon.

O relatório é devolvido em vez de impresso: o terminal escreve em cor e o
daemon escreve no journal, e quem decide isso é quem chamou.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aide.storage import vault
from aide.storage.search import guardar_vetor, indexar

log = logging.getLogger(__name__)

# o updated_at do SQLite tem resolução de segundos e o mtime tem fração; sem
# folga, toda nota recém-criada parece editada e reindexa à toa
FOLGA_MTIME = timedelta(seconds=2)


@dataclass
class Relatorio:
    reindexadas: list[tuple[int, str]] = field(default_factory=list)
    adotadas: list[tuple[int, str]] = field(default_factory=list)
    recolhidas: list[Path] = field(default_factory=list)
    sumidas: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def mexeu(self) -> bool:
        return bool(self.reindexadas or self.adotadas or self.recolhidas or self.sumidas)


def reconciliar(conn, vault_dir: Path, embedder=None, forcar: bool = False) -> Relatorio:
    """Varre o vault e acerta o banco.

    Arquivo que o banco não conhece é adotado; arquivo de nota apagada volta
    para a lixeira; linha sem arquivo é relatada. Com `forcar`, reindexa tudo,
    que é o que o comando à mão precisa depois de um banco corrompido; sem ele,
    só o que mudou desde a última indexação, que é o que o daemon precisa para
    rodar a cada quinze minutos sem trabalho inútil.
    """
    relatorio = Relatorio()
    vivas = {Path(r["path"]).resolve(): r for r in conn.execute(
        "SELECT id, title, path, updated_at FROM notes WHERE deleted_at IS NULL")}
    apagadas = {Path(r["path"]).resolve() for r in conn.execute(
        "SELECT path FROM notes WHERE deleted_at IS NOT NULL")}

    for caminho in vault.arquivos(vault_dir):
        real = caminho.resolve()

        if real in vivas:
            row = vivas[real]
            if forcar or _mudou(caminho, row["updated_at"]):
                corpo = vault.corpo_de(caminho)
                _indexar(conn, row["id"], row["title"], corpo, embedder)
                conn.execute("UPDATE notes SET updated_at = datetime('now') WHERE id = ?",
                             (row["id"],))
                relatorio.reindexadas.append((row["id"], row["title"]))
            continue

        if real in apagadas:
            destino = vault.para_lixeira(vault_dir, caminho)
            if destino:
                relatorio.recolhidas.append(destino)
            continue

        meta, corpo = vault.ler(caminho)
        titulo = meta.get("title") or caminho.stem
        cur = conn.execute("INSERT INTO notes (title, path, tags) VALUES (?, ?, ?)",
                           (titulo, str(caminho), (meta.get("tags") or "").strip("[]") or None))
        _indexar(conn, cur.lastrowid, titulo, corpo, embedder)
        relatorio.adotadas.append((cur.lastrowid, titulo))

    for real, row in vivas.items():
        if not real.exists():
            relatorio.sumidas.append((row["id"], row["title"], row["path"]))

    return relatorio


def _mudou(caminho: Path, indexado_em: str) -> bool:
    # datetime('now') do SQLite é UTC; comparar com mtime local atrasaria a
    # reindexação pelo tamanho do fuso (4h aqui) e ninguém entenderia por quê
    modificado = datetime.fromtimestamp(caminho.stat().st_mtime, tz=UTC)
    indexado = datetime.fromisoformat(indexado_em).replace(tzinfo=UTC)
    return modificado > indexado + FOLGA_MTIME


def _indexar(conn, note_id: int, titulo: str, corpo: str, embedder) -> None:
    """Palavra-chave sempre; semântico só com embedder, e sem propagar falha:
    a nota precisa ficar indexada mesmo sem rede ou sem chave."""
    indexar(conn, note_id, titulo, corpo)
    if embedder is None:
        return
    try:
        vetor = embedder.embed_one(f"{titulo}\n\n{corpo}")
    except Exception:
        log.warning("embedding da nota %s falhou", note_id, exc_info=True)
        return
    if vetor:
        guardar_vetor(conn, "note", note_id, f"{titulo}\n\n{corpo}", vetor, embedder.modelo)
