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

# a licença de cada pacote que entrou no bundle (todas MIT ou parecidas). Os
# que o npm publica sem o arquivo têm o texto do repositório em licencas/; um
# pacote novo sem nenhum dos dois para o build, em vez de sair sem aviso.
licenca_de() {
    local achado
    achado=$(find node_modules/"$1" -maxdepth 1 -type f -iregex '.*/\(licen[cs]e\|copying\)[^/]*' \
        | head -1)
    if [ -n "$achado" ]; then echo "$achado"; return; fi
    case "$1" in
        @excalidraw/excalidraw) echo licencas/excalidraw.txt ;;
        @radix-ui/*) echo licencas/radix-ui.txt ;;
        react-remove-scroll-bar) echo licencas/react-remove-scroll-bar.txt ;;
        *) echo "sem licença: $1" >&2; return 1 ;;
    esac
}
{
    while read -r pacote; do
        echo "== $pacote $(node -p "require('./node_modules/$pacote/package.json').version") =="
        cat "$(licenca_de "$pacote")"
        echo
    done < pacotes.txt
    echo "== fontes =="
    echo "As de fonts/ vêm do pacote @excalidraw/excalidraw: Cascadia, Liberation,"
    echo "Lilita, Nunito, Assistant, Excalifont e Virgil sob a SIL OFL 1.1;"
    echo "Comic Shanns sob MIT."
} > "$DESTINO/LICENCAS.txt"
rm pacotes.txt
du -sh "$DESTINO"
