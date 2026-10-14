#!/usr/bin/env bash
# Cópia diária do que não dá para recriar: o banco e o vault.
#
# Duas cópias, com papéis diferentes:
#
# - a LOCAL ($DESTINO): repositório git em texto, com histórico — dá para voltar
#   ao estado de ontem e ver o que mudou. Nunca sai da máquina: ela tem o banco
#   inteiro, privado incluído, e o histórico guarda até o que foi apagado.
# - o COFRE ($COFRE): o mesmo conteúdo, empacotado e criptografado com `age`
#   para a sua chave. É o único que vai para o remoto (o GitHub), e vai como
#   um commit só, refeito a cada envio, com os últimos $MANTER pacotes. Sem a
#   chave privada ninguém abre — nem o GitHub, nem quem entrar na sua conta.
#
# Sem chave, não há cofre nem envio: o backup fica só local. A chave é criada
# por deploy/backup-chave.sh; guarde uma cópia dela FORA deste computador, ou
# o cofre não serve no dia em que o disco morrer.
#
# O banco vai como dump SQL, não como arquivo .db. Dois motivos: o .db binário
# sai com bytes diferentes a cada cópia (freelist, ordem de página), o que
# encheria o histórico de commits sem mudança nenhuma; e o dump dá diff
# legível — dá para ver qual tarefa entrou ontem.
#
# Restaurar do cofre (o mais recente), numa pasta vazia:
#   age -d -i ~/.config/my-aide/backup.key backups/backup-AAAA-MM-DDTHHMM.tar.gz.age | tar -xz
#   (sai data/aide.sql e vault/; daí em diante, como abaixo)
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
COFRE="${MY_AIDE_BACKUP_COFRE:-$HOME/.local/share/my-aide-backup-cofre}"
CHAVE="${MY_AIDE_BACKUP_CHAVE:-$HOME/.config/my-aide/backup.key}"
MANTER="${MY_AIDE_BACKUP_MANTER:-30}"
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
MUDOU=1
if git -C "$DESTINO" diff --cached --quiet; then
    MUDOU=0
    echo "nada mudou desde o último backup"
else
    git -C "$DESTINO" commit -q -m "backup $(date +%Y-%m-%dT%H:%M)"
    echo "backup gravado: $(git -C "$DESTINO" rev-parse --short HEAD)"
fi

# ---------- o cofre: a única cópia que sai da máquina ----------

if [ ! -f "$CHAVE" ]; then
    echo "sem chave em $CHAVE: backup só local (deploy/backup-chave.sh cria a chave)"
    exit 0
fi
# chave legível por outra conta não é segredo; melhor parar do que fingir
if [ "$(stat -c %a "$CHAVE")" != "600" ]; then
    echo "a chave $CHAVE precisa de permissão 600; nada foi enviado" >&2
    exit 1
fi
if ! command -v age >/dev/null || ! command -v age-keygen >/dev/null; then
    echo "há chave mas o age não está instalado (sudo apt install age); nada foi enviado" >&2
    exit 1
fi

mkdir -p "$COFRE/backups"
# um pacote novo quando algo mudou, ou quando o cofre ainda está vazio
if [ "$MUDOU" = 1 ] || [ -z "$(ls -A "$COFRE/backups")" ]; then
    DESTINATARIO="$(age-keygen -y "$CHAVE")"
    PACOTE="$COFRE/backups/backup-$(date +%Y-%m-%dT%H%M%S).tar.gz.age"
    tar -C "$DESTINO" -czf - data vault | age -r "$DESTINATARIO" -o "$PACOTE.parcial"
    # confere que abre com a chave antes de valer: um pacote que não abre é
    # pior que nenhum, porque dá a impressão de backup
    age -d -i "$CHAVE" "$PACOTE.parcial" | tar -tzf - >/dev/null
    mv "$PACOTE.parcial" "$PACOTE"
    echo "cofre: $(basename "$PACOTE")"
    # só os últimos $MANTER; o histórico longo fica na cópia local
    ls -1 "$COFRE/backups"/*.age | sort | head -n "-$MANTER" | xargs -r rm --
fi

if [ ! -d "$COFRE/.git" ]; then
    git -C "$COFRE" init -q -b main
fi
if ! git -C "$COFRE" remote | grep -q origin; then
    echo "cofre sem remoto: ficou só local"
    exit 0
fi
# um commit só, refeito a cada envio: o remoto nunca acumula versões antigas
git -C "$COFRE" checkout -q --orphan envio
git -C "$COFRE" add -A
git -C "$COFRE" commit -q -m "cofre $(date +%Y-%m-%dT%H:%M)"
git -C "$COFRE" branch -D main -q 2>/dev/null || true
git -C "$COFRE" branch -m main
git -C "$COFRE" push -q --force origin main && echo "cofre enviado para o remoto"
git -C "$COFRE" reflog expire --expire=now --all
git -C "$COFRE" gc -q --prune=now
