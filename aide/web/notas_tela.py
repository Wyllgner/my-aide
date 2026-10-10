"""A tela de notas: o vault como pastas e arquivos, com o editor ao lado.

Igual ao Obsidian no que importa: a árvore é o disco, o nome do arquivo é o
título, e o que se edita é o arquivo inteiro, frontmatter incluído. Nada aqui
existe só no banco — abrir o `vault/` no Obsidian mostra exatamente o mesmo.

A árvore e o editor saem prontos do servidor; o `/app.js` só cuida de salvar
enquanto você digita e dos botões de criar e apagar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from aide.channels import formato
from aide.storage import anexos, links, vault
from aide.web import consultas, grafo, markdown, visao
from aide.web.icones import icone
from aide.web.notas_api import TAMANHO_MAXIMO
from aide.web.paginas import cabecalho


def _href(caminho: str) -> str:
    return "/notas?arquivo=" + quote(caminho, safe="/")


def _contar(itens: list[dict]) -> tuple[int, int, int]:
    """(notas, pastas, desenhos) da árvore inteira."""
    notas = pastas = desenhos = 0
    for item in itens:
        if item["tipo"] == "pasta":
            pastas += 1
            n, p, d = _contar(item["filhos"])
            notas, pastas, desenhos = notas + n, pastas + p, desenhos + d
        elif item["tipo"] == "desenho":
            desenhos += 1
        else:
            notas += 1
    return notas, pastas, desenhos


def _href_desenho(caminho: str, de: str) -> str:
    """A tela do desenho; `de` é a nota aberta, para o "Notas" voltar a ela."""
    url = "/desenho?caminho=" + quote(caminho, safe="/")
    return url + "&de=" + quote(de, safe="/") if de else url


def _ramo(itens: list[dict], aberto: str) -> str:
    """Pasta fechada, a não ser a que contém a nota aberta: com tudo aberto,
    um vault de verdade vira uma lista de duzentas linhas."""
    html = ""
    for item in itens:
        caminho = escape(item["caminho"])
        if item["tipo"] == "pasta":
            abre = " open" if aberto.startswith(item["caminho"] + "/") else ""
            html += (f'<details{abre} data-pasta="{caminho}"><summary>'
                     f'{icone("pasta", 14)}<span class="nome-pasta">{escape(item["nome"])}</span>'
                     f'<button type="button" class="nova-na-pasta" data-pasta="{caminho}"'
                     f' title="nova nota nesta pasta"'
                     f' aria-label="nova nota em {escape(item["nome"])}">{icone("nova-nota", 14)}</button>'
                     f'<button type="button" class="novo-desenho-na-pasta" data-pasta="{caminho}"'
                     f' title="novo desenho nesta pasta"'
                     f' aria-label="novo desenho em {escape(item["nome"])}">{icone("desenho", 14)}</button>'
                     f'<button type="button" class="renomear-pasta" data-pasta="{caminho}"'
                     f' title="renomear ou mover a pasta"'
                     f' aria-label="renomear {escape(item["nome"])}">{icone("renomear", 14)}</button>'
                     f'<button type="button" class="apagar-pasta" data-pasta="{caminho}"'
                     f' title="mandar a pasta para a lixeira (pede um segundo clique)"'
                     f' aria-label="apagar {escape(item["nome"])}">{icone("lixeira", 14)}'
                     f'<span class="rotulo"></span></button>'
                     f'<span class="conta">{_arquivos_em(item["filhos"])}</span></summary>'
                     f'<div class="filhos">{_ramo(item["filhos"], aberto) or _vazia()}</div>'
                     f'</details>')
        elif item["tipo"] == "desenho":
            # fora do arrastar por enquanto: mover desenho tem a sua rota
            html += (f'<a class="arquivo desenho" href="{escape(_href_desenho(item["caminho"], aberto))}"'
                     f' title="{caminho}" draggable="false">{icone("desenho", 14)}'
                     f'<span>{escape(item["nome"])}</span></a>')
        else:
            atual = ' aria-current="page"' if item["caminho"] == aberto else ""
            html += (f'<a class="arquivo" href="{escape(_href(item["caminho"]))}"{atual}'
                     f' title="{caminho}">{icone("nota", 14)}<span>{escape(item["nome"])}</span></a>')
    return html


def _arquivos_em(itens: list[dict]) -> int:
    notas, _pastas, desenhos = _contar(itens)
    return notas + desenhos


def _vazia() -> str:
    return '<span class="pasta-vazia">vazia</span>'


def _mais_recente(raiz: Path, indice: links.Indice) -> str | None:
    """A última nota que você mexeu, entre as que a árvore mostra."""
    datas = []
    for caminho in indice.caminhos:
        try:
            datas.append((vault.resolver(raiz, caminho).stat().st_mtime, caminho))
        except (vault.ForaDoVault, OSError):
            continue
    return max(datas)[1] if datas else None


def _escolher(ctx, raiz: Path, arquivo: str | None, nota: int | None,
              indice: links.Indice) -> str | None:
    """A nota aberta: a da URL; senão a do id antigo (`?nota=3`, que é o que o
    assessor e os links velhos usam); senão a última que você mexeu."""
    if arquivo:
        try:
            if vault.resolver(raiz, arquivo).is_file():
                return arquivo
        except vault.ForaDoVault:
            pass
    if nota is not None:
        row = ctx.conn.execute("SELECT path FROM notes WHERE id = ? AND deleted_at IS NULL",
                               (nota,)).fetchone()
        if row and Path(row["path"]).is_file():
            try:
                return vault.relativo_de(raiz, Path(row["path"]))
            except ValueError:
                pass
    return _mais_recente(raiz, indice)


# o que é marcação no trecho que o índice devolve: [[alvo|apelido]] fica só
# o apelido (ou o alvo), e #, *, _, `, o > da citação e [!tipo] somem; o
# trecho pode vir cortado no meio de um link, e os [[ ou ]] soltos também saem
_WIKI = re.compile(r"!?\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_MARCAS = re.compile(r"\[![\w-]+\][+-]?|(?<!\w)#{1,6}\s|(?<!\S)>+\s|[*_`]+|!?\[\[|\]\]")


def _trecho(texto: str, termos: list[str]) -> str:
    """O trecho do achado em texto corrido, com as palavras buscadas marcadas."""
    limpo = " ".join(_MARCAS.sub(" ", _WIKI.sub(r"\1", texto)).split())[:140]
    html = escape(limpo)
    if termos:
        padrao = re.compile("|".join(re.escape(escape(t)) for t in termos), re.IGNORECASE)
        html = padrao.sub(lambda m: f"<mark>{m.group(0)}</mark>", html)
    return html


def _busca(ctx, raiz: Path, busca: str, aberto: str | None) -> str:
    """Direto no índice, e não pela tool do modelo: `notes.search` esconde as
    privadas de propósito, e aqui quem procura é o dono. Sem embedder, que é
    o que a página tem — a consulta também não sai da máquina."""
    from aide.storage.search import buscar, termos_da_consulta

    termos = termos_da_consulta(busca)
    achados = buscar(ctx.conn, busca, embedder=None, limite=20,
                     incluir_privadas=ctx.ver_privado)
    # a nota cujo título tem o que você buscou vem antes: é ela que você quer
    # quase sempre, e o rank do texto às vezes a põe por último
    def no_titulo(achado) -> int:
        titulo = (achado.get("title") or "").casefold()
        return 0 if termos and all(t in titulo for t in termos) else 1

    itens, quantos = "", 0
    for a in sorted(achados, key=no_titulo):
        row = ctx.conn.execute("SELECT path FROM notes WHERE id = ?", (a["id"],)).fetchone()
        try:
            relativo = vault.relativo_de(raiz, Path(row["path"]))
        except (TypeError, ValueError):
            continue
        atual = ' aria-current="page"' if relativo == aberto else ""
        trecho = (f'<span class="trecho">{_trecho(a["trecho"], termos)}</span>'
                  if a.get("trecho") else "")
        itens += (f'<a class="arquivo achado" href="{escape(_href(relativo))}&amp;busca='
                  f'{escape(quote(busca))}"{atual}>{escape(a.get("title") or relativo)}'
                  f'<span class="onde">{escape(relativo)}</span>{trecho}</a>')
        quantos += 1
    topo = f'<p class="eyebrow">{formato.plural(quantos, "resultado")}</p>'
    return topo + itens if itens else '<p class="vazio">Nada encontrado.</p>'


# ao vivo: a nota formatada, e o bloco clicado vira markdown ali mesmo
MODOS = (("editar", "editar"), ("dividido", "lado a lado"), ("vivo", "ao vivo"), ("ler", "ler"))


def _modo(pedido: str | None) -> str:
    """O modo vem de um cookie que o `/app.js` grava: lido aqui, a página já
    nasce no modo certo, em vez de abrir lado a lado e trocar um instante
    depois. Valor desconhecido cai no padrão — o cookie não é confiável."""
    return pedido if pedido in dict(MODOS) else "dividido"


def _modos(atual: str) -> str:
    botoes = ""
    for modo, rotulo in MODOS:
        apertado = "true" if modo == atual else "false"
        botoes += (f'<button type="button" class="modo" data-modo="{modo}"'
                   f' aria-pressed="{apertado}" title="{rotulo} · Ctrl+E alterna com ler">'
                   f'{icone(modo, 15)}<span>{rotulo}</span></button>')
    return f'<div class="modos" role="group" aria-label="modo de visualização">{botoes}</div>'


def _backlinks(entradas: list[grafo.Ligacao]) -> str:
    """Quem aponta para a nota aberta, com a linha em volta de cada link —
    é o contexto que diz por que a outra nota fala desta."""
    por_origem: dict[str, list[str]] = {}
    for lig in entradas:
        por_origem.setdefault(lig.origem, []).append(lig.citacao.trecho)
    if not por_origem:
        return ('<section class="backlinks"><p class="eyebrow">Links para esta nota</p>'
                '<p class="vazio-curto">Nenhuma nota aponta para esta ainda.</p></section>')
    itens = ""
    for origem in sorted(por_origem, key=str.casefold):
        trechos = "".join(f'<li>{escape(t[:160])}{"…" if len(t) > 160 else ""}</li>'
                          for t in dict.fromkeys(por_origem[origem]))
        nome = origem.rpartition("/")[2].removesuffix(".md")
        itens += (f'<li><a href="{escape(_href(origem))}">{escape(nome)}</a>'
                  f'<span class="onde">{escape(origem)}</span><ul class="trechos">{trechos}'
                  f'</ul></li>')
    return (f'<section class="backlinks"><p class="eyebrow">Links para esta nota · '
            f'{formato.plural(len(por_origem), "nota")}</p><ul>{itens}</ul></section>')


def _visao_geral(raiz: Path, agora: datetime, indice: links.Indice, conn=None) -> str:
    """O painel do vault: números, atividade, as mais citadas, tags e órfãs."""
    from aide.web import graficos
    from aide.web.telas import _cartao, _indicador

    v = visao.montar(raiz, agora, dias=30, indice=indice, conn=conn)

    def nome(caminho: str) -> str:
        return caminho.rpartition("/")[2].removesuffix(".md")

    indicadores = "".join([
        _indicador("Notas", str(v.notas), formato.plural(v.palavras, "palavra")),
        _indicador("Ligações", str(v.ligacoes), "entre notas diferentes"),
        _indicador("Órfãs", str(len(v.orfas)), "sem link para nem de ninguém"),
        _indicador("Links quebrados", str(v.quebrados), "apontam para nota que não existe",
                   alerta=bool(v.quebrados)),
        _indicador("Tags", str(len(v.tags)), "do frontmatter e #do texto"),
    ])
    atividade = graficos.colunas([(dia[8:], n) for dia, n in v.atividade], 600, 96,
                                 vazio="nenhuma nota ainda")
    citadas = graficos.barras([(nome(c), n) for c, n in v.mais_citadas], rotulo_px=150,
                              vazio="nenhuma nota é citada ainda")
    tags = graficos.barras(v.tags[:12], rotulo_px=120, vazio="nenhuma tag ainda")
    orfas = "".join(f'<a href="{escape(_href(c))}">{escape(nome(c))}</a>' for c in v.orfas[:40])
    if len(v.orfas) > 40:
        orfas += f'<span class="onde">e mais {len(v.orfas) - 40}</span>'
    return f"""
