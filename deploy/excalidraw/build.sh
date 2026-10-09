#!/usr/bin/env bash
# Recompila aide/web/vendor/excalidraw a partir das versões fixas do
# package.json. Precisa de Node só aqui; o servidor serve o resultado pronto.
set -euo pipefail
cd "$(dirname "$0")"
DESTINO=../../aide/web/vendor/excalidraw
PACOTE=node_modules/@excalidraw/excalidraw/dist/prod

# --ignore-scripts: nenhum pacote roda nada na instalação
npm ci --ignore-scripts --no-audit --no-fund

rm -rf "$DESTINO"
mkdir -p "$DESTINO"
node build.mjs "$DESTINO" > pacotes.txt

cp "$PACOTE/index.css" "$DESTINO/excalidraw.css"
# Xiaolai é a fonte de chinês/japonês: 13 MB que não compensam
mkdir -p "$DESTINO/fonts"
for fonte in "$PACOTE"/fonts/*/; do
    nome=$(basename "$fonte")
    [ "$nome" = Xiaolai ] || cp -r "$fonte" "$DESTINO/fonts/$nome"
done

# a licença de cada pacote que entrou no bundle (todas MIT ou parecidas)
{
    while read -r pacote; do
        licenca=$(ls node_modules/"$pacote"/LICEN[CS]E* 2>/dev/null | head -1 || true)
        echo "== $pacote $(node -p "require('./node_modules/$pacote/package.json').version") =="
        if [ -n "$licenca" ]; then cat "$licenca"; else
            node -p "require('./node_modules/$pacote/package.json').license"; fi
        echo
    done < pacotes.txt
    echo "== fontes =="
    echo "As de fonts/ vêm do pacote @excalidraw/excalidraw: Cascadia, Liberation,"
    echo "Lilita, Nunito, Assistant, Excalifont e Virgil sob a SIL OFL 1.1;"
    echo "Comic Shanns sob MIT."
} > "$DESTINO/LICENCAS.txt"
rm pacotes.txt
du -sh "$DESTINO"
