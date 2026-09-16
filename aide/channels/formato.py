"""Como uma mensagem do assessor é escrita.

Uma mensagem é montada uma vez e renderizada por canal, porque os canais não
são iguais: o terminal é monoespaçado e aceita cor, a notificação de desktop é
fonte proporcional e texto puro, e o Telegram é proporcional mas entende
markdown. Alinhar coluna num dos três e mandar igual para os outros produz
exatamente a bagunça que este módulo existe para evitar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def por_extenso(momento: datetime) -> str:
    """'Quarta, 16 de setembro'.

    Escrito à mão em vez de `strftime`: o `%A` depende do locale instalado no
    sistema, e numa máquina em C ele devolve "Wednesday" no meio de uma
    interface em português — sem erro, só errado.
    """
    dia = DIAS[momento.weekday()]
    return f"{dia.capitalize()}, {momento.day} de {MESES[momento.month - 1]}"


def quando(iso: str | None, agora: datetime) -> str:
    """Data curta mais a leitura humana: '04/09 (há 12 dias)'.

    A data sozinha obriga a calcular de cabeça quanto tempo passou; o relativo
    sozinho perde a referência. Juntos cabem numa coluna e respondem as duas
    perguntas.
    """
    if not iso:
        return "sem prazo"

    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=agora.tzinfo)
    momento = momento.astimezone(agora.tzinfo)

    data = momento.strftime("%d/%m")
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - agora.date()).days

    if dias == 0:
        return f"{data} (hoje {hora})"
    if dias == 1:
        return f"{data} (amanhã {hora})"
    if dias == -1:
        return f"{data} (ontem)"
    if dias < 0:
        return f"{data} (há {abs(dias)} dias)"
    if dias < 7:
        return f"{data} ({DIAS[momento.weekday()]} {hora})"
    return f"{data} (em {dias} dias)"


def atraso(iso: str, agora: datetime) -> str:
    """Só o quanto, para a coluna estreita: '12 dias', '1 dia', 'hoje'."""
    momento = datetime.fromisoformat(iso)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=agora.tzinfo)
    dias = (agora.date() - momento.astimezone(agora.tzinfo).date()).days
    if dias <= 0:
        return "hoje"
    return "1 dia" if dias == 1 else f"{dias} dias"


# ---------- o modelo ----------


@dataclass
class Item:
    """Uma linha. `ref` é o id, `texto` o assunto, `marca` o prazo ou o quanto."""

    texto: str
    ref: str = ""
    marca: str = ""


@dataclass
class Secao:
    titulo: str
    itens: list[Item] = field(default_factory=list)


@dataclass
class Mensagem:
    titulo: str
    secoes: list[Secao] = field(default_factory=list)
    rodape: str = ""

    @property
    def vazia(self) -> bool:
        return not any(s.itens for s in self.secoes)


# ---------- renderizadores ----------

LARGURA_REF = 5
LARGURA_TEXTO = 32


def _cheias(mensagem: Mensagem) -> list[Secao]:
    return [s for s in mensagem.secoes if s.itens]


def para_terminal(mensagem: Mensagem) -> str:
    """Monoespaçado: dá para alinhar em coluna, que é o que faz a lista ser escaneável."""
    linhas = [mensagem.titulo, ""]
    for secao in _cheias(mensagem):
        linhas.append(secao.titulo.upper())
        for item in secao.itens:
            ref = item.ref.ljust(LARGURA_REF)
            texto = item.texto[:LARGURA_TEXTO].ljust(LARGURA_TEXTO) if item.marca else item.texto
            linhas.append(f"  {ref}{texto}{item.marca}".rstrip())
        linhas.append("")
    if mensagem.rodape:
        linhas.append(mensagem.rodape)
    return "\n".join(linhas).strip()


def para_desktop(mensagem: Mensagem) -> str:
    """Fonte proporcional e espaço curto: sem coluna, sem título repetido.

    O título da mensagem já vai no cabeçalho da notificação, então repeti-lo no
    corpo gasta uma das poucas linhas que aparecem antes do corte.
    """
    linhas = []
    for secao in _cheias(mensagem):
        linhas.append(f"{secao.titulo}:")
        linhas.extend(
            f"  {' '.join(p for p in (item.ref, item.texto) if p)}"
            + (f" — {item.marca}" if item.marca else "")
            for item in secao.itens
        )
    if mensagem.rodape:
        linhas.append(mensagem.rodape)
    return "\n".join(linhas).strip()


def para_telegram(mensagem: Mensagem) -> str:
    """Markdown: negrito na seção em vez de coluna, que não alinha aqui."""
    linhas = [f"*{escapar(mensagem.titulo)}*", ""]
    for secao in _cheias(mensagem):
        linhas.append(f"*{escapar(secao.titulo)}*")
        for item in secao.itens:
            corpo = escapar(" ".join(p for p in (item.ref, item.texto) if p))
            linhas.append(f"• {corpo}" + (f" — _{escapar(item.marca)}_" if item.marca else ""))
        linhas.append("")
    if mensagem.rodape:
        linhas.append(f"_{escapar(mensagem.rodape)}_")
    return "\n".join(linhas).strip()


# o Markdown legado do Telegram só se engasga com estes quatro
_ESCAPAR = str.maketrans({"*": r"\*", "_": r"\_", "`": r"\`", "[": r"\["})


def escapar(texto: str) -> str:
    """Um título com _ ou * quebraria a formatação da mensagem inteira."""
    return texto.translate(_ESCAPAR)