<div class="visao">
  <div class="visao-numeros">{indicadores}</div>
  {_cartao("Notas mexidas por dia · últimos 30 dias",
           atividade + '<p class="nota-grafico">cada nota conta uma vez por dia em que foi '
           'mexida — pela página, pelo assessor ou por fora; antes do registro existir, '
           'vale a data de modificação do arquivo</p>')}
  <div class="visao-dupla">
    {_cartao("Mais citadas", citadas)}
    {_cartao("Tags", tags)}
  </div>
  {_cartao("Órfãs", f'<div class="orfas">{orfas}</div>' if orfas else
           '<p class="vazio-curto">Nenhuma: toda nota aponta ou é apontada.</p>')}
</div>"""


def _por_tag(raiz: Path, indice, tag: str, aberto: str | None) -> str:
    """As notas com a tag, do frontmatter ou do texto. Como no Obsidian,
    #casa traz também #casa/obra."""
    alvo = tag.casefold()
    achadas = []
    for caminho, leitura in grafo.leituras(raiz, indice).items():
        if any(t.casefold() == alvo or t.casefold().startswith(alvo + "/")
               for t in leitura.tags):
            achadas.append(caminho)
    topo = (f'<p class="eyebrow">#{escape(tag)} · '
            f'{formato.plural(len(achadas), "nota")}</p>')
    if not achadas:
        return topo + '<p class="vazio">Nenhuma nota com esta tag.</p>'
    itens = ""
    for caminho in sorted(achadas, key=str.casefold):
        atual = ' aria-current="page"' if caminho == aberto else ""
        nome = caminho.rpartition("/")[2].removesuffix(".md")
        itens += (f'<a class="arquivo achado" href="{escape(_href(caminho))}&amp;tag='
                  f'{escape(quote(tag, safe="/"))}"{atual}>{escape(nome)}'
                  f'<span class="onde">{escape(caminho)}</span></a>')
    return topo + itens


