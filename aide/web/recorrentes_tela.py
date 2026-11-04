"""O cartão dos gastos fixos na tela de gastos: só a lista.

Cadastrar, mudar e encerrar são pela conversa.
"""

from __future__ import annotations

from html import escape

from aide.tools.expenses import formatar, por_extenso


def _detalhe(fixo: dict) -> str:
    partes = [f'dia {fixo["dia"]}', por_extenso(fixo["method"])]
    if fixo["category"]:
        partes.append(fixo["category"] + (f' · {fixo["tag"]}' if fixo["tag"] else ""))
    if fixo["proxima"]:
        dia = fixo["proxima"]
        partes.append(f"próxima em {dia[8:10]}/{dia[5:7]}/{dia[:4]}")
    return " · ".join(partes)


def _linha(fixo: dict) -> str:
    return (f'<div class="fixo-linha">'
            f'<span class="fixo-nome">{escape(fixo["description"])}'
            f'<span class="fixo-detalhe">{escape(_detalhe(fixo))}</span></span>'
            f'<span class="mono fixo-valor">{escape(fixo["valor"])}</span></div>')


def cartao_recorrentes(ctx, registry) -> str:
    fixos = registry.call("expenses.recurring", {}, ctx).data or []
    if fixos:
        resumo = f'{formatar(sum(f["cents"] for f in fixos))} por mês'
        corpo = "".join(_linha(f) for f in fixos)
    else:
        resumo = ""
        corpo = ('<p style="margin:0;font-size:12.5px;color:var(--faint);line-height:1.5">'
                 'Nada cadastrado. Para cadastrar assinatura ou conta fixa, diga no Telegram '
                 '"o claude é 110 todo dia 5".</p>')
    return ('<div class="card" style="padding:16px 20px;margin-top:16px">'
            '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:10px">'
            '<span class="eyebrow">Gastos fixos</span>'
            f'<span style="font-size:12.5px;color:var(--muted)">{escape(resumo)}</span></div>'
            f'{corpo}</div>')
