"""A folha de estilo, servida uma vez em /app.css.

Separada do HTML porque é a mesma em todas as telas — repeti-la em cada página
faria o navegador reprocessar o mesmo texto a cada clique.
"""

from __future__ import annotations

CSS = """
:root {
  --paper:#FBFBFC; --surface:#FFFFFF; --ink:#15171C; --muted:#6C727E;
  --faint:#9CA2AD; --line:#EDEFF2; --line-soft:#F4F5F7;
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
.notas-lateral { padding: 10px; display: flex; flex-direction: column; gap: 6px;
                 max-height: 78vh; overflow: auto; }
.notas-editor { padding: 22px 26px; display: flex; flex-direction: column; gap: 10px;
                min-height: 60vh; }
.notas-botoes { display: flex; gap: 6px; padding: 2px 2px 6px;
                border-bottom: 1px solid var(--line-soft); }
.botao-fraco { font: inherit; font-size: 12.5px; padding: 6px 12px; cursor: pointer;
               border: 1px solid var(--line); border-radius: var(--r-pill);
               background: var(--surface); color: var(--muted); }
.botao-fraco:hover { color: var(--ink); border-color: var(--faint); }
#apagar[data-armado] { color: var(--accent); border-color: var(--accent); }
.campo-busca { font: inherit; font-size: 13px; padding: 7px 13px; width: 230px;
               border: 1px solid var(--line); border-radius: var(--r-pill);
               background: var(--surface); }
.criar { display: flex; flex-direction: column; gap: 4px; padding: 4px 2px; }
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
.arvore .arquivo { display: block; padding: 6px 8px; border-radius: var(--r-inner);
                   color: var(--muted); overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; }
.arvore .arquivo[aria-current="page"] { background: var(--soft); color: var(--accent);
                                         font-weight: 600; }
.arvore .achado { white-space: normal; }
.arvore .onde, .arvore .trecho { display: block; font-size: 11.5px; color: var(--faint);
                                 font-weight: 400; margin-top: 2px; }
.arvore .pasta-vazia { font-size: 12px; color: var(--faint); padding: 4px 8px; }
.limpar { font-size: 12.5px; padding: 8px; }
.editor-topo { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.editor-acoes { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.privada { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted);
           cursor: pointer; }
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

/* uma tela de PC, mas não quebrada num monitor estreito */
@media (max-width: 1100px) {
  .lateral { width: 68px; padding: 22px 10px; }
  .lateral .rotulo, .marca span, .saldo { display: none; }
  nav a { justify-content: center; padding: 11px 0; }
  main { padding: 28px 24px; }
  .notas { grid-template-columns: 220px minmax(0, 1fr); }
}
@media (max-width: 760px) {
  .notas { grid-template-columns: 1fr; }
  .notas-lateral { max-height: 40vh; }
}
"""
