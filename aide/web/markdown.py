"""A nota em markdown virada em HTML para a prévia.

No servidor, e não no navegador, para haver um só lugar que decide o que é
seguro mostrar. O texto é seu, mas pode ter vindo de fora — colado de um
site, de um e-mail, de um arquivo baixado —, então nada nele vira código:

- HTML escrito na nota aparece como texto (`html: False`);
- link só para http, https e mailto; `javascript:` e companhia ficam texto;
- imagem nunca carrega: uma imagem de fora avisaria o dono dela de que você
  abriu a nota (é assim que e-mail rastreia leitura). Vira um link;
- âncora de título leva o prefixo `s-`, para um "# editor" na nota não
  ganhar o mesmo id de um elemento da página.

E o que é do Obsidian: [[links]], [[nota|apelido]], [[nota#seção]], listas de
tarefa e o frontmatter mostrado como propriedades.
"""

from __future__ import annotations

import re
import unicodedata
from html import escape
from urllib.parse import quote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from aide.storage import vault
from aide.storage.links import Indice
from aide.storage.links import chave as chave_link

ESQUEMAS_SEGUROS = ("http", "https", "mailto")


def ancora(titulo: str) -> str:
    """'Próximos passos!' -> 's-próximos-passos'. Igual no título e no link."""
    texto = unicodedata.normalize("NFC", titulo).casefold().strip()
    texto = re.sub(r"[^\w\s-]", "", texto)
    return "s-" + (re.sub(r"\s+", "-", texto).strip("-") or "secao")


def href_da_nota(caminho: str, secao: str = "") -> str:
    return ("/notas?arquivo=" + quote(caminho, safe="/")
            + ("#" + quote(ancora(secao)) if secao else ""))


def _seguro(url: str) -> bool:
    return urlsplit(url.strip()).scheme.lower() in ESQUEMAS_SEGUROS


# ---------- regras ----------


def _wikilink(state, silent: bool) -> bool:
    """[[alvo#seção|apelido]], numa linha só e sem colchete dentro."""
    inicio = state.pos
    if not state.src.startswith("[[", inicio):
        return False
    fim = state.src.find("]]", inicio + 2)
    if fim < 0:
        return False
    dentro = state.src[inicio + 2:fim]
    if not dentro.strip() or any(c in dentro for c in "[]\n"):
        return False
    if not silent:
        alvo, _, apelido = dentro.partition("|")
        nome, _, secao = alvo.partition("#")
        token = state.push("wikilink", "", 0)
        token.meta = {"nome": nome.strip(), "secao": secao.strip(), "apelido": apelido.strip()}
    state.pos = fim + 2
    return True


def _render_wikilink(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    nome, secao, apelido = meta["nome"], meta["secao"], meta["apelido"]
    texto = apelido or (f"{nome} › {secao}" if nome and secao else nome or secao)
    destino = env["indice"].resolver(nome, env["origem"]) if nome else env["origem"]
    if destino is None:
        # quebrado: sem href, para não levar a lugar nenhum; o alvo fica
        # guardado para a página poder oferecer criar a nota
        # sem href o <a> some do teclado e do leitor de tela; role e
        # tabindex o devolvem
        return (f'<a class="wikilink quebrado" role="link" tabindex="0"'
                f' data-alvo="{escape(nome)}" title="essa nota ainda não existe;'
                f' clique para criar">{escape(texto)}</a>')
    return (f'<a class="wikilink" href="{escape(href_da_nota(destino, secao))}"'
            f' title="{escape(destino)}">{escape(texto)}</a>')


def _render_link_open(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    href = token.attrGet("href") or ""
    if _seguro(href):
        token.attrSet("target", "_blank")
        token.attrSet("rel", "noopener noreferrer")
    else:
        destino = _nota_por_link_markdown(href, env)
        if destino:
            token.attrSet("href", href_da_nota(destino))
        else:
            token.attrs.pop("href", None)
    return self.renderToken(tokens, idx, options, env)


def _nota_por_link_markdown(href: str, env) -> str | None:
    """[texto](Outra%20nota.md): o link markdown para outra nota do vault."""
    import posixpath
    from urllib.parse import unquote

    alvo = unquote(href.split("#")[0])
    if not alvo.lower().endswith(".md") or urlsplit(alvo).scheme:
        return None
    pasta = env["origem"].rpartition("/")[0] if env["origem"] else ""
    # relativo à nota, como o Obsidian grava: ../Inbox/Nota.md
    relativo = posixpath.normpath(posixpath.join(pasta, alvo))
    if not relativo.startswith(".."):
        achado = env["indice"].por_caminho.get(chave_link(relativo))
        if achado:
            return achado
    return env["indice"].resolver(alvo, env["origem"])


def _render_imagem(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    src = token.attrGet("src") or ""
    alt = self.renderInlineAsText(token.children or [], options, env) or "imagem"
    if _seguro(src):
        return (f'<a class="imagem-externa" href="{escape(src)}" target="_blank"'
                f' rel="noopener noreferrer" title="imagem de fora, não carregada">'
                f'{escape(alt)}</a>')
    return f'<span class="imagem-externa">{escape(alt)}</span>'


def _ancoras(state) -> None:
    """id em cada título, para [[nota#seção]] cair nele."""
    vistos: dict[str, int] = {}
    tokens = state.tokens
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or i + 1 >= len(tokens):
            continue
        base = ancora(tokens[i + 1].content)
        vistos[base] = vistos.get(base, 0) + 1
        token.attrSet("id", base if vistos[base] == 1 else f"{base}-{vistos[base]}")


TAREFA = re.compile(r"\[([ xX])\] ")


def _tarefas(state) -> None:
    """`- [ ] item` vira caixa marcável só de olhar; quem muda é o texto."""
    tokens = state.tokens
    for i, token in enumerate(tokens):
        if (token.type != "inline" or i < 2 or tokens[i - 1].type != "paragraph_open"
                or tokens[i - 2].type != "list_item_open"):
            continue
        casado = TAREFA.match(token.content)
        if not casado or not token.children or token.children[0].type != "text":
            continue
        primeiro = token.children[0]
        primeiro.content = primeiro.content[casado.end():]
        caixa = Token("tarefa", "", 0)
        caixa.meta = {"feita": casado.group(1) != " "}
        token.children.insert(0, caixa)
        tokens[i - 2].attrSet("class", "tarefa")


def _render_tarefa(self, tokens, idx, options, env) -> str:
    feita = " checked" if tokens[idx].meta["feita"] else ""
    return f'<input type="checkbox" disabled{feita}> '


def _motor() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.inline.ruler.before("link", "wikilink", _wikilink)
    md.core.ruler.push("ancoras", _ancoras)
    md.core.ruler.push("tarefas", _tarefas)
    md.add_render_rule("wikilink", _render_wikilink)
    md.add_render_rule("link_open", _render_link_open)
    md.add_render_rule("image", _render_imagem)
    md.add_render_rule("tarefa", _render_tarefa)
    return md


MOTOR = _motor()


def _propriedades(meta: dict[str, str]) -> str:
    if not meta:
        return ""
    linhas = "".join(f"<dt>{escape(chave)}</dt><dd>{escape(valor)}</dd>"
                     for chave, valor in meta.items())
    return f'<dl class="propriedades">{linhas}</dl>'


def renderizar(texto: str, origem: str | None, indice: Indice) -> str:
    """O HTML da prévia da nota `origem` (caminho no vault)."""
    meta, corpo = vault.separar(texto)
    env = {"origem": origem, "indice": indice}
    return _propriedades(meta) + MOTOR.render(corpo, env)
