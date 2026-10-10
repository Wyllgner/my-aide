"""A folha de estilo, servida uma vez em /app.css.

Separada do HTML porque é a mesma em todas as telas — repeti-la em cada página
faria o navegador reprocessar o mesmo texto a cada clique.
"""

from __future__ import annotations

# As fontes moram no projeto (licença OFL, em aide/web/fontes/): buscá-las no
# Google a cada página contava a ele cada vez que você abria o assessor.
# Só os alfabetos latino e latino estendido, que cobrem o português.
FONTES = """
@font-face { font-family: 'IBM Plex Mono'; font-style: normal; font-weight: 400; font-display: swap;
  src: url(/fontes/ibm-plex-mono-400-latin-ext.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'IBM Plex Mono'; font-style: normal; font-weight: 400; font-display: swap;
  src: url(/fontes/ibm-plex-mono-400-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: 'IBM Plex Mono'; font-style: normal; font-weight: 500; font-display: swap;
  src: url(/fontes/ibm-plex-mono-500-latin-ext.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'IBM Plex Mono'; font-style: normal; font-weight: 500; font-display: swap;
  src: url(/fontes/ibm-plex-mono-500-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: 'Instrument Serif'; font-style: normal; font-weight: 400; font-display: swap;
  src: url(/fontes/instrument-serif-400-latin-ext.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'Instrument Serif'; font-style: normal; font-weight: 400; font-display: swap;
  src: url(/fontes/instrument-serif-400-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: 'Public Sans'; font-style: normal; font-weight: 400 600; font-display: swap;
  src: url(/fontes/public-sans-var-latin-ext.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'Public Sans'; font-style: normal; font-weight: 400 600; font-display: swap;
  src: url(/fontes/public-sans-var-latin.woff2) format('woff2');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
"""