def _parecidas(alvo: str, caminhos: list[str]) -> list[str]:
    """Notas que existem com nome parecido: quase sempre o link quebrado é
    um nome digitado errado ("Fornecedor" por "Fornecedores")."""
    import difflib

    por_nome: dict[str, str] = {}
    for caminho in caminhos:
        por_nome.setdefault(caminho.rpartition("/")[2].removesuffix(".md").casefold(), caminho)
    achadas = difflib.get_close_matches(alvo.casefold(), list(por_nome), n=2, cutoff=0.75)
    return [por_nome[a] for a in achadas]


def _quebrados(raiz: Path, quebrados: list[grafo.Ligacao], caminhos: list[str] | None = None) -> str:
    """Os links para notas que não existem, um cartão por nota que falta, com
    quem cita e o botão de criar. Criar vai para a pasta de quem citou
    primeiro — o mesmo que o clique no link quebrado faz na prévia."""
    por_alvo: dict[str, list[grafo.Ligacao]] = {}
    for lig in quebrados:
        nome = lig.citacao.caminho_pedido(lig.origem).rpartition("/")[2]
        por_alvo.setdefault(markdown.chave_link(nome), []).append(lig)
    if not por_alvo:
        return ('<div class="quebrados-topo"><p class="eyebrow">Links quebrados</p>'
                '<p class="quebrados-explica">Nenhum: todo [[link]] leva a uma nota.</p></div>')
    citacoes = len(quebrados)
    topo = ('<div class="quebrados-topo"><p class="eyebrow">Links quebrados</p>'
            f'<p class="quebrados-resumo">{formato.plural(len(por_alvo), "nota faltando", "notas faltando")}'
            f' · {formato.plural(citacoes, "citação", "citações")}</p>'
            '<p class="quebrados-explica">Links para notas que ainda não existem. Crie a nota,'
            ' ligue a uma parecida que já existe, ou abra quem cita para corrigir.</p></div>')
    itens = ""
    for chave in sorted(por_alvo, key=lambda k: (-len(por_alvo[k]), k)):
        ligs = por_alvo[chave]
        origens = list(dict.fromkeys(lig.origem for lig in ligs))
        novo = _caminho_novo(raiz, ligs[0].citacao.caminho_pedido(ligs[0].origem))
        alvo = (novo or ligs[0].citacao.alvo).rpartition("/")[2].removesuffix(".md")
        citam = "".join(_onde_cita(o, [lig for lig in ligs if lig.origem == o])
                        for o in origens)
        pasta = novo.rpartition("/")[0] if novo else ""
        botao = (f'<button type="button" class="botao-fraco criar-quebrado"'
                 f' data-caminho="{escape(novo)}" title="criar {escape(novo)}">'
                 f'{icone("nova-nota", 14)}<span>criar</span></button>' if novo else "")
        onde = (f'<span class="onde">nasce em {escape(pasta + "/" if pasta else "raiz do vault")}</span>'
                if novo else '<span class="onde">nome que não pode virar arquivo</span>')
        vezes = formato.plural(len(origens), "nota cita", "notas citam")
        sugestoes = "".join(
            f'<button type="button" class="ligar-quebrado" data-alvo="{escape(ligs[0].citacao.alvo)}"'
            f' data-para="{escape(c)}" title="trocar o link por [[{escape(c.removesuffix(".md"))}]]'
            f' nas notas que citam">{icone("quebrado", 13)}<span>ligar a'
            f' <strong>{escape(c.rpartition("/")[2].removesuffix(".md"))}</strong></span></button>'
            for c in _parecidas(alvo, caminhos or []))
        sugestao = (f'<div class="quebrado-sugestao"><span class="onde">parecida com:</span>'
                    f'{sugestoes}</div>' if sugestoes else "")
        itens += (f'<div class="quebrado-item"><div class="quebrado-alvo">'
                  f'<div class="quebrado-nome"><strong>{escape(alvo)}</strong>'
                  f'<span class="onde">{vezes} · </span>{onde}</div>{botao}</div>'
                  f'{sugestao}<ul class="quebrado-citacoes">{citam}</ul></div>')
    return topo + itens


