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
tarefa, callouts (`> [!info] Título`) e o frontmatter mostrado como propriedades.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html import escape
from urllib.parse import quote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from aide.storage import vault
from aide.storage.links import Indice
from aide.storage.links import chave as chave_link
from aide.web.icones import icone

ESQUEMAS_SEGUROS = ("http", "https", "mailto")


def ancora(titulo: str) -> str:
    """'Próximos passos!' -> 's-próximos-passos'. Igual no título e no link."""
    texto = unicodedata.normalize("NFC", titulo).casefold().strip()
    texto = re.sub(r"[^\w\s-]", "", texto)
    return "s-" + (re.sub(r"\s+", "-", texto).strip("-") or "secao")


def href_da_tag(tag: str, origem: str | None = None) -> str:
    """A lista de notas com a tag, sem fechar a nota que está aberta."""
    href = "/notas?tag=" + quote(tag, safe="/")
    return href + ("&arquivo=" + quote(origem, safe="/") if origem else "")


def _etiqueta(tag: str, origem: str | None) -> str:
    return f'<a class="tag" href="{escape(href_da_tag(tag, origem))}">#{escape(tag)}</a>'


def href_da_nota(caminho: str, secao: str = "") -> str:
    return ("/notas?arquivo=" + quote(caminho, safe="/")
            + ("#" + quote(ancora(secao)) if secao else ""))


def _seguro(url: str) -> bool:
    return urlsplit(url.strip()).scheme.lower() in ESQUEMAS_SEGUROS


# ---------- regras ----------


# `[[foto.png]]`, `![[relatório.pdf]]`: os tipos de anexo que o Obsidian
# reconhece. Lista, e não "qualquer extensão": "Plano v1.2" é nota
ANEXO = re.compile(r"\.(png|jpe?g|gif|bmp|svg|webp|avif|mp3|wav|m4a|ogg|flac|3gp"
                   r"|mp4|webm|ogv|mov|mkv|pdf|canvas|base)$", re.IGNORECASE)


# [[Planta.excalidraw]]: desenho do vault, que abre na tela dele
DESENHO = re.compile(r"\.excalidraw$", re.IGNORECASE)


def _wikilink(state, silent: bool) -> bool:
    """[[alvo#seção|apelido]] e ![[...]], numa linha só e sem colchete dentro."""
    inicio = state.pos
    embutido = state.src.startswith("![[", inicio)
    abre = inicio + (3 if embutido else 2)
    if not embutido and not state.src.startswith("[[", inicio):
        return False
    fim = state.src.find("]]", abre)
    if fim < 0:
        return False
    dentro = state.src[abre:fim]
    if not dentro.strip() or any(c in dentro for c in "[]\n"):
        return False
    if not silent:
        alvo, _, apelido = dentro.partition("|")
        nome, _, secao = alvo.partition("#")
        token = state.push("wikilink", "", 0)
        token.meta = {"nome": nome.strip(), "secao": secao.strip(), "apelido": apelido.strip(),
                      "embutido": embutido}
    state.pos = fim + 2
    return True


