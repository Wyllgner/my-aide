"""O HTML. Sem framework de front, sem build: é o dado de uma pessoa."""

from __future__ import annotations

TOKENS = """
  --paper:#FBFBFC; --surface:#FFF; --ink:#15171C; --muted:#6C727E;
  --faint:#9CA2AD; --line:#EDEFF2; --accent:#C4432B; --soft:#FCF1EE;
  --r-card:16px; --r-inner:10px;
"""


def esqueleto(titulo: str = "my-aide", corpo: str = "") -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Public+Sans:wght@400;450;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{{TOKENS}}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink);
       font-family: 'Public Sans', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }}
.h1 {{ font-family: 'Instrument Serif', Georgia, serif; font-weight: 400;
      font-size: 34px; letter-spacing: -.015em; margin: 0; }}
.mono {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.card {{ background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-card); box-shadow: 0 1px 2px rgba(21,23,28,.04); }}
.eyebrow {{ font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
           color: var(--faint); font-weight: 600; }}
main {{ padding: 34px 40px; }}
</style>
</head>
<body>
<main>{corpo or _vazio()}</main>
</body>
</html>
"""


def _vazio() -> str:
    return """
<p class="eyebrow" style="margin: 0 0 6px;">127.0.0.1 · só leitura</p>
<h1 class="h1">my-aide</h1>
<p style="margin: 18px 0 0; color: var(--muted); max-width: 46ch; line-height: 1.6;">
  O esqueleto está de pé. As telas entram nas próximas etapas.
</p>
"""