# o trecho em volta do link: uns 50 caracteres de cada lado, sem [[ ]] e com
# o link quebrado marcado
_EM_VOLTA = 50


def _trecho_do_link(trecho: str, alvo: str) -> str:
    casado = re.search(r"!?\[\[\s*" + re.escape(alvo) + r"[^\]]*\]\]", trecho)
    if not casado:
        casado = re.search(re.escape(alvo), trecho)
    if not casado:
        return escape(trecho[:_EM_VOLTA * 2]) + ("…" if len(trecho) > _EM_VOLTA * 2 else "")
    antes = trecho[max(0, casado.start() - _EM_VOLTA):casado.start()]
    depois = trecho[casado.end():casado.end() + _EM_VOLTA]

    def limpo(t: str) -> str:
        return escape(re.sub(r"!?\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t))

    return (("…" if casado.start() > _EM_VOLTA else "") + limpo(antes)
            + f"<mark>{escape(alvo)}</mark>" + limpo(depois)
            + ("…" if len(trecho) - casado.end() > _EM_VOLTA else ""))


def _onde_cita(origem: str, ligs: list[grafo.Ligacao]) -> str:
    """Quem cita, com o trecho em volta do link; o clique abre a nota já no
    link — `linha` e `alvo` o /app.js lê da URL para rolar e destacar."""
    primeira = min(ligs, key=lambda lig: lig.citacao.linha)
    href = (f"{_href(origem)}&linha={primeira.citacao.linha}"
            f"&alvo={quote(primeira.citacao.alvo, safe='')}")
    vezes = f' <span class="vezes">{len(ligs)}×</span>' if len(ligs) > 1 else ""
    nome = origem.rpartition("/")[2].removesuffix(".md")
    return (f'<li><a href="{escape(href)}" title="abrir {escape(origem)} no link">'
            f'{icone("nota", 13)}<span>{escape(nome)}</span>{vezes}</a>'
            f'<span class="trecho">{_trecho_do_link(primeira.citacao.trecho, primeira.citacao.alvo)}'
            f'</span></li>')


def _caminho_novo(raiz: Path, caminho: str) -> str | None:
    """O caminho, se ele pode virar arquivo no vault; senão None."""
    try:
        vault.resolver(raiz, caminho)
    except vault.ForaDoVault:
        return None
    return caminho


def _grafo_local(mapa: grafo.Mapa, indice: links.Indice, aberto: str) -> str:
    """A nota aberta e as vizinhas, no mesmo desenho do grafo do vault."""
    from aide.web import grafo_svg

    nos, arestas = grafo_svg.vizinhanca(grafo_svg.do_mapa(mapa, indice.caminhos), aberto)
    if len(nos) < 2:
        return ""
    return (f'<section class="local"><p class="eyebrow">Grafo local · '
            f'{formato.plural(len(nos) - 1, "vizinha")}'
            f' <span class="dica-grafo">Ctrl + roda para zoom</span></p>'
            f'{grafo_svg.desenhar(nos, arestas, aberto, classe="grafo local", largura=420, altura=300)}'
            f'</section>')


def _editor(raiz: Path, aberto: str, agora: datetime, indice: links.Indice,
            modo: str = "dividido", entradas: list | None = None, local: str = "") -> str:
    """O editor da nota aberta.

    Corretor desligado em nota privada: o "corretor avançado" do Chrome manda
    o que você digita para o Google. A quebra de linha logo depois de
    <textarea> é de propósito: o HTML descarta a primeira, e sem ela uma nota
    que começa em linha vazia perderia essa linha ao ser salva."""
    arquivo = vault.resolver(raiz, aberto)
    if arquivo.stat().st_size > TAMANHO_MAXIMO:
        # posta no vault por fora (um export, um log): ler e renderizar a cada
        # abertura travaria a página, e salvar seria recusado de todo jeito
        return (f'<h2 style="margin:0;font-size:20px;font-weight:600">{escape(arquivo.stem)}</h2>'
                f'<p class="vazio">Esta nota tem '
                f'{arquivo.stat().st_size / 1024 / 1024:.1f} MB, grande demais para abrir'
                f' aqui. Abra no Obsidian ou num editor de texto.</p>')
    try:
        texto = arquivo.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # um .md antigo do Windows (Latin-1). Abrir trocando o que não se lê
        # por "�" e salvar estragaria cada acento; melhor não abrir
        return (f'<h2 style="margin:0;font-size:20px;font-weight:600">{escape(arquivo.stem)}</h2>'
                f'<p class="vazio">Esta nota não está em UTF-8 e não abre aqui sem'
                f' estragar os acentos. Abra no Obsidian ou num editor de texto e'
                f' salve como UTF-8.</p>')
    meta, corpo = vault.separar(texto)
    privada = vault.privada(meta)
    modificada = datetime.fromtimestamp(arquivo.stat().st_mtime, tz=agora.tzinfo)
    pasta, _, nome = aberto.rpartition("/")
    trilha = (f'<span style="color:var(--faint)">{escape(pasta.replace("/", " › "))} › </span>'
              if pasta else "")
    palavras = len(corpo.split())
    return f"""
<div class="editor-topo">
  <div style="min-width:0">
    <p class="mono" style="margin:0 0 4px;font-size:11.5px;overflow:hidden;
       text-overflow:ellipsis;white-space:nowrap">{trilha}{escape(nome)}</p>
    <h2 id="titulo" class="titulo-nota" title="clique para renomear ou mover">{escape(arquivo.stem)}</h2>
    <form id="renomear" class="renomear" hidden>
      <input id="renomear-caminho" autocomplete="off" spellcheck="false"
        value="{escape(aberto.removesuffix(".md"))}" aria-label="caminho da nota">
      <span class="dica">Enter salva · Esc cancela · mude a pasta para mover</span>
      <span id="renomear-erro" class="erro"></span>
    </form>
  </div>
  <div class="editor-acoes" role="toolbar" aria-label="ações da nota">
    <label class="privada" title="privada: não vai para o modelo nem para a OpenAI">
      <input type="checkbox" id="privada"{" checked" if privada else ""}>
      {icone("privada", 15)}<span>privada</span></label>
    {_modos(modo)}
    <span class="separador" aria-hidden="true"></span>
    <button type="button" id="botao-anexar" class="botao"
      title="anexar imagem, PDF, áudio ou vídeo · também dá para colar (Ctrl+V) ou arrastar para o texto">
      {icone("anexar", 15)}<span>anexar</span></button>
    <input type="file" id="escolher-anexo" multiple hidden accept="{",".join(anexos.EXTENSOES)}">
    <button type="button" id="botao-renomear" class="botao" title="renomear ou mover · F2">
      {icone("renomear", 15)}<span>renomear</span></button>
    <button type="button" id="apagar" class="botao botao-perigo"
      title="mandar para a lixeira do vault (pede um segundo clique)">
      {icone("lixeira", 15)}<span class="rotulo">apagar</span></button>
  </div>
</div>
<p class="mono editor-meta"><span id="estado" data-estado="salvo">salvo</span>
  · {formato.plural(palavras, "palavra")}
  · modificada {escape(formato.quando(modificada.isoformat(), agora))}</p>
<div id="conflito" class="conflito" hidden>
  <span>Esta nota mudou fora daqui desde que você abriu.</span>
  <button type="button" id="usar-disco" class="botao-fraco">ficar com a do disco</button>
  <button type="button" id="usar-meu" class="botao-fraco">manter o que eu escrevi</button>
</div>
<div class="area" data-modo="{modo}">
<div class="campo"><pre id="realce" class="realce" aria-hidden="true"></pre>
<textarea id="editor" spellcheck="{"false" if privada else "true"}" data-caminho="{escape(aberto)}"
  data-versao="{escape(str(arquivo.stat().st_mtime_ns))}">
{escape(texto)}</textarea></div>
<article id="previa" class="previa">{markdown.renderizar(texto, aberto, indice, anexos.indice(raiz))}</article>
</div>
<div class="ao-redor">{_backlinks(entradas or [])}{local}</div>"""


def tela(ctx, registry, agora: datetime, nota: int | None = None,
         busca: str | None = None, arquivo: str | None = None,
         modo: str | None = None, quebrados: bool = False, geral: bool = False,
         grafo_todo: bool = False, tag: str | None = None) -> str:
    raiz = Path(ctx.config.vault_dir)
    # "#casa" na busca é a lista da tag, e não uma busca de texto (que ignora o #)
    if busca and re.fullmatch(r"#[\w/-]+", busca.strip()):
        tag, busca = busca.strip()[1:], None
    tag = (tag or "").strip().lstrip("#").strip("/") or None
    itens = vault.arvore(raiz)
    indice = links.indice(raiz, itens)
    aberto = _escolher(ctx, raiz, arquivo, nota, indice)
    if aberto:
        # antes de mostrar: a caixa "privada" lê o frontmatter
        from aide.storage.reconciliacao import privado_para_o_arquivo

        privado_para_o_arquivo(ctx.conn, raiz / aberto)
    notas, pastas, desenhos = _contar(itens)
    # apagar nota move o arquivo para vault/.trash; sem dizer isso em algum lugar,
    # a lixeira é uma pasta que só cresce e ninguém sabe que existe
    na_lixeira = consultas.notas_na_lixeira(raiz)

    resumo = " · ".join(p for p in (
        formato.plural(notas, "nota"),
        formato.plural(pastas, "pasta") if pastas else "",
        formato.plural(desenhos, "desenho") if desenhos else "",
        formato.plural(na_lixeira, "arquivo na lixeira", "arquivos na lixeira")
        if na_lixeira else "") if p)
    if busca:
        resumo += f' · busca: "{busca}"'
    if tag:
        resumo += f" · tag: #{tag}"

    mapa = grafo.mapa(raiz, indice)
    entradas = mapa.entradas(aberto) if aberto else []
    quebrados_todos = mapa.quebrados()
    voltar = (f'<a class="limpar" href="{escape(_href(aberto)) if aberto else "/notas"}">'
              f'voltar às pastas</a>')

    if busca:
        lateral = _busca(ctx, raiz, busca, aberto) + voltar
    elif tag:
        lateral = _por_tag(raiz, indice, tag, aberto) + voltar
    elif quebrados:
        lateral = _quebrados(raiz, quebrados_todos, indice.caminhos) + voltar
    else:
        # o título separa a árvore dos atalhos de cima; as ferramentas dela
        # (filtrar, recolher) entram ao lado
        lateral = ('<div class="arvore-topo"><p class="eyebrow">Pastas</p>'
                   '<span class="arvore-ferramentas">'
                   '<button type="button" class="ferramenta" id="recolher-pastas"'
                   ' title="recolher todas as pastas" aria-label="recolher todas as pastas">'
                   f'{icone("recolher", 14)}</button></span></div>'
                   '<input type="search" class="filtro-arvore" placeholder="filtrar por nome…"'
                   ' aria-label="filtrar a árvore por nome" autocomplete="off" spellcheck="false">'
                   '<p class="vazio-curto filtro-vazio" hidden>Nenhuma nota com esse nome.</p>'
                   + (_ramo(itens, "" if geral or grafo_todo else aberto or "") or (
                       '<p class="vazio">Nenhuma nota ainda. Crie a primeira com “+ nota”.</p>')))
    volta = "&amp;arquivo=" + escape(quote(aberto, safe="/")) if aberto else ""
    de_volta = escape(_href(aberto)) if aberto else "/notas"

    def atalho(classe: str, param: str, rotulo: str, nome_icone: str, ativo: bool) -> str:
        """O atalho continua no lugar quando aberto, só marcado; clicar de novo
        volta para a nota, como desmarcar."""
        href = de_volta if ativo else f"/notas?{param}=1{volta}"
        atual = ' aria-current="page"' if ativo else ""
        return (f'<a class="{classe}" href="{href}"{atual}>{icone(nome_icone, 15)}'
                f'<span>{rotulo}</span></a>')

    abrir_rapido = ('<button type="button" id="abrir-rapido" class="atalho-visao"'
                    ' title="abrir uma nota pelo nome · Ctrl+O">'
                    f'{icone("auditoria", 15)}<span>abrir nota…</span>'
                    '<kbd>Ctrl+O</kbd></button>')
    atalhos = (abrir_rapido
               + atalho("atalho-visao", "geral", "visão geral do vault", "painel", geral)
               + atalho("atalho-visao", "grafo", "grafo", "grafo", grafo_todo))
    lateral = f'<div class="atalhos">{atalhos}</div>' + lateral
    if quebrados_todos or quebrados:
        alvos = len({markdown.chave_link(lig.citacao.caminho_pedido(lig.origem)
                                         .rpartition("/")[2]) for lig in quebrados_todos})
        lateral = atalho("aviso-quebrados", "quebrados",
                         formato.plural(alvos, "link quebrado", "links quebrados"),
                         "quebrado", quebrados) + lateral

    pasta_atual = aberto.rpartition("/")[0] if aberto else ""
    if grafo_todo:
        from aide.web import grafo_svg

        nos = indice.caminhos
        arestas = grafo_svg.do_mapa(mapa, nos)
        corpo = (f'<div class="grafo-topo"><p class="eyebrow">Grafo · '
                 f'{formato.plural(len(nos), "nota")} · '
                 f'{formato.plural(len(arestas), "ligação", "ligações")}</p>'
                 f'<span class="onde">arraste para mover · roda do mouse para zoom ·'
                 f' clique numa nota para abrir</span></div>'
                 + grafo_svg.desenhar(nos, arestas, aberto))
    elif geral:
        corpo = _visao_geral(raiz, agora, indice, ctx.conn)
    elif aberto:
        corpo = _editor(raiz, aberto, agora, indice, _modo(modo), entradas,
                        _grafo_local(mapa, indice, aberto))
    else:
        corpo = '<p class="vazio">Escolha uma nota à esquerda ou crie uma nova.</p>'

    busca_form = (
        f'<form method="get" action="/notas" style="display:flex;gap:6px">'
        f'<input name="busca" value="{escape(busca or "")}" placeholder="buscar nas notas"'
        f' class="campo-busca"></form>')

    return f"""
{cabecalho("Notas", resumo, busca_form)}
<div class="notas" data-notas="{escape(json.dumps(indice.caminhos, ensure_ascii=False))}">
  <div class="card notas-lateral">
    <div class="notas-botoes">
      <button type="button" id="nova-nota" class="botao botao-principal"
        title="nova nota{" em " + escape(pasta_atual) if pasta_atual else ""}">
        {icone("nova-nota", 15)}<span>nova nota</span></button>
      <button type="button" id="nova-pasta" class="botao"
        title="nova pasta{" em " + escape(pasta_atual) if pasta_atual else ""}">
        {icone("nova-pasta", 15)}<span>pasta</span></button>
      <button type="button" id="novo-desenho" class="botao"
        title="novo desenho{" em " + escape(pasta_atual) if pasta_atual else ""}">
        {icone("desenho", 15)}<span>desenho</span></button>
    </div>
    <form id="criar" class="criar" hidden data-pasta="{escape(pasta_atual)}">
      <input id="criar-nome" autocomplete="off" required>
      <span class="dica">Enter cria · Esc cancela</span>
      <span id="criar-erro" class="erro"></span>
    </form>
    <div class="arvore" aria-label="pastas e notas">{lateral}</div>
  </div>
  <div class="card notas-editor">{corpo}</div>
</div>"""
