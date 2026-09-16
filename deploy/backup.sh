#!/usr/bin/env bash
# Cópia diária do que não dá para recriar: o banco e o vault.
#
# O destino é um repositório git separado — o histórico versionado é o que
# transforma isso em backup de verdade: dá para voltar ao estado de ontem, não
# só ao último instante.
#
# O banco vai como dump SQL, não como arquivo .db. Dois motivos: o .db binário
# sai com bytes diferentes a cada cópia (freelist, ordem de página), o que
# encheria o histórico de commits sem mudança nenhuma; e o dump dá diff
# legível — dá para ver qual tarefa entrou ontem.
#
# Restaurar:
#   .venv/bin/python -c "import sqlite3,sys; \
#     sqlite3.connect('data/aide.db').executescript(open(sys.argv[1]).read())" \
#     ~/.local/share/my-aide-backup/data/aide.sql
#   .venv/bin/myaide reindexar      # repovoa o índice de busca

set -euo pipefail

# O destino guarda o banco inteiro em texto e as notas. Sem isto o umask do
# desktop (002) faria o dump nascer legível por qualquer conta da máquina.
umask 077

ORIGEM="${MY_AIDE_DIR:-$HOME/Documentos/acessor}"
DESTINO="${MY_AIDE_BACKUP_DIR:-$HOME/.local/share/my-aide-backup}"
PYTHON="$ORIGEM/.venv/bin/python"

mkdir -p "$DESTINO/data"

if [ ! -d "$DESTINO/.git" ]; then
    git -C "$DESTINO" init -q -b main
fi

# modo somente leitura: o daemon está escrevendo neste banco agora mesmo.
"$PYTHON" - "$ORIGEM/data/aide.db" "$DESTINO/data/aide.sql" <<'PYEOF'
import re
import sqlite3
import sys

origem, destino = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)

# O iterdump não sabe despejar uma tabela virtual: escreve direto no
# sqlite_master e emite os INSERT antes das tabelas-sombra existirem, então o
# dump não restaura. O índice FTS é descartável de qualquer forma — recriamos
# a tabela vazia e `myaide reindexar` a repovoa a partir do vault.
FTS = re.compile(
    r"""^(?:CREATE\s+(?:VIRTUAL\s+)?TABLE\s+['"]?notes_fts"""
    r"""|INSERT\s+INTO\s+["']?notes_fts"""
    r"""|INSERT\s+INTO\s+sqlite_master\b.*'notes_fts')""",
    re.IGNORECASE | re.DOTALL,
)

versao = conn.execute("PRAGMA user_version").fetchone()[0]

with open(destino, "w") as saida:
    for comando in conn.iterdump():
        if FTS.match(comando):
            continue
        saida.write(comando + "\n")
    # o iterdump omite o user_version; sem ele o migrate() acha que o banco é
    # novo e tenta reaplicar as migrations sobre tabelas que já existem.
    saida.write(f"PRAGMA user_version = {versao};\n")
    saida.write("CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body);\n")

conn.close()
PYEOF

# --delete para uma nota apagada sumir também do backup; o histórico do git é
# quem guarda a versão anterior.
# --chmod porque -a preserva a permissão da origem: uma nota frouxa lá viraria
# uma nota frouxa aqui. O destino impõe a sua, não herda a do vizinho.
rsync -a --delete --chmod=D700,F600 "$ORIGEM/vault/" "$DESTINO/vault/"

git -C "$DESTINO" add -A
if git -C "$DESTINO" diff --cached --quiet; then
    echo "nada mudou desde o último backup"
    exit 0
fi

git -C "$DESTINO" commit -q -m "backup $(date +%Y-%m-%dT%H:%M)"
echo "backup gravado: $(git -C "$DESTINO" rev-parse --short HEAD)"

# Só empurra se houver remoto configurado; sem remoto, o backup é local.
if git -C "$DESTINO" remote | grep -q origin; then
    git -C "$DESTINO" push -q origin main && echo "enviado para o remoto"
fi
