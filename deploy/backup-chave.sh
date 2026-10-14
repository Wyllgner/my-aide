#!/usr/bin/env bash
# Cria a chave do cofre do backup (uma vez) e, se receber um endereço, liga o
# cofre ao remoto.
#
#   deploy/backup-chave.sh                                  # só a chave
#   deploy/backup-chave.sh https://github.com/voce/dados.git
#
# A chave privada fica em ~/.config/my-aide/backup.key (600). GUARDE UMA
# CÓPIA DELA FORA DESTE COMPUTADOR — num gerenciador de senhas, num pendrive
# guardado, impresso. Sem ela o cofre não abre, e o cofre existe justamente
# para o dia em que este computador não existir mais.
set -euo pipefail
umask 077

CHAVE="${MY_AIDE_BACKUP_CHAVE:-$HOME/.config/my-aide/backup.key}"
COFRE="${MY_AIDE_BACKUP_COFRE:-$HOME/.local/share/my-aide-backup-cofre}"

if ! command -v age-keygen >/dev/null; then
    echo "instale o age primeiro: sudo apt install age" >&2
    exit 1
fi

mkdir -p "$(dirname "$CHAVE")"
if [ -f "$CHAVE" ]; then
    echo "a chave já existe em $CHAVE; não troquei (trocar perderia o acesso ao cofre)"
else
    age-keygen -o "$CHAVE" 2>/dev/null
    chmod 600 "$CHAVE"
    echo "chave criada em $CHAVE"
fi
echo "chave pública: $(age-keygen -y "$CHAVE")"

mkdir -p "$COFRE"
[ -d "$COFRE/.git" ] || git -C "$COFRE" init -q -b main
if [ "${1:-}" ]; then
    git -C "$COFRE" remote remove origin 2>/dev/null || true
    git -C "$COFRE" remote add origin "$1"
    echo "cofre ligado a $1"
fi
echo
echo "Agora guarde uma cópia de $CHAVE fora deste computador."