CSS = FONTES + """
:root {
  --paper:#FBFBFC; --surface:#FFFFFF; --ink:#15171C; --muted:#6C727E;
  --faint:#9CA2AD; --line:#EDEFF2; --line-soft:#F4F5F7; --borda:#DDE0E6;
  --accent:#C4432B; --accent-forte:#A63722; --soft:#FCF1EE;
  --r-card:16px; --r-inner:10px; --r-pill:999px;
  --sombra:0 1px 2px rgba(21,23,28,.04);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: 'Public Sans', system-ui, -apple-system, sans-serif;
  font-size: 14px; -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-forte); }

.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.h1 { font-family: 'Instrument Serif', Georgia, serif; font-weight: 400;
      font-size: 34px; letter-spacing: -.015em; margin: 0; }
.eyebrow { font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
           color: var(--faint); font-weight: 600; margin: 0; }
.card { background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-card); box-shadow: var(--sombra); }
.pill { font-size: 11px; font-weight: 600; padding: 3px 9px;
        border-radius: var(--r-pill); background: var(--soft); color: var(--accent); }
.late { color: var(--accent); }

/* estrutura */
.app { display: flex; min-height: 100vh; }
main { flex: 1; padding: 34px 40px; min-width: 0; }
.cabecalho { display: flex; align-items: flex-end; justify-content: space-between;
             gap: 24px; margin-bottom: 26px; }

/* barra lateral */
.lateral {
  width: 236px; flex-shrink: 0; background: var(--surface);
  border-right: 1px solid var(--line); padding: 26px 16px;
  display: flex; flex-direction: column; gap: 26px;
  position: sticky; top: 0; height: 100vh;
}
.marca { display: flex; align-items: center; gap: 9px; padding: 0 10px;
         font-family: 'Instrument Serif', Georgia, serif; font-size: 21px;
         letter-spacing: -.01em; color: var(--ink); }
.marca:hover { color: var(--ink); }
.vivo { width: 7px; height: 7px; border-radius: var(--r-pill); background: #3E9C6B; }
.vivo[data-parado="1"] { background: var(--faint); }

nav { display: flex; flex-direction: column; gap: 2px; }
nav a { display: flex; align-items: center; gap: 11px; padding: 9px 12px;
        border-radius: var(--r-inner); color: var(--muted); font-weight: 450; }
nav a:hover { background: var(--line-soft); color: var(--ink); }
nav a[aria-current="page"] { background: var(--soft); color: var(--accent); font-weight: 600; }
nav a svg { flex-shrink: 0; }

/* a lateral já é branca: sem a borda, o bloco não se lê como bloco */
.saldo { margin-top: auto; display: flex; flex-direction: column; gap: 9px;
         padding: 13px 12px; background: var(--paper);
         border: 1px solid var(--line); border-radius: 12px; }
.barra { height: 4px; border-radius: var(--r-pill); background: var(--line); overflow: hidden; }
.barra > div { height: 100%; background: var(--accent); border-radius: var(--r-pill); }

/* listas */
.linha { display: flex; align-items: center; gap: 14px; padding: 13px 20px;
         border-top: 1px solid var(--line-soft); }
.linha:first-child { border-top: 0; }
.ref { font-size: 12px; color: var(--faint); width: 34px; flex-shrink: 0; }
.quando { font-size: 13px; color: var(--muted); margin-left: auto; flex-shrink: 0; }
.vazio { color: var(--faint); padding: 28px 20px; font-size: 13.5px; }

/* notas: árvore à esquerda, editor à direita */
.notas { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 20px; align-items: start; }
/* a lateral fica no lugar enquanto a nota rola: a árvore está sempre à mão */
.notas-lateral { padding: 10px; display: flex; flex-direction: column; gap: 6px;
                 position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow: auto; }
.notas-editor { padding: 22px 26px; display: flex; flex-direction: column; gap: 10px;
                min-height: 60vh; }
.notas-botoes { display: flex; gap: 6px; padding: 2px 2px 8px;
                border-bottom: 1px solid var(--line-soft); }
.notas-botoes .botao { flex: 1; justify-content: center; padding: 0 10px; }
/* três botões não cabem lado a lado na lateral: o principal fica sozinho em
   cima, pasta e desenho dividem a linha de baixo */
.notas-botoes { flex-wrap: wrap; }
.notas-botoes #nova-nota { flex-basis: 100%; }
/* .botao vem depois nesta folha: as duas classes juntas para valer sobre ele */
.botao.botao-principal, .botao.botao-principal svg { color: #fff; }
.botao.botao-principal { background: var(--accent); border-color: var(--accent); font-weight: 600; }
.botao.botao-principal:hover { background: var(--accent-forte); border-color: var(--accent-forte); }
.botao-fraco { font: inherit; font-size: 12.5px; padding: 6px 12px; cursor: pointer;
               border: 1px solid var(--line); border-radius: var(--r-pill);
               background: var(--surface); color: var(--muted); }
.botao-fraco:hover { color: var(--ink); border-color: var(--faint); }
.campo-busca { font: inherit; font-size: 13px; padding: 7px 13px; width: 230px;
               border: 1px solid var(--line); border-radius: var(--r-pill);
               background: var(--surface); }
.criar { display: flex; flex-direction: column; gap: 4px; padding: 4px 2px; }
.criar .dica { font-size: 11px; color: var(--faint); }
.criar input { font: inherit; font-size: 13px; padding: 7px 10px; width: 100%;
               border: 1px solid var(--line); border-radius: var(--r-inner); }
.erro { font-size: 12px; color: var(--accent); }
.arvore { display: flex; flex-direction: column; gap: 1px; font-size: 13.5px; }
.arvore summary { list-style: none; cursor: pointer; padding: 6px 8px;
                  border-radius: var(--r-inner); color: var(--ink); font-weight: 500;
                  display: flex; align-items: center; gap: 6px; }
.arvore summary::-webkit-details-marker { display: none; }
.arvore summary::before { content: "›"; color: var(--faint); width: 10px;
                          transition: transform .12s; }
.arvore details[open] > summary::before { transform: rotate(90deg); }
.arvore summary:hover, .arvore .arquivo:hover { background: var(--line-soft); }
.arvore .conta { margin-left: auto; font-size: 11px; color: var(--faint); }
.arvore .filhos { padding-left: 14px; border-left: 1px solid var(--line-soft);
                  margin-left: 12px; display: flex; flex-direction: column; gap: 1px; }
.arvore .arquivo { display: flex; align-items: center; gap: 7px; padding: 6px 8px;
                   border-radius: var(--r-inner); color: var(--muted); }
.arvore .arquivo > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* ícone de pasta e de nota: fracos, só para o olho separar um do outro */
.arvore summary > svg, .arvore .arquivo > svg { flex-shrink: 0; color: var(--faint); }
.arvore .arquivo[aria-current="page"] > svg { color: var(--accent); }
.arvore-topo { display: flex; align-items: center; justify-content: space-between; gap: 6px;
               padding: 8px 8px 2px; border-top: 1px solid var(--line-soft); margin-top: 2px; }
.arvore-topo .eyebrow { margin: 0; }
.arvore-ferramentas { display: flex; gap: 2px; }
.ferramenta { display: inline-flex; align-items: center; justify-content: center; width: 26px;
  height: 26px; border: 0; border-radius: 6px; background: none; color: var(--faint);
  cursor: pointer; }
.ferramenta:hover { background: var(--line-soft); color: var(--ink); }
.ferramenta:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.filtro-arvore { font: inherit; font-size: 12.5px; margin: 4px 2px 4px; padding: 6px 10px;
  border: 1px solid var(--line); border-radius: var(--r-inner); background: var(--surface);
  color: var(--ink); }
.filtro-arvore:focus { outline: none; border-color: var(--faint); }
.filtro-vazio { padding: 2px 8px; }
/* arrastando uma nota: ela fica apagada, e a pasta sob ela é marcada */
.arvore .arquivo.arrastando { opacity: .45; }
.arvore summary.alvo-soltar, .arvore-topo.alvo-soltar { background: var(--soft);
  outline: 2px dashed var(--accent); outline-offset: -2px; border-radius: var(--r-inner); }
.arvore .arquivo[aria-current="page"] { background: var(--soft); color: var(--accent);
                                         font-weight: 600; }
.arvore .achado { display: block; white-space: normal; }
/* a palavra buscada, no trecho do resultado e na nota aberta por ele */
.arvore .trecho mark, .previa mark.achado-busca { color: inherit; border-radius: 2px;
  padding: 0 1px; background: color-mix(in srgb, #E8B931 40%, transparent); }
.arvore .onde, .arvore .trecho { display: block; font-size: 11.5px; color: var(--faint);
                                 font-weight: 400; margin-top: 2px; }
.arvore .pasta-vazia { font-size: 12px; color: var(--faint); padding: 4px 8px; }
.limpar { font-size: 12.5px; padding: 8px; }
.editor-topo { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
               flex-wrap: wrap; }
.editor-acoes { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
                justify-content: flex-end; }
.separador { width: 1px; height: 20px; background: var(--borda); margin: 0 2px; }

/* os botões da nota: 32px de altura, ícone e texto, borda que se vê */
.botao, .privada { font: inherit; font-size: 13px; height: 32px; padding: 0 12px;
                   display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
                   border: 1px solid var(--borda); border-radius: var(--r-pill);
                   background: var(--surface); color: var(--ink); cursor: pointer;
                   transition: background .12s, border-color .12s, color .12s; }
.botao svg, .privada svg, .modo svg { flex-shrink: 0; color: var(--muted); }
.botao:hover, .privada:hover { background: var(--line-soft); border-color: var(--faint); }
.botao:focus-visible, .modo:focus-visible, .privada:has(input:focus-visible) {
  outline: 2px solid var(--accent); outline-offset: 2px; }
.botao-perigo:hover, .botao-perigo:hover svg { color: var(--accent); }
.botao-perigo:hover { border-color: var(--accent); background: var(--soft); }
/* armado: o segundo clique apaga. Cheio, para não passar por engano */
.botao-perigo[data-armado], .botao-perigo[data-armado] svg { color: #fff; }
.botao-perigo[data-armado] { background: var(--accent); border-color: var(--accent); }
.botao-perigo .rotulo { min-width: 46px; }

/* privada: a caixa vira uma chave; marcada, fica na cor de alerta */
.privada { color: var(--muted); user-select: none; }
.privada input { position: absolute; opacity: 0; width: 1px; height: 1px; pointer-events: none; }
.privada:has(input:checked) { background: var(--soft); border-color: var(--accent);
                              color: var(--accent); font-weight: 600; }
.privada:has(input:checked) svg { color: var(--accent); }
.editor-meta { margin: 0; font-size: 11.5px; color: var(--faint); }
#estado[data-estado="pendente"], #estado[data-estado="salvando"] { color: var(--muted); }
#estado[data-estado="erro"] { color: var(--accent); }
.conflito { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px;
            background: var(--soft); color: var(--accent); border-radius: var(--r-inner);
            font-size: 13px; }
/* display:flex numa classe vence o [hidden] do navegador; sem isto o campo de
   criar e o aviso de conflito aparecem vazios na tela */
[hidden] { display: none !important; }
#editor { flex: 1; min-height: 58vh; width: 100%; resize: vertical; padding: 14px 16px;
          border: 1px solid var(--line); border-radius: var(--r-inner); background: var(--paper);
          font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 13.5px;
          line-height: 1.7; color: var(--ink); tab-size: 2; }
#editor:focus { outline: none; border-color: var(--faint); background: var(--surface); }

/* editar, lado a lado, ler */
.modos { display: flex; border: 1px solid var(--borda); border-radius: var(--r-pill);
         overflow: hidden; height: 32px; }
.modo { font: inherit; font-size: 13px; padding: 0 12px; border: 0; cursor: pointer;
        display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
        background: var(--surface); color: var(--muted); transition: background .12s; }
.modo:hover { background: var(--line-soft); color: var(--ink); }
.modo + .modo { border-left: 1px solid var(--borda); }
.modo[aria-pressed="true"] { background: var(--soft); color: var(--accent); font-weight: 600; }
.modo[aria-pressed="true"] svg { color: var(--accent); }
/* tela estreita: os modos ficam só no ícone, com o nome no title */
@media (max-width: 1280px) { .modo span { display: none; } .modo { padding: 0 10px; } }
.area { flex: 1; display: grid; gap: 16px; min-height: 58vh; border-radius: var(--r-inner); }
/* arrastando um arquivo por cima: a área inteira aceita */
.area.soltando { outline: 2px dashed var(--accent); outline-offset: 4px; background: var(--soft); }
.area[data-modo="dividido"] { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.area[data-modo="editar"] .previa, .area[data-modo="ler"] .campo,
.area[data-modo="vivo"] .campo { display: none; }

/* cores no editor: o campo fica transparente por cima de uma cópia colorida
   do mesmo texto (#realce). Os dois precisam quebrar linha no mesmo lugar:
   mesma fonte, mesmo espaçamento e o mesmo espaço reservado para a barra */
.campo { position: relative; min-width: 0; display: flex; }
.realce { position: absolute; inset: 0; margin: 0; overflow: hidden; pointer-events: none;
          padding: 14px 16px; border: 1px solid transparent; border-radius: var(--r-inner);
          background: var(--paper); white-space: pre-wrap; overflow-wrap: break-word;
          font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 13.5px;
          line-height: 1.7; color: var(--ink); tab-size: 2; scrollbar-gutter: stable; }
#editor.colorido { color: transparent; caret-color: var(--ink); background: transparent;
                   position: relative; scrollbar-gutter: stable; }
#editor.colorido::selection { background: rgba(196, 67, 43, .18); }
#editor.colorido:focus { background: transparent; }
.campo:focus-within .realce { background: var(--surface); }
.realce .r-titulo { color: var(--accent); font-weight: 500; }
.realce .r-marca { color: var(--faint); }
.realce .r-forte { font-weight: 600; }
.realce .r-italico { font-style: italic; }
.realce .r-codigo { color: #3F7A54; }
.realce .r-link { color: var(--accent); }
.realce .r-url { color: var(--muted); }
.realce .r-citacao { color: var(--muted); }
.realce .r-front { color: var(--faint); }
.realce .r-tag { color: #2B5FA8; }
.area[data-modo="ler"] .previa, .area[data-modo="vivo"] .previa {
  border-color: transparent; background: transparent; padding: 4px 2px; }

/* a prévia: leitura confortável, mesma família da página */
.previa { min-width: 0; overflow: auto; max-height: 70vh; padding: 14px 18px;
          border: 1px solid var(--line-soft); border-radius: var(--r-inner);
          font-size: 14.5px; line-height: 1.7; color: var(--ink); overflow-wrap: anywhere; }
.area[data-modo="ler"] .previa { max-height: none; max-width: 760px; }
/* ao vivo: clicar num bloco troca ele pelo markdown dele, no mesmo lugar e
   na mesma letra; o espaço vazio embaixo também aceita clique (escreve no fim) */
.area[data-modo="vivo"] .previa { max-height: none; max-width: 760px; min-height: 58vh;
                                  cursor: text; padding: 4px 10px; }
/* o padding acima é onde cabem a sobra de 8px do bloco aberto e a sombra
   do bloco sob o mouse: sem ele, abrir um bloco criava rolagem para o lado */
.bloco-vivo { display: block; width: calc(100% + 16px); margin: -4px -8px .9em; padding: 4px 8px;
              border: 0; border-radius: var(--r-inner); background: var(--line-soft);
              font: inherit; line-height: inherit; color: var(--ink); resize: none;
              overflow: hidden; tab-size: 2; }
.bloco-vivo:focus { outline: none; box-shadow: inset 2px 0 0 var(--accent); }
.bloco-pendente { white-space: pre-wrap; color: var(--muted); margin: 0 0 .9em; }
/* o bloco sob o mouse ganha um fundo leve: mostra o que o clique vai abrir.
   Sombra, e não padding, para nada sair do lugar */
.area[data-modo="vivo"] .previa [data-bloco]:hover { background: var(--line-soft);
  box-shadow: 0 0 0 6px var(--line-soft); border-radius: 2px; }
.area[data-modo="vivo"] .previa pre:has(> code[data-bloco]:hover) { box-shadow: 0 0 0 3px var(--line); }
/* a dica embaixo da nota; enquanto um bloco está aberto, os atalhos dele */
.area[data-modo="vivo"] .previa::after { display: block; margin-top: 18px; font-size: 12px;
  color: var(--faint); content: "clique num bloco para editar · clique aqui embaixo para escrever no fim"; }
.area[data-modo="vivo"] .previa:empty::after { margin-top: 0; font-size: 14.5px;
  content: "Nota vazia. Clique aqui para começar a escrever."; }
.area[data-modo="vivo"] .previa:has(.bloco-vivo)::after {
  content: "/ comandos · Esc sai · Shift+Enter bloco novo embaixo · ↑ ↓ nas pontas muda de bloco · Ctrl+B negrito · Ctrl+I itálico · Ctrl+K link · [[ liga a outra nota"; }
.previa > :first-child { margin-top: 0; }
.previa h1, .previa h2, .previa h3 { font-weight: 600; line-height: 1.3; margin: 1.3em 0 .5em; }
.previa h1 { font-size: 22px; } .previa h2 { font-size: 18px; } .previa h3 { font-size: 15.5px; }
.previa p, .previa ul, .previa ol, .previa pre, .previa table, .previa blockquote { margin: 0 0 .9em; }
.previa ul, .previa ol { padding-left: 1.4em; }
.previa li.tarefa { list-style: none; margin-left: -1.3em; }
/* a feita sai riscada e apagada; as subtarefas embaixo dela não */
.previa li.feita > .tarefa-texto, .previa li.feita > p > .tarefa-texto {
  color: var(--faint); text-decoration: line-through; text-decoration-color: var(--faint); }
.previa li.tarefa input { margin: 0 6px 0 0; vertical-align: -1px; cursor: pointer;
                          accent-color: var(--accent); }
.previa code { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12.5px;
               background: var(--line-soft); padding: 1px 5px; border-radius: 5px; }
.previa pre { background: var(--line-soft); padding: 12px 14px; border-radius: var(--r-inner);
              overflow: auto; }
.previa pre code { background: none; padding: 0; }
.previa blockquote { border-left: 3px solid var(--line); padding-left: 12px; color: var(--muted); }
/* callouts (> [!tipo]): caixa tingida pela cor do tipo, título com ícone.
   Tipo desconhecido fica com a cor da nota */
.previa .callout { --cor: #2B5FA8; border: 0; border-radius: var(--r-inner); padding: 10px 14px;
  background: color-mix(in srgb, var(--cor) 9%, transparent); color: var(--ink); }
.previa .callout[data-callout="note"] { --cor: #2B5FA8; }
.previa .callout[data-callout="abstract"] { --cor: #1F8A8A; }
.previa .callout[data-callout="info"] { --cor: #2B5FA8; }
.previa .callout[data-callout="todo"] { --cor: #2B5FA8; }
.previa .callout[data-callout="tip"] { --cor: #1F8A8A; }
.previa .callout[data-callout="success"] { --cor: #3F7A54; }
.previa .callout[data-callout="question"] { --cor: #B7791F; }
.previa .callout[data-callout="warning"] { --cor: #B7791F; }
.previa .callout[data-callout="failure"] { --cor: #C4432B; }
.previa .callout[data-callout="danger"] { --cor: #C4432B; }
.previa .callout[data-callout="bug"] { --cor: #C4432B; }
.previa .callout[data-callout="example"] { --cor: #7A4FB5; }
.previa .callout[data-callout="quote"] { --cor: #6B7280; }
.previa .callout-titulo { display: flex; align-items: center; gap: 8px; font-weight: 600;
  color: var(--cor); }
.previa .callout-titulo svg { flex: none; }
.previa .callout > .callout-titulo + * { margin-top: 6px; }
.previa .callout > :last-child { margin-bottom: 0; }
.previa details.callout > summary { cursor: pointer; list-style: none; }
.previa details.callout > summary::-webkit-details-marker { display: none; }
.previa details.callout > summary::after { content: "›"; margin-left: auto; font-size: 18px;
  line-height: 1; transition: transform .15s; }
.previa details.callout[open] > summary::after { transform: rotate(90deg); }
.previa table { border-collapse: collapse; font-size: 13px; }
.previa th, .previa td { border: 1px solid var(--line); padding: 5px 10px; text-align: left; }
.previa hr { border: 0; border-top: 1px solid var(--line); margin: 1.4em 0; }
.previa .wikilink { border-bottom: 1px solid var(--soft); }
/* #tag: etiqueta azul, a mesma cor da tag no editor; leva às notas com ela */
.previa a.tag { display: inline-block; padding: 0 7px; border-radius: var(--r-pill);
  font-size: .88em; line-height: 1.6; text-decoration: none; color: #2B5FA8;
  background: color-mix(in srgb, #2B5FA8 10%, transparent); }
.previa a.tag:hover { background: color-mix(in srgb, #2B5FA8 18%, transparent); }
.previa .wikilink.quebrado { color: var(--faint); border-bottom: 1px dashed var(--faint);
                             cursor: pointer; }
.previa .wikilink.quebrado:hover { color: var(--accent); border-color: var(--accent); }
.previa .imagem-externa::before { content: "▧ "; color: var(--faint); }
.previa .anexo { color: var(--muted); }
.previa .anexo-imagem { max-width: 100%; height: auto; border-radius: var(--r-inner);
                        display: block; margin: 6px 0; }
.previa .anexo-midia { max-width: 100%; display: block; margin: 6px 0; }
.previa .anexo::before { content: "⎘ "; color: var(--faint); }
.propriedades { display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px;
                margin: 0 0 16px; padding: 10px 12px; border-radius: var(--r-inner);
                background: var(--paper); border: 1px solid var(--line-soft);
                font-size: 12.5px; }
.propriedades dt { color: var(--faint); font-family: 'IBM Plex Mono', ui-monospace, monospace; }
.propriedades dd { margin: 0; color: var(--muted); overflow-wrap: anywhere; }

/* renomear */
.titulo-nota { margin: 0; font-size: 20px; font-weight: 600; cursor: text;
               border-radius: 6px; padding: 0 4px; margin-left: -4px; }
.titulo-nota:hover { background: var(--line-soft); }
.renomear { display: flex; flex-direction: column; gap: 3px; }
.renomear input { font: inherit; font-size: 15px; font-weight: 600; padding: 4px 8px;
                  width: min(520px, 100%); border: 1px solid var(--faint);
                  border-radius: 8px; }
.renomear .dica { font-size: 11px; color: var(--faint); }

/* renomear pasta: em tela de toque o lápis fica à vista, fraco — não há
   "passar o mouse" para fazê-lo aparecer */
.arvore .nome-pasta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nova-na-pasta, .novo-desenho-na-pasta, .renomear-pasta, .apagar-pasta { font: inherit; font-size: 11.5px; border: 0; background: none;
                                 min-width: 24px; height: 24px; padding: 0 5px;
                                 display: inline-flex; align-items: center;
                                 justify-content: center; gap: 4px; color: var(--muted);
                                 cursor: pointer; opacity: .45; border-radius: 6px;
                                 flex-shrink: 0; }
/* com mouse, somem até você passar por cima da pasta: dez pastas com dois
   ícones cada viram ruído. O apagar esperando o segundo clique fica à vista */
@media (hover: hover) {
  .nova-na-pasta, .novo-desenho-na-pasta, .renomear-pasta, .apagar-pasta {
    opacity: 0; transition: opacity .12s; }
}
.arvore summary:hover .nova-na-pasta, .nova-na-pasta:focus-visible,
.arvore summary:hover .novo-desenho-na-pasta, .novo-desenho-na-pasta:focus-visible,
.arvore summary:hover .renomear-pasta, .renomear-pasta:focus-visible,
.arvore summary:hover .apagar-pasta, .apagar-pasta:focus-visible,
.apagar-pasta[data-armado] { opacity: 1; }
.nova-na-pasta:focus-visible, .novo-desenho-na-pasta:focus-visible,
.renomear-pasta:focus-visible, .apagar-pasta:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 1px; }
.nova-na-pasta:hover, .novo-desenho-na-pasta:hover, .renomear-pasta:hover { color: var(--ink); background: var(--surface); }
.apagar-pasta:hover { color: var(--accent); background: var(--surface); }
/* armado: o segundo clique manda a pasta para a lixeira */
.apagar-pasta[data-armado] { opacity: 1; color: #fff; background: var(--accent); font-weight: 600; }
.apagar-pasta .rotulo:empty { display: none; }
.renomear-pasta-form { display: flex; flex-direction: column; gap: 3px; padding: 4px 6px; }
.renomear-pasta-form input { font: inherit; font-size: 13px; padding: 5px 8px; width: 100%;
                             border: 1px solid var(--faint); border-radius: 8px; }

/* visão geral do vault */
.atalho-visao { display: flex; align-items: center; gap: 8px; font-size: 13px;
                padding: 7px 8px; margin: 0 0 2px;
                border-radius: var(--r-inner); color: var(--muted); }
.atalho-visao:hover { background: var(--line-soft); color: var(--ink); }
.atalho-visao svg, .aviso-quebrados svg { flex-shrink: 0; }
/* aberto: fica no lugar, marcado como a nota aberta na árvore */
.atalho-visao[aria-current="page"] { background: var(--soft); color: var(--accent); font-weight: 600; }
.aviso-quebrados[aria-current="page"] { background: var(--accent); color: #fff; }
.visao { display: flex; flex-direction: column; gap: 14px; }
.visao-numeros { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.visao-dupla { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.nota-grafico { margin: 8px 0 0; font-size: 11.5px; color: var(--faint); }
.orfas { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; }
@media (max-width: 1100px) {
  .visao-numeros { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .visao-dupla { grid-template-columns: 1fr; }
}

/* grafo */
.atalhos { display: flex; flex-direction: column; gap: 1px; margin-bottom: 2px; }
button.atalho-visao { width: 100%; border: 0; background: none; font: inherit; font-size: 13px;
  text-align: left; cursor: pointer; }
.atalho-visao kbd { margin-left: auto; font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 10.5px; color: var(--faint); }

/* abrir nota rápido (Ctrl+O): a caixa no meio da tela, por cima de tudo */
.seletor-fundo { position: fixed; inset: 0; z-index: 30; display: flex; justify-content: center;
  align-items: flex-start; padding: 14vh 16px 0; background: rgba(21, 23, 28, .18); }
.seletor { width: min(560px, 100%); background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-inner); box-shadow: 0 16px 48px rgba(21, 23, 28, .18); overflow: hidden; }
.seletor input { width: 100%; box-sizing: border-box; border: 0; border-bottom: 1px solid var(--line);
  padding: 14px 16px; font: inherit; font-size: 15px; color: var(--ink); background: transparent;
  outline: none; }
.seletor-lista { list-style: none; margin: 0; padding: 6px; max-height: 50vh; overflow-y: auto; }
.seletor-lista li { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 7px 10px; border-radius: 7px; cursor: pointer; font-size: 14px; }
.seletor-lista li[aria-selected="true"] { background: var(--soft); color: var(--accent); }
.seletor-lista li.vazio { cursor: default; color: var(--faint); }
.seletor-lista .onde { font-size: 11.5px; color: var(--faint); min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.seletor .dica { margin: 0; padding: 8px 16px; font-size: 11.5px; color: var(--faint);
  border-top: 1px solid var(--line); }
.grafo-topo { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.grafo-topo .onde { font-size: 11.5px; color: var(--faint); }
.grafo { width: 100%; height: 66vh; background: var(--paper); border-radius: var(--r-inner);
         border: 1px solid var(--line-soft); cursor: grab; touch-action: none;
         user-select: none; }
.grafo:active { cursor: grabbing; }
.grafo line { stroke: #D9DCE2; stroke-width: 1; transition: opacity .12s; }
.grafo text { font-size: 11px; fill: var(--muted); text-anchor: middle; paint-order: stroke;
              stroke: var(--paper); stroke-width: 3px; pointer-events: none;
              font-family: 'Public Sans', system-ui, sans-serif; }
.grafo a.no circle { stroke: var(--paper); stroke-width: 1.5; transition: opacity .12s; }
.grafo a.no:hover circle { stroke: var(--ink); }
.grafo a.atual circle { stroke: var(--ink); stroke-width: 2.5; }
.grafo.focado a.no:not(.perto), .grafo.focado line:not(.perto) { opacity: .15; }
.grafo.focado line.perto { stroke: var(--accent); stroke-width: 1.5; }
.grafo text.so-perto { display: none; }
.ao-redor { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 16px;
            align-items: start; }
.ao-redor > :only-child { grid-column: 1 / -1; }
.local { border-top: 1px solid var(--line-soft); padding-top: 14px; margin-top: 6px; }
.grafo.local { height: 300px; margin-top: 10px; touch-action: pan-y pinch-zoom; }
.grafo a.no:focus { outline: none; }
.dica-grafo { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 6px; }
.grafo a.no:focus circle { stroke: var(--accent); stroke-width: 3; }
@media (max-width: 1100px) { .ao-redor { grid-template-columns: 1fr; } }
.grafo.focado a.perto text.so-perto { display: inline; }

/* links quebrados */
.aviso-quebrados { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500;
                   padding: 7px 8px; margin: 0 0 4px;
                   border-radius: var(--r-inner); background: var(--soft); color: var(--accent); }
.quebrados-topo { padding: 8px 8px 4px; border-top: 1px solid var(--line-soft); margin-top: 2px; }
.quebrados-topo .eyebrow { margin: 0 0 2px; }
.quebrados-resumo { margin: 0; font-size: 13px; font-weight: 600; color: var(--ink); }
.quebrados-explica { margin: 3px 0 0; font-size: 11.5px; line-height: 1.45; color: var(--faint); }
/* cada nota que falta é um cartão: nome e criar em cima, quem cita embaixo */
.quebrado-item { display: flex; flex-direction: column; gap: 6px; padding: 10px;
                 border: 1px solid var(--line-soft); border-radius: var(--r-inner);
                 background: var(--surface); font-size: 13px; }
.quebrado-item + .quebrado-item { margin-top: 6px; }
.quebrado-alvo { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.quebrado-nome { min-width: 0; }
.quebrado-nome strong { display: block; overflow-wrap: anywhere; }
.quebrado-nome .onde { font-size: 11px; color: var(--faint); }
.criar-quebrado { display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
                  padding: 4px 10px; color: var(--accent); border-color: var(--soft);
                  background: var(--soft); font-weight: 600; }
.criar-quebrado:hover { color: #fff; background: var(--accent); border-color: var(--accent); }
/* "ligar a X": a nota parecida que já existe, para um nome digitado errado */
.quebrado-sugestao { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.quebrado-sugestao .onde { font-size: 11px; color: var(--faint); }
.ligar-quebrado { display: inline-flex; align-items: center; gap: 5px; font: inherit;
  font-size: 12px; padding: 3px 9px; border: 1px solid var(--line); border-radius: var(--r-pill);
  background: var(--surface); color: var(--muted); cursor: pointer; }
.ligar-quebrado:hover { color: var(--ink); border-color: var(--faint); }
.ligar-quebrado strong { color: var(--ink); }
.quebrado-citacoes { list-style: none; margin: 0; padding: 6px 0 0; display: flex;
                     flex-direction: column; gap: 6px; border-top: 1px dashed var(--line); }
.quebrado-citacoes a { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px;
                       font-weight: 500; }
.quebrado-citacoes a svg { color: var(--faint); flex-shrink: 0; }
.quebrado-citacoes a:hover span { text-decoration: underline; }
.quebrado-citacoes .vezes { font-size: 11px; color: var(--faint); }
.quebrado-citacoes .trecho { display: block; margin-top: 1px; font-size: 11.5px; line-height: 1.45;
                             color: var(--muted); overflow-wrap: anywhere; }
.quebrado-citacoes .trecho mark { color: var(--accent); background: none; font-weight: 600;
                                  border-bottom: 1px dashed var(--accent); }

/* o link aonde a lista de quebrados levou: pisca e some devagar */
@keyframes destaque { from { background: #FBE3DC; box-shadow: 0 0 0 4px #FBE3DC; }
                      to { background: transparent; box-shadow: 0 0 0 4px transparent; } }
.previa .destaque { animation: destaque 2.4s ease-out; border-radius: 4px; }

/* backlinks */
.backlinks { border-top: 1px solid var(--line-soft); padding-top: 14px; margin-top: 6px; }
.backlinks > ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid;
                  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.backlinks > ul > li { padding: 10px 12px; border: 1px solid var(--line-soft);
                       border-radius: var(--r-inner); font-size: 13.5px; min-width: 0; }
.backlinks a { font-weight: 600; }
.backlinks .onde { display: block; font-size: 11px; color: var(--faint); margin-top: 2px; }
.backlinks .trechos { margin: 6px 0 0; padding: 0; list-style: none; font-size: 12.5px;
                      color: var(--muted); line-height: 1.5; }
.backlinks .trechos li { overflow-wrap: anywhere; }
.backlinks .trechos li + li { margin-top: 4px; }
.vazio-curto { margin: 6px 0 0; font-size: 13px; color: var(--faint); }

/* autocompletar [[ e os comandos do / (a lista longa rola) */
.sugestoes { position: absolute; z-index: 10; margin: 0; padding: 4px; list-style: none;
             min-width: 240px; max-width: 360px; max-height: 320px; overflow-y: auto;
             background: var(--surface);
             border: 1px solid var(--line); border-radius: var(--r-inner);
             box-shadow: 0 6px 20px rgba(21,23,28,.10); font-size: 13px; }
.sugestoes li { padding: 6px 9px; border-radius: 7px; cursor: pointer;
                display: flex; flex-direction: column; }
.sugestoes li[aria-selected="true"] { background: var(--soft); color: var(--accent); }
.sugestoes .onde { font-size: 11px; color: var(--faint); }

/* uma tela de PC, mas não quebrada num monitor estreito */
@media (max-width: 1100px) {
  .lateral { width: 68px; padding: 22px 10px; }
  .lateral .rotulo, .marca span, .saldo { display: none; }
  nav a { justify-content: center; padding: 11px 0; }
  main { padding: 28px 24px; }
  .notas { grid-template-columns: 220px minmax(0, 1fr); }
  .area[data-modo="dividido"] { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .notas { grid-template-columns: 1fr; }
  .notas-lateral { max-height: 40vh; }
}

/* a tela de desenho: barra fina em cima, o Excalidraw no resto */
.desenho-corpo { height: 100vh; margin: 0; display: flex; flex-direction: column; overflow: hidden; }
.desenho-barra { display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  border-bottom: 1px solid var(--line); background: var(--surface); }
.desenho-nome { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; font-size: 14px; }
.desenho-pasta { color: var(--muted); }
.desenho-estado { font-size: 12.5px; color: var(--muted); white-space: nowrap; }
.desenho-estado.erro { color: var(--accent); }
.desenho-editor { flex: 1; min-height: 0; position: relative; }
.desenho-conflito { border-radius: 0; }
/* "Web Embed" e "Mermaid to Excalidraw" não funcionam aqui (a CSP barra
   iframe de fora; o mermaid ficou fora do pacote). O Excalidraw dá o mesmo
   data-testid aos dois. Quatro seletores: o excalidraw.css vem depois com
   três (.excalidraw .dropdown-menu .dropdown-menu-item-base). A div antes do
   mermaid é o título "Generate", que ficaria sozinho */
.desenho-editor .excalidraw .dropdown-menu [data-testid="toolbar-embeddable"],
.desenho-editor .excalidraw .dropdown-menu div:has(+ [data-testid="toolbar-embeddable"]) {
  display: none; }
/* "Procurar bibliotecas" abre o site do Excalidraw com o endereço daqui, e a
   volta (baixar a biblioteca escolhida) a CSP barra: o caminho não leva a nada */
.desenho-editor .excalidraw .library-menu-control-buttons .library-menu-browse-button {
  display: none; }

/* ![[desenho.excalidraw]] na nota: a prévia leva ao desenho */
.desenho-embutido { display: inline-block; max-width: 100%; border: 1px solid var(--line);
  border-radius: var(--r-inner); background: #fff; line-height: 0; }
.desenho-embutido img { max-width: 100%; height: auto; border-radius: var(--r-inner); }
.desenho-embutido:hover { border-color: var(--faint); }
.desenho-embutido.sem-previa { line-height: 1.4; padding: 10px 14px; font-size: 13px;
  color: var(--muted); background: var(--line-soft); }
"""