def _render_wikilink(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    nome, secao, apelido = meta["nome"], meta["secao"], meta["apelido"]
    texto = apelido or (f"{nome} › {secao}" if nome and secao else nome or secao)
    if ANEXO.search(nome):
        return _anexo(nome, apelido, env)
    if DESENHO.search(nome):
        if meta.get("embutido"):
            return _desenho_embutido(nome, apelido, env)
        return _link_de_desenho(nome, apelido, env)
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


def _link_de_desenho(alvo: str, apelido: str, env) -> str:
    """Abre a tela do desenho, e o "Notas" de lá volta para esta nota. Sem o
    desenho, fica quebrado como link de nota: o clique cria o desenho."""
    indice = env.get("desenhos")
    caminho = indice.resolver(alvo, env["origem"]) if indice else None
    texto = escape(apelido or alvo.rpartition("/")[2][:-len(".excalidraw")])
    if caminho is None:
        return (f'<a class="wikilink desenho quebrado" role="link" tabindex="0"'
                f' data-alvo="{escape(alvo)}" title="esse desenho ainda não existe;'
                f' clique para criar">{texto}</a>')
    href = _href_do_desenho(caminho, env)
    return (f'<a class="wikilink desenho" href="{escape(href)}"'
            f' title="{escape(caminho)}">{texto}</a>')


def _href_do_desenho(caminho: str, env) -> str:
    href = "/desenho?caminho=" + quote(caminho, safe="/")
    if env["origem"]:
        href += "&de=" + quote(env["origem"], safe="/")
    return href


def _desenho_embutido(alvo: str, apelido: str, env) -> str:
    """![[Planta.excalidraw]]: a prévia em PNG da versão atual, que leva ao
    desenho. `apelido` numérico é a largura, como nas imagens. Sem prévia
    (mexido por fora, ou nunca aberto aqui), um aviso que leva ao desenho —
    abrir gera a prévia."""
    indice = env.get("desenhos")
    caminho = indice.resolver(alvo, env["origem"]) if indice else None
    if caminho is None:
        return _link_de_desenho(alvo, "" if apelido.isdigit() else apelido, env)
    nome = escape(alvo.rpartition("/")[2][:-len(".excalidraw")])
    href = escape(_href_do_desenho(caminho, env))
    previa_de = env.get("previa_de")
    assinatura = previa_de(caminho) if previa_de else None
    if assinatura is None:
        return (f'<a class="desenho-embutido sem-previa" href="{href}" title="{escape(caminho)}">'
                f'{nome} · abrir para gerar a prévia</a>')
    # a assinatura no endereço troca a imagem quando o desenho muda
    src = (f"/api/desenhos/previa?caminho={quote(caminho, safe='/')}&v={assinatura}")
    largura = f' width="{int(apelido)}"' if apelido.isdigit() and 0 < int(apelido) <= 4000 else ""
    rotulo = escape(apelido) if apelido and not apelido.isdigit() else nome
    return (f'<a class="desenho-embutido" href="{href}" title="{escape(caminho)}">'
            f'<img src="{escape(src)}" alt="{rotulo}" loading="lazy"{largura}></a>')


def _render_link_open(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    href = token.attrGet("href") or ""
    if _seguro(href):
        token.attrSet("target", "_blank")
        token.attrSet("rel", "noopener noreferrer")
    else:
        destino, secao = _nota_por_link_markdown(href, env)
        if destino:
            token.attrSet("href", href_da_nota(destino, secao))
        else:
            token.attrs.pop("href", None)
    return self.renderToken(tokens, idx, options, env)


def _nota_por_link_markdown(href: str, env) -> tuple[str | None, str]:
    """[texto](Outra%20nota.md#Seção) e [texto](#Seção): (nota, seção).

    O link markdown para outra nota do vault, ou para um título da própria."""
    import posixpath
    from urllib.parse import unquote

    caminho, _, fragmento = href.partition("#")
    alvo, secao = unquote(caminho), unquote(fragmento)
    if not alvo:
        return (env["origem"], secao) if secao else (None, "")
    if not alvo.lower().endswith(".md") or urlsplit(alvo).scheme:
        return None, ""
    pasta = env["origem"].rpartition("/")[0] if env["origem"] else ""
    # relativo à nota, como o Obsidian grava: ../Inbox/Nota.md
    relativo = posixpath.normpath(posixpath.join(pasta, alvo))
    if not relativo.startswith(".."):
        achado = env["indice"].por_caminho.get(chave_link(relativo))
        if achado:
            return achado, secao
    return env["indice"].resolver(alvo, env["origem"]), secao


def _anexo(alvo: str, apelido: str, env) -> str:
    """Imagem, áudio, vídeo ou PDF do vault. `apelido` numérico é a largura,
    como no Obsidian: ![[foto.png|300]]."""
    from aide.storage import anexos

    indice = env.get("anexos")
    caminho = indice.resolver(alvo, env["origem"]) if indice else None
    nome = alvo.rpartition("/")[2]
    if caminho is None:
        return (f'<span class="anexo" title="anexo não encontrado no vault">'
                f'{escape(apelido or nome)}</span>')
    src = "/api/notas/anexo?caminho=" + quote(caminho, safe="/")
    largura = f' width="{int(apelido)}"' if apelido.isdigit() and 0 < int(apelido) <= 4000 else ""
    rotulo = escape(apelido if apelido and not apelido.isdigit() else nome)
    tipo = anexos.tipo(caminho)
    if tipo.startswith("image/"):
        return (f'<img class="anexo-imagem" src="{escape(src)}" alt="{rotulo}"'
                f' loading="lazy"{largura}>')
    if tipo.startswith("audio/"):
        return f'<audio class="anexo-midia" controls preload="none" src="{escape(src)}"></audio>'
    if tipo.startswith("video/"):
        return (f'<video class="anexo-midia" controls preload="metadata"'
                f' src="{escape(src)}"{largura}></video>')
    return (f'<a class="anexo" href="{escape(src)}" target="_blank" rel="noopener noreferrer">'
            f'{rotulo}</a>')


def _render_imagem(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    src = token.attrGet("src") or ""
    alt = self.renderInlineAsText(token.children or [], options, env) or "imagem"
    if _seguro(src):
        # imagem de fora nunca carrega: avisaria o dono dela que a nota foi aberta
        return (f'<a class="imagem-externa" href="{escape(src)}" target="_blank"'
                f' rel="noopener noreferrer" title="imagem de fora, não carregada">'
                f'{escape(alt)}</a>')
    # ![texto](anexos/foto.png): relativa à nota, como o Obsidian grava
    import posixpath
    from urllib.parse import unquote

    if env.get("anexos") and not urlsplit(src).scheme:
        pasta = (env["origem"] or "").rpartition("/")[0]
        relativo = posixpath.normpath(posixpath.join(pasta, unquote(src)))
        alvo = relativo if not relativo.startswith("..") else unquote(src)
        if ANEXO.search(alvo):
            return _anexo(alvo, alt if alt != "imagem" else "", env)
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


# os blocos que ganham a linha do arquivo onde começam, para a página poder
# rolar a prévia até um link citado (a lista de links quebrados leva até ele)
BLOCOS_COM_FONTE = frozenset({"paragraph_open", "heading_open", "list_item_open",
                              "blockquote_open", "table_open", "hr"})


def _fontes(state) -> None:
    deslocamento = state.env.get("deslocamento", 0)
    linhas = state.src.split("\n")
    for token in state.tokens:
        if token.type in BLOCOS_COM_FONTE and token.map and not token.hidden:
            token.attrSet("data-fonte", str(deslocamento + token.map[0]))
        # os blocos de fora (parágrafo, lista inteira, código...) levam também
        # onde terminam: no modo ao vivo, clicar num deles abre só essas linhas.
        # A lista conta a linha vazia que vem depois dela; essa fica de fora
        if token.level == 0 and token.nesting >= 0 and token.map and not token.hidden:
            inicio, fim = token.map
            while fim > inicio + 1 and not linhas[fim - 1].strip():
                fim -= 1
            token.attrSet("data-bloco", f"{deslocamento + inicio}-{deslocamento + fim}")


TAREFA = re.compile(r"\[([ xX])\] ")


def _tarefas(state) -> None:
    """`- [ ] item` vira caixa marcável. A caixa leva a linha do arquivo onde
    a tarefa está, e quem marca é o script, trocando `[ ]` por `[x]` no texto
    — a prévia nunca escreve sozinha."""
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
        item = tokens[i - 2]
        caixa.meta = {"feita": casado.group(1) != " ",
                      "linha": state.env.get("deslocamento", 0) + item.map[0]
                      if item.map else None}
        # o texto da tarefa num span: a feita sai riscada sem riscar junto as
        # subtarefas que estão embaixo dela
        abre = Token("tarefa_texto_open", "span", 1)
        abre.attrSet("class", "tarefa-texto")
        token.children = [caixa, abre] + token.children + [Token("tarefa_texto_close", "span", -1)]
        tokens[i - 2].attrSet("class", "tarefa feita" if caixa.meta["feita"] else "tarefa")


def _render_tarefa(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    feita = " checked" if meta["feita"] else ""
    if meta["linha"] is None:
        return f'<input type="checkbox" disabled{feita}> '
    return f'<input type="checkbox" data-linha="{int(meta["linha"])}"{feita}> '


# endereço com esquema, até o primeiro espaço ou caractere que não cabe em URL
URL_SOLTA = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)


def _aparar(url: str) -> str:
    """Pontuação colada no fim é da frase, não do endereço: "veja https://x.org."
    Parêntese de fechamento só fica se tiver o de abertura (links da Wikipédia)."""
    while url and url[-1] in ".,;:!?)]'*_":
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def _url_solta(state) -> None:
    """https://exemplo.org escrito no meio do texto vira link, como no Obsidian.

    Sem dependência nova: uma regra que só olha texto comum — fora de link
    existente e de código, que não chegam aqui como texto. O link sai pelo
    mesmo `link_open` dos outros, então ganha a mesma proteção."""
    for bloco in state.tokens:
        if bloco.type != "inline" or not bloco.children:
            continue
        novos, dentro_de_link = [], 0
        for token in bloco.children:
            if token.type == "link_open":
                dentro_de_link += 1
            elif token.type == "link_close":
                dentro_de_link -= 1
            if token.type != "text" or dentro_de_link or "://" not in token.content:
                novos.append(token)
                continue
            texto, inicio = token.content, 0
            for casado in URL_SOLTA.finditer(texto):
                url = _aparar(casado.group(0))
                href = state.md.normalizeLink(url)
                if not url.split("://", 1)[1] or not state.md.validateLink(href):
                    continue
                if casado.start() > inicio:
                    novos.append(_texto(texto[inicio:casado.start()]))
                abre = Token("link_open", "a", 1)
                abre.attrSet("href", href)
                novos.extend([abre, _texto(url), Token("link_close", "a", -1)])
                inicio = casado.start() + len(url)
            if inicio < len(texto):
                novos.append(_texto(texto[inicio:]))
        bloco.children = novos


# ---------- callouts do Obsidian ----------
# `> [!tipo] Título` vira uma caixa com ícone e cor. Os tipos e apelidos são
# os do Obsidian, para o vault continuar abrindo igual lá; o rótulo é o
# título quando você não escreve um. `[!tipo]-` nasce fechado, `+` aberto.

CALLOUTS = {
    "note": "Nota", "abstract": "Resumo", "info": "Info", "todo": "A fazer",
    "tip": "Dica", "success": "Feito", "question": "Pergunta", "warning": "Atenção",
    "failure": "Falhou", "danger": "Perigo", "bug": "Bug", "example": "Exemplo",
    "quote": "Citação",
}
APELIDOS_CALLOUT = {
    "summary": "abstract", "tldr": "abstract", "hint": "tip", "important": "tip",
    "check": "success", "done": "success", "help": "question", "faq": "question",
    "caution": "warning", "attention": "warning", "fail": "failure", "missing": "failure",
    "error": "danger", "cite": "quote",
}
CALLOUT = re.compile(r"\[!([\w-]+)\]([+-]?)[ \t]*")


def _fim_do_bloco(tokens: list[Token], i: int) -> int:
    """O blockquote_close do blockquote_open em `i` (pode haver outros dentro)."""
    fundo = 0
    for k in range(i, len(tokens)):
        if tokens[k].type == "blockquote_open":
            fundo += 1
        elif tokens[k].type == "blockquote_close":
            fundo -= 1
            if not fundo:
                return k
    return len(tokens) - 1


def _callouts(state) -> None:
    """A primeira linha da citação, se for `[!tipo]`, vira o título; o resto
    fica como corpo. O título continua sendo um token `inline`: os [[links]]
    nele contam no grafo como qualquer outro."""
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        abre = tokens[i]
        if (abre.type != "blockquote_open" or i + 3 >= len(tokens)
                or tokens[i + 1].type != "paragraph_open" or tokens[i + 2].type != "inline"):
            i += 1
            continue
        linha = tokens[i + 2]
        filhos = linha.children or []
        casado = CALLOUT.match(filhos[0].content) if filhos and filhos[0].type == "text" else None
        if not casado:
            i += 1
            continue
        escrito = casado.group(1).casefold()
        tipo = APELIDOS_CALLOUT.get(escrito, escrito)
        dobra = casado.group(2)
        quebra = next((k for k, f in enumerate(filhos) if f.type in ("softbreak", "hardbreak")),
                      len(filhos))
        resto = filhos[0].content[casado.end():]
        titulo = ([_texto(resto)] if resto else []) + filhos[1:quebra]
        if not titulo:
            titulo = [_texto(CALLOUTS.get(tipo, escrito.capitalize()))]
        linha.children = filhos[quebra + 1:]
        linha.content = linha.content.partition("\n")[2]
        if not linha.children:
            # só o título: o parágrafo vazio some
            tokens[i + 1].hidden = tokens[i + 3].hidden = True

        fecha = tokens[_fim_do_bloco(tokens, i)]
        abre.attrSet("class", "callout")
        abre.attrSet("data-callout", tipo)
        if dobra:
            abre.tag = fecha.tag = "details"
            if dobra == "+":
                abre.attrSet("open", "")
        cabeca = Token("callout_titulo_open", "", 1)
        cabeca.meta = {"tipo": tipo, "dobra": bool(dobra)}
        corpo_titulo = Token("inline", "", 0)
        corpo_titulo.children = titulo
        corpo_titulo.content = ""
        corpo_titulo.map = linha.map
        pe = Token("callout_titulo_close", "", -1)
        pe.meta = cabeca.meta
        tokens[i + 1:i + 1] = [cabeca, corpo_titulo, pe]
        i += 4


def _render_callout_abre(self, tokens, idx, options, env) -> str:
    meta = tokens[idx].meta
    tag = "summary" if meta["dobra"] else "div"
    # o ícone é dos nossos; tipo desconhecido usa o da nota
    nome = "callout-" + (meta["tipo"] if meta["tipo"] in CALLOUTS else "note")
    return f'<{tag} class="callout-titulo">{icone(nome, 16)}<span>'


def _render_callout_fecha(self, tokens, idx, options, env) -> str:
    return "</span></summary>\n" if tokens[idx].meta["dobra"] else "</span></div>\n"


def _tags(state) -> None:
    """#tag no texto vira etiqueta que leva às notas com ela. Fora de link e
    de código, como a URL solta; a mesma regra de `etiquetas`."""
    for bloco in state.tokens:
        if bloco.type != "inline" or not bloco.children:
            continue
        novos, dentro_de_link = [], 0
        for token in bloco.children:
            if token.type == "link_open":
                dentro_de_link += 1
            elif token.type == "link_close":
                dentro_de_link -= 1
            if token.type != "text" or dentro_de_link or "#" not in token.content:
                novos.append(token)
                continue
            texto, inicio = token.content, 0
            for casado in TAG.finditer(texto):
                if casado.start() > inicio:
                    novos.append(_texto(texto[inicio:casado.start()]))
                tag = Token("tag", "", 0)
                tag.meta = {"nome": casado.group(1).strip("/") or casado.group(1)}
                novos.append(tag)
                inicio = casado.end()
            if inicio < len(texto):
                novos.append(_texto(texto[inicio:]))
        bloco.children = novos


def _render_tag(self, tokens, idx, options, env) -> str:
    return _etiqueta(tokens[idx].meta["nome"], env.get("origem"))


def _texto(conteudo: str) -> Token:
    token = Token("text", "", 0)
    token.content = conteudo
    return token


def _motor() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.inline.ruler.before("link", "wikilink", _wikilink)
    md.core.ruler.push("ancoras", _ancoras)
    md.core.ruler.push("tarefas", _tarefas)
    md.core.ruler.push("url_solta", _url_solta)
    md.core.ruler.push("callouts", _callouts)
    md.core.ruler.push("tags", _tags)
    md.core.ruler.push("fontes", _fontes)
    md.add_render_rule("wikilink", _render_wikilink)
    md.add_render_rule("link_open", _render_link_open)
    md.add_render_rule("image", _render_imagem)
    md.add_render_rule("tarefa", _render_tarefa)
    md.add_render_rule("tag", _render_tag)
    md.add_render_rule("callout_titulo_open", _render_callout_abre)
    md.add_render_rule("callout_titulo_close", _render_callout_fecha)
    return md


MOTOR = _motor()


def _valor(chave: str, valor: str, origem: str | None) -> str:
    """As tags viram etiquetas clicáveis; o resto, texto."""
    if chave.casefold() not in ("tags", "tag"):
        return escape(valor)
    tags = [t.strip().lstrip("#").strip("/") for t in valor.strip("[]").split(",")]
    return " ".join(_etiqueta(t, origem) for t in tags if t) or escape(valor)


def _propriedades(meta: dict[str, str], fim: int, origem: str | None = None) -> str:
    """O frontmatter em lista; `fim` é a linha onde o corpo começa, e o
    bloco vai da primeira linha do arquivo até ela."""
    if not meta:
        return ""
    linhas = "".join(f"<dt>{escape(chave)}</dt><dd>{_valor(chave, valor, origem)}</dd>"
                     for chave, valor in meta.items())
    return f'<dl class="propriedades" data-bloco="0-{fim}">{linhas}</dl>'


def renderizar(texto: str, origem: str | None, indice: Indice, anexos=None,
               desenhos=None, previa_de=None) -> str:
    """O HTML da prévia da nota `origem` (caminho no vault)."""
    meta, _ = vault.separar(texto)
    inicio = vault.inicio_do_corpo(texto)
    # o corpo sem cortar as linhas vazias do começo: a linha de cada tarefa na
    # prévia precisa bater com a do arquivo
    corpo = "\n".join(texto.split("\n")[inicio:])
    env = {"origem": origem, "indice": indice, "deslocamento": inicio, "anexos": anexos,
           "desenhos": desenhos, "previa_de": previa_de}
    return _propriedades(meta, inicio, origem) + MOTOR.render(corpo, env)


# ---------- links de uma nota, para o mapa ----------


@dataclass(frozen=True)
class Citacao:
    """Um link escrito numa nota: o que está no texto, ainda sem destino."""

    tipo: str  # "wiki" para [[...]], "md" para [texto](arquivo.md)
    alvo: str
    secao: str
    linha: int  # linha no arquivo, contando o frontmatter
    trecho: str = ""  # o texto dessa linha, para mostrar o link no contexto

    def caminho_pedido(self, origem: str) -> str:
        """O caminho da nota (ou do desenho) que o link pede, para mostrar e
        para criar: `[[Fornecedores]]` na pasta de quem cita; `[x](../Nova%20nota.md)`
        decodificado e relativo à nota, como o Obsidian grava."""
        import posixpath
        from urllib.parse import unquote

        pasta = origem.rpartition("/")[0]
        if self.tipo == "wiki" and DESENHO.search(self.alvo):
            # o desenho leva a extensão no próprio link
            return self.alvo if "/" in self.alvo or not pasta else f"{pasta}/{self.alvo}"
        if self.tipo == "md":
            relativo = unquote(self.alvo.partition("#")[0])
            caminho = posixpath.normpath(posixpath.join(pasta, relativo))
        elif "/" in self.alvo or not pasta:
            caminho = self.alvo
        else:
            caminho = f"{pasta}/{self.alvo}"
        return caminho.removesuffix(".md") + ".md"

    def destino(self, origem: str, indice: Indice) -> str | None:
        """Para onde aponta hoje — muda quando notas são criadas ou apagadas."""
        env = {"origem": origem, "indice": indice}
        if self.tipo == "wiki":
            return indice.resolver(self.alvo, origem) if self.alvo else origem
        return _nota_por_link_markdown(self.alvo, env)[0]


def _linha_do_link(linhas: list[str], de: int, coluna: int, ate: int,
                   *marcas: str) -> tuple[int, int]:
    """(linha, coluna depois da marca) do link no arquivo, procurando a partir
    de onde ficou o link anterior do bloco. Num parágrafo de várias linhas o
    bloco começa antes; o contexto do backlink e o renomear precisam da linha
    do link, não da primeira do parágrafo. A coluna faz dois links iguais na
    mesma linha, ou um igual a um da linha de cima, caírem cada um no seu."""
    for marca in marcas:
        for n in range(de, min(ate, len(linhas))):
            achado = linhas[n].find(marca, coluna if n == de else 0)
            if achado >= 0:
                return n, achado + len(marca)
    return de, coluna


def _link_para_nota(href: str) -> bool:
    """Só link markdown que aponta para nota conta no mapa: `.md` ou só
    `#seção`. `foto.png` ou `Projetos/` como link quebrado fariam o "criar"
    gerar `foto.png.md`."""
    from urllib.parse import unquote

    caminho, _, fragmento = href.partition("#")
    caminho = unquote(caminho)
    if not caminho:
        return bool(fragmento)
    return caminho.lower().endswith(".md") and not urlsplit(caminho).scheme


def citacoes(texto: str, de_desenho: bool = False) -> list[Citacao]:
    """Os links da nota, pelo mesmo parser da prévia: link dentro de bloco de
    código não conta, e o que a prévia mostra como link é o que vira ligação.

    `de_desenho`: só os [[...excalidraw]] e ![[...excalidraw]], que o mapa de
    notas deixa de fora — para renomear um desenho sem quebrar quem o cita."""
    notas, de_desenhos = citacoes_separadas(texto)
    return de_desenhos if de_desenho else notas


def citacoes_separadas(texto: str) -> tuple[list[Citacao], list[Citacao]]:
    """(links para notas, links para desenhos), lendo o texto uma vez só."""
    inicio = vault.inicio_do_corpo(texto)
    corpo = "\n".join(texto.split("\n")[inicio:])
    linhas = texto.split("\n")
    notas: list[Citacao] = []
    de_desenhos: list[Citacao] = []
    for bloco in MOTOR.parse(corpo, {"deslocamento": inicio}):
        if bloco.type != "inline" or not bloco.children:
            continue
        de = inicio + (bloco.map[0] if bloco.map else 0)
        ate = inicio + (bloco.map[1] if bloco.map else 1)
        coluna = 0
        for token in bloco.children:
            # anexo e desenho não são nota: no mapa, virariam "nota que não
            # existe", e o "criar" faria Planta.excalidraw.md
            nome = token.meta.get("nome", "") if token.type == "wikilink" else ""
            if token.type == "wikilink" and DESENHO.search(nome):
                # "[[Casa.excalidraw" e não só o nome: "Casa.excalidraw" também
                # está dentro de "[[Projetos/Casa.excalidraw", numa linha acima
                marcas = ("[[" + nome, nome)
                tipo, alvo, secao, lista = "wiki", nome, token.meta["secao"], de_desenhos
            elif token.type == "wikilink" and not ANEXO.search(nome):
                # "[[Casa" antes de "Casa": o nome sozinho também aparece dentro
                # de "[[Projetos/Casa" numa linha acima, no mesmo parágrafo
                marcas = (("[[" + nome, nome) if nome else ("[[",))
                tipo, alvo, secao, lista = "wiki", nome, token.meta["secao"], notas
            elif token.type == "link_open" and _link_para_nota(token.attrGet("href") or ""):
                href = token.attrGet("href") or ""
                # o href como foi escrito, se der; senão o primeiro "](" do bloco
                marcas = (f"]({href}", "](")
                tipo, alvo, secao, lista = "md", href, "", notas
            else:
                continue
            linha, coluna = _linha_do_link(linhas, de, coluna, ate, *marcas)
            de = linha  # o próximo link do bloco está daqui em diante
            lista.append(Citacao(tipo, alvo, secao, linha, linhas[linha].strip()))
    return notas, de_desenhos


# ---------- tags ----------

# #tag do Obsidian: letras, números, _, - e /; precisa de pelo menos uma letra
# ("#2024" não é tag) e não pode vir colada em palavra (e-mail, URL#âncora)
TAG = re.compile(r"(?<![\w/#&])#([\w/-]*[^\W\d_][\w/-]*)")


def etiquetas(texto: str) -> list[str]:
    """As tags da nota: as do frontmatter e as #tags do texto, sem as de
    dentro de código. Cada uma uma vez, na grafia em que apareceu primeiro."""
    meta, _ = vault.separar(texto)
    # "tag" é o nome antigo da mesma propriedade, e o Obsidian ainda aceita
    declaradas = ",".join(meta.get(chave, "").strip("[]") for chave in ("tags", "tag"))
    achadas = [t.strip().lstrip("#") for t in declaradas.split(",")]
    inicio = vault.inicio_do_corpo(texto)
    corpo = "\n".join(texto.split("\n")[inicio:])
    for bloco in MOTOR.parse(corpo, {}):
        if bloco.type != "inline" or not bloco.children:
            continue
        for token in bloco.children:
            if token.type == "tag":
                achadas.append(token.meta["nome"])
    vistas: dict[str, str] = {}
    for tag in achadas:
        tag = tag.strip("/")
        if tag and tag.casefold() not in vistas:
            vistas[tag.casefold()] = tag
    return list(vistas.values())
