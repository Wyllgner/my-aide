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
from aide.storage.search import guardar_vetor, indexar, remover_do_indice, remover_vetor

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
    vetorizadas: list[tuple[int, str]] = field(default_factory=list)

    @property
    def mexeu(self) -> bool:
        return bool(self.reindexadas or self.adotadas or self.recolhidas or self.sumidas
                    or self.vetorizadas)


def reconciliar(conn, vault_dir: Path, embedder=None, forcar: bool = False) -> Relatorio:
    """Varre o vault e acerta o banco.

    Arquivo que o banco não conhece é adotado; arquivo de nota apagada volta
    para a lixeira; linha sem arquivo é relatada. Com `forcar`, reindexa tudo,
    que é o que o comando à mão precisa depois de um banco corrompido; sem ele,
    só o que mudou desde a última indexação, que é o que o daemon precisa para
    rodar a cada quinze minutos sem trabalho inútil.
    """
    relatorio = Relatorio()
    privado_para_o_arquivo(conn)
    vivas = {Path(r["path"]).resolve(): r for r in conn.execute(
        "SELECT id, title, path, updated_at, private FROM notes WHERE deleted_at IS NULL")}
    apagadas = {Path(r["path"]).resolve() for r in conn.execute(
        "SELECT path FROM notes WHERE deleted_at IS NOT NULL")}

    for caminho in vault.arquivos(vault_dir):
        real = caminho.resolve()

        if real in vivas:
            row = vivas[real]
            if forcar or _mudou(caminho, row["updated_at"]):
                meta, corpo = vault.ler(caminho)
                privada = bool(row["private"])
                if vault.privada(meta) and not privada:
                    # marcada privada no arquivo, por fora do assessor. Só sobe:
                    # tirar o privado é decisão explícita, nunca efeito de uma
                    # linha que sumiu do frontmatter
                    privada = True
                    conn.execute("UPDATE notes SET private = 1 WHERE id = ?", (row["id"],))
                    remover_vetor(conn, row["id"])
                _indexar(conn, row["id"], row["title"], corpo,
                         None if privada else embedder)
                _registrar_fora(conn, vault_dir, caminho)
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
        privada = vault.privada(meta)
        cur = conn.execute("INSERT INTO notes (title, path, tags, private) VALUES (?, ?, ?, ?)",
                           (titulo, str(caminho), (meta.get("tags") or "").strip("[]") or None,
                            int(privada)))
        _indexar(conn, cur.lastrowid, titulo, corpo, None if privada else embedder)
        _registrar_fora(conn, vault_dir, caminho)
        relatorio.adotadas.append((cur.lastrowid, titulo))

    for real, row in vivas.items():
        if not real.exists():
            relatorio.sumidas.append((row["id"], row["title"], row["path"]))

    if embedder is not None:
        _sem_vetor(conn, embedder, relatorio)
    return relatorio


def privado_para_o_arquivo(conn, caminho: Path | None = None) -> list[Path]:
    """Escreve `private: true` no arquivo das notas que só o banco tem como
    privadas; devolve as que mudaram. Com `caminho`, só essa nota.

    São as de antes de o privado ir para o arquivo. A página lê o privado do
    frontmatter e, ao salvar, grava no banco o que ele diz: sem a linha, a
    caixa aparecia desmarcada, a primeira edição tornava a nota normal e a
    reconciliação seguinte mandava o texto para fora.
    """
    sql = "SELECT path FROM notes WHERE private = 1 AND deleted_at IS NULL"
    params: tuple = ()
    if caminho is not None:
        sql += " AND path = ?"
        params = (str(caminho),)
    marcadas = []
    for row in conn.execute(sql, params).fetchall():
        arquivo = Path(row["path"])
        try:
            texto = arquivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if vault.privada(vault.separar(texto)[0]):
            continue
        vault.gravar(arquivo, vault.com_privado(texto))
        marcadas.append(arquivo)
    return marcadas


def sincronizar(conn, caminho: Path) -> int:
    """Põe no índice o arquivo que acabou de ser salvo na página; devolve o id.

    Título, tags e privado vêm do frontmatter, e aqui o privado vale nos dois
    sentidos: na página o frontmatter está na sua frente, e desmarcar é uma
    decisão que você tomou vendo. A busca por palavra-chave é refeita na hora,
    porque é local; o vetor velho é apagado e o novo fica para a reconciliação
    do daemon, que não manda nota privada. Gerar o vetor a cada pausa na
    digitação mandaria o texto para fora antes de você marcar a nota como
    privada — e pagaria uma chamada por pausa.

    Linha apagada com o mesmo caminho volta à vida: sem isso a reconciliação
    veria "arquivo de nota apagada" e mandaria a nota nova para a lixeira.
    """
    meta, corpo = vault.ler(caminho)
    titulo = meta.get("title") or caminho.stem
    tags = (meta.get("tags") or "").strip("[]") or None
    privada = int(vault.privada(meta))
    row = conn.execute("SELECT id FROM notes WHERE path = ?", (str(caminho),)).fetchone()
    if row is None:
        note_id = conn.execute(
            "INSERT INTO notes (title, path, tags, private) VALUES (?, ?, ?, ?)",
            (titulo, str(caminho), tags, privada)).lastrowid
    else:
        note_id = row["id"]
        conn.execute(
            "UPDATE notes SET title = ?, tags = ?, private = ?, deleted_at = NULL,"
            " updated_at = datetime('now') WHERE id = ?", (titulo, tags, privada, note_id))
    indexar(conn, note_id, titulo, corpo)
    remover_vetor(conn, note_id)
    return note_id


