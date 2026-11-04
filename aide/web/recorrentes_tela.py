"""O cartão dos gastos fixos na tela de gastos. Quem envia é o /gastos.js."""

from __future__ import annotations

from html import escape

from aide.tools.expenses import formatar, por_extenso
from aide.web.icones import icone


def _detalhe(fixo: dict) -> str:
    partes = [f'dia {fixo["dia"]}', por_extenso(fixo["method"])]
    if fixo["category"]:
        partes.append(fixo["category"] + (f' · {fixo["tag"]}' if fixo["tag"] else ""))
    if fixo["proxima"]:
        dia = fixo["proxima"]
        partes.append(f"próxima em {dia[8:10]}/{dia[5:7]}/{dia[:4]}")
    return " · ".join(partes)


def _linha(fixo: dict) -> str:
    # o valor sem "R$": é o que a pessoa digitaria, e a tool entende os dois
    valor = fixo["valor"].replace("R$", "").strip()
    return (f'<form class="fixo-linha" data-id="{fixo["id"]}">'
            f'<span class="fixo-nome">{escape(fixo["description"])}'
            f'<span class="fixo-detalhe">{escape(_detalhe(fixo))}</span></span>'
            f'<label class="teto-rotulo">valor<input name="valor" value="{escape(valor)}"'
            f' inputmode="decimal" required class="fixo-valor"></label>'
            f'<label class="teto-rotulo">dia<input name="dia" value="{fixo["dia"]}"'
            f' inputmode="numeric" required class="fixo-dia"></label>'
            f'<button type="submit" class="botao">{icone("editar", 16)}salvar</button>'
            f'<button type="button" class="botao" data-encerrar>{icone("lixeira", 16)}'
            f'<span class="rotulo">encerrar</span></button></form>')


def _formulario() -> str:
    return ('<form id="fixo-novo" class="teto-form">'
            '<label class="teto-rotulo">descrição<input name="descricao" required'
            ' autocomplete="off" class="teto-campo"></label>'
            '<label class="teto-rotulo">valor por mês<input name="valor" inputmode="decimal"'
            ' placeholder="R$" required class="fixo-valor"></label>'
            '<label class="teto-rotulo">dia<input name="dia" inputmode="numeric" required'
            ' class="fixo-dia"></label>'
            '<label class="teto-rotulo">categoria<input name="categoria" list="teto-categorias"'
            ' autocomplete="off" class="teto-campo"></label>'
            '<label class="teto-rotulo">forma<select name="forma" class="fixo-valor">'
            '<option value="debito">débito</option><option value="credito">crédito</option>'
            '</select></label>'
            f'<button type="submit" class="botao botao-principal">{icone("editar", 16)}'
            'cadastrar</button>'
            '<p class="teto-dica">lança um gasto por mês, com doze meses marcados à frente; '
            'mudar valor ou dia vale para os meses que ainda não caíram, e encerrar guarda '
            'os que já caíram</p></form>')


def cartao_recorrentes(ctx, registry) -> str:
    fixos = registry.call("expenses.recurring", {}, ctx).data or []
    if fixos:
        resumo = f'{formatar(sum(f["cents"] for f in fixos))} por mês'
        corpo = "".join(_linha(f) for f in fixos)
    else:
        resumo = ""
        corpo = ('<p style="margin:0;font-size:12.5px;color:var(--faint);line-height:1.5">'
                 'Nada cadastrado. Assinatura e conta fixa entram aqui embaixo, ou diga no '
                 'Telegram "o claude é 110 todo dia 5".</p>')
    return ('<div class="card" style="padding:16px 20px;margin-top:16px">'
            '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:10px">'
            '<span class="eyebrow">Gastos fixos</span>'
            f'<span style="font-size:12.5px;color:var(--muted)">{escape(resumo)}</span></div>'
            f'{corpo}<p id="fixos-erro" class="teto-erro" hidden></p>{_formulario()}</div>')
