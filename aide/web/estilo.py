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

/* uma tela de PC, mas não quebrada num monitor estreito */
@media (max-width: 1100px) {
  .lateral { width: 68px; padding: 22px 10px; }
  .lateral .rotulo, .marca span, .saldo { display: none; }
  nav a { justify-content: center; padding: 11px 0; }
  main { padding: 28px 24px; }
}
"""