def mover_no_indice(conn, de: Path, para: Path) -> int:
    """Acompanha no banco uma nota renomeada ou movida; devolve o id.

    A linha é a mesma — busca, histórico e vetor continuam valendo, porque o
    texto não mudou. Só o caminho e, se o título vinha do nome do arquivo, o
    título. Linha apagada que tinha o caminho novo sai do caminho: ele é
    único no banco, e o arquivo que ela marcava já está na lixeira.
    """
    conn.execute("UPDATE notes SET path = path || '#apagada-' || id"
                 " WHERE path = ? AND deleted_at IS NOT NULL", (str(para),))
    row = conn.execute("SELECT id FROM notes WHERE path = ? AND deleted_at IS NULL",
                       (str(de),)).fetchone()
    if row is None:
        return sincronizar(conn, para)
    meta, corpo = vault.ler(para)
    titulo = meta.get("title") or para.stem
    conn.execute("UPDATE notes SET path = ?, title = ?, updated_at = datetime('now')"
                 " WHERE id = ?", (str(para), titulo, row["id"]))
    indexar(conn, row["id"], titulo, corpo)
    return row["id"]


def esquecer(conn, caminho: Path) -> int | None:
    """O lado do banco de mandar um arquivo para a lixeira pela página."""
    row = conn.execute("SELECT id FROM notes WHERE path = ? AND deleted_at IS NULL",
                       (str(caminho),)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE notes SET deleted_at = datetime('now') WHERE id = ?", (row["id"],))
    remover_do_indice(conn, row["id"])
    remover_vetor(conn, row["id"])
    return row["id"]


def _sem_vetor(conn, embedder, relatorio: Relatorio) -> None:
    """Notas normais que ainda não viraram vetor: as salvas pela página, ou as
    em que a chamada falhou da outra vez."""
    for row in conn.execute(
            "SELECT n.id, n.title, n.path FROM notes n WHERE n.deleted_at IS NULL"
            " AND n.private = 0 AND NOT EXISTS (SELECT 1 FROM embeddings e"
            " WHERE e.ref_type = 'note' AND e.ref_id = n.id)").fetchall():
        caminho = Path(row["path"])
        if not caminho.exists():
            continue
        meta, corpo = vault.ler(caminho)
        if vault.privada(meta):
            # marcada no arquivo depois da última indexação, e a varredura de
            # cima não viu porque o mtime ficou dentro da folga: o arquivo,
            # que é o que vai para fora, tem a última palavra
            conn.execute("UPDATE notes SET private = 1 WHERE id = ?", (row["id"],))
            continue
        _indexar(conn, row["id"], row["title"], corpo, embedder)
        relatorio.vetorizadas.append((row["id"], row["title"]))


def _registrar_fora(conn, vault_dir: Path, caminho: Path) -> None:
    """Mexida por fora (Obsidian, editor): o dia é o da modificação do arquivo,
    no fuso desta máquina, que é o de quem escreveu."""
    from aide.storage import atividade

    quando = datetime.fromtimestamp(caminho.stat().st_mtime).astimezone()
    atividade.registrar(conn, vault_dir, caminho, quando, "fora")


def _mudou(caminho: Path, indexado_em: str) -> bool:
    # datetime('now') do SQLite é UTC; comparar com mtime local atrasaria a
    # reindexação pelo tamanho do fuso (4h aqui) e ninguém entenderia por quê
    modificado = datetime.fromtimestamp(caminho.stat().st_mtime, tz=UTC)
    indexado = datetime.fromisoformat(indexado_em).replace(tzinfo=UTC)
    return modificado > indexado + FOLGA_MTIME


def _indexar(conn, note_id: int, titulo: str, corpo: str, embedder) -> None:
    """Palavra-chave sempre; semântico só com embedder, e sem propagar falha:
    a nota precisa ficar indexada mesmo sem rede ou sem chave. Para nota
    privada quem chama passa embedder None: o vetor sairia daqui com o texto."""
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
