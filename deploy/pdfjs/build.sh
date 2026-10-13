#!/usr/bin/env bash
# Recompila aide/web/vendor/pdfjs a partir da versão fixa abaixo. Precisa de
# npm só aqui; o servidor serve o resultado pronto.
#
# O pdf.js já vem compilado no pacote: não há bundle, só cópia. O pacote é
# baixado com `npm pack` (nenhum script dele roda) e conferido pelo hash
# publicado no registro antes de qualquer coisa sair dele.
set -euo pipefail
cd "$(dirname "$0")"
VERSAO=6.3.289
INTEGRIDADE=sha512-ZHjSVpDa3D6izMq8/04lvkhkATUmL9px6ChPaXc1k6nU2Mrhlg1/7F0bdUqCwUjw3NsPTfPZsMDUU6ZIcRaeQw==
DESTINO=../../aide/web/vendor/pdfjs

TRABALHO=$(mktemp -d)
trap 'rm -rf "$TRABALHO"' EXIT
(cd "$TRABALHO" && npm pack "pdfjs-dist@$VERSAO" --silent > /dev/null)
PACOTE="$TRABALHO/pdfjs-dist-$VERSAO.tgz"
OBTIDA="sha512-$(openssl dgst -sha512 -binary "$PACOTE" | base64 -w0)"
if [ "$OBTIDA" != "$INTEGRIDADE" ]; then
    echo "pacote não confere com o hash fixado" >&2
    exit 1
fi
tar xzf "$PACOTE" -C "$TRABALHO"

rm -rf "$DESTINO"
mkdir -p "$DESTINO"
# .js e não .mjs: o servidor só entrega os tipos que conhece (app.py)
cp "$TRABALHO/package/build/pdf.min.mjs" "$DESTINO/pdf.js"
cp "$TRABALHO/package/build/pdf.worker.min.mjs" "$DESTINO/pdf.worker.js"
{
    echo "== pdfjs-dist $VERSAO =="
    cat "$TRABALHO/package/LICENSE"
} > "$DESTINO/LICENCAS.txt"
du -sh "$DESTINO"
