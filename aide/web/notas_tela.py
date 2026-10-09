"""A tela de notas: o vault como pastas e arquivos, com o editor ao lado.

Igual ao Obsidian no que importa: a árvore é o disco, o nome do arquivo é o
título, e o que se edita é o arquivo inteiro, frontmatter incluído. Nada aqui
existe só no banco — abrir o `vault/` no Obsidian mostra exatamente o mesmo.

A árvore e o editor saem prontos do servidor; o `/app.js` só cuida de salvar
enquanto você digita e dos botões de criar e apagar.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from aide.channels import formato
from aide.storage import links, vault
from aide.web import consultas, grafo, markdown
from aide.web.notas_api import TAMANHO_MAXIMO
from aide.web.paginas import cabecalho


def _href(caminho: str) -> str:
    return "/notas?arquivo=" + quote(caminho, safe="/")


def _contar(itens: list[dict]) -> tuple[int, int]:
    notas = pastas = 0
    for item in itens:
        if item["tipo"] == "pasta":
            pastas += 1
            n, p = _contar(item["filhos"])
            notas, pastas = notas + n, pastas + p
        else:
            notas += 1
    return notas, pastas


def _ramo(itens: list[dict], aberto: str) -> str:
    """Pasta fechada, a não ser a que contém a nota aberta: com tudo aberto,
    um vault de verdade vira uma lista de duzentas linhas."""
    html = ""
    for item in itens:
        caminho = escape(item["caminho"])
        if item["tipo"] == "pasta":
            abre = " open" if aberto.startswith(item["caminho"] + "/") else ""
            html += (f'<details{abre} data-pasta="{caminho}"><summary>{escape(item["nome"])}'
                     f'<span class="conta">{_contar(item["filhos"])[0]}</span></summary>'
                     f'<div class="filhos">{_ramo(item["filhos"], aberto) or _vazia()}</div>'
                     f'</details>')
        else:
            atual = ' aria-current="page"' if item["caminho"] == aberto else ""
            html += (f'<a class="arquivo" href="{escape(_href(item["caminho"]))}"{atual}'
                     f' title="{caminho}">{escape(item["nome"])}</a>')
    return html


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


def _busca(ctx, raiz: Path, busca: str, aberto: str | None) -> str:
    """Direto no índice, e não pela tool do modelo: `notes.search` esconde as
    privadas de propósito, e aqui quem procura é o dono. Sem embedder, que é
    o que a página tem — a consulta também não sai da máquina."""
    from aide.storage.search import buscar

    itens = ""
    for a in buscar(ctx.conn, busca, embedder=None, limite=20,
                    incluir_privadas=ctx.ver_privado):
        row = ctx.conn.execute("SELECT path FROM notes WHERE id = ?", (a["id"],)).fetchone()
        try:
            relativo = vault.relativo_de(raiz, Path(row["path"]))
        except (TypeError, ValueError):
            continue
        atual = ' aria-current="page"' if relativo == aberto else ""
        trecho = (f'<span class="trecho">{escape(a["trecho"][:110])}</span>'
                  if a.get("trecho") else "")
        itens += (f'<a class="arquivo achado" href="{escape(_href(relativo))}&amp;busca='
                  f'{escape(quote(busca))}"{atual}>{escape(a.get("title") or relativo)}'
                  f'<span class="onde">{escape(relativo)}</span>{trecho}</a>')
    return itens or '<p class="vazio">Nada encontrado.</p>'


MODOS = (("editar", "editar"), ("dividido", "lado a lado"), ("ler", "ler"))


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
                   f' aria-pressed="{apertado}">{rotulo}</button>')
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


def _quebrados(raiz: Path, quebrados: list[grafo.Ligacao]) -> str:
    """Os links para notas que não existem, um item por nota que falta, com
    quem cita e o botão de criar. Criar vai para a pasta de quem citou
    primeiro — o mesmo que o clique no link quebrado faz na prévia."""
    por_alvo: dict[str, list[grafo.Ligacao]] = {}
    for lig in quebrados:
        nome = lig.citacao.caminho_pedido(lig.origem).rpartition("/")[2]
        por_alvo.setdefault(markdown.chave_link(nome), []).append(lig)
    if not por_alvo:
        return '<p class="vazio">Nenhum link quebrado.</p>'
    itens = ""
    for chave in sorted(por_alvo, key=lambda k: (-len(por_alvo[k]), k)):
        ligs = por_alvo[chave]
        origens = list(dict.fromkeys(lig.origem for lig in ligs))
        novo = _caminho_novo(raiz, ligs[0].citacao.caminho_pedido(ligs[0].origem))
        alvo = (novo or ligs[0].citacao.alvo).rpartition("/")[2].removesuffix(".md")
        citam = ", ".join(
            f'<a href="{escape(_href(o))}">{escape(o.rpartition("/")[2].removesuffix(".md"))}</a>'
            for o in origens)
        botao = (f'<button type="button" class="botao-fraco criar-quebrado"'
                 f' data-caminho="{escape(novo)}">criar</button>' if novo else
                 '<span class="onde">nome que não pode virar arquivo</span>')
        itens += (f'<div class="quebrado-item"><div><strong>{escape(alvo)}</strong>'
                  f'<span class="onde">citada em {citam}</span></div>{botao}</div>')
    return itens


def _caminho_novo(raiz: Path, caminho: str) -> str | None:
    """O caminho, se ele pode virar arquivo no vault; senão None."""
    try:
        vault.resolver(raiz, caminho)
    except vault.ForaDoVault:
        return None
    return caminho


def _editor(raiz: Path, aberto: str, agora: datetime, indice: links.Indice,
            modo: str = "dividido", entradas: list | None = None) -> str:
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
    texto = arquivo.read_text(encoding="utf-8")
    meta, corpo = vault.ler(arquivo)
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
  <div class="editor-acoes">
    <label class="privada"><input type="checkbox" id="privada"{" checked" if privada else ""}>
      privada</label>
    {_modos(modo)}
    <button type="button" id="botao-renomear" class="botao-fraco">renomear</button>
    <button type="button" id="apagar" class="botao-fraco">apagar</button>
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
<textarea id="editor" spellcheck="{"false" if privada else "true"}" data-caminho="{escape(aberto)}"
  data-versao="{escape(str(arquivo.stat().st_mtime_ns))}"
  data-notas="{escape(json.dumps(indice.caminhos, ensure_ascii=False))}">
{escape(texto)}</textarea>
<article id="previa" class="previa">{markdown.renderizar(texto, aberto, indice)}</article>
</div>
{_backlinks(entradas or [])}"""


def tela(ctx, registry, agora: datetime, nota: int | None = None,
         busca: str | None = None, arquivo: str | None = None,
         modo: str | None = None, quebrados: bool = False) -> str:
    raiz = Path(ctx.config.vault_dir)
    itens = vault.arvore(raiz)
    indice = links.indice(raiz, itens)
    aberto = _escolher(ctx, raiz, arquivo, nota, indice)
    notas, pastas = _contar(itens)
    # apagar nota move o arquivo para vault/.trash; sem dizer isso em algum lugar,
    # a lixeira é uma pasta que só cresce e ninguém sabe que existe
    na_lixeira = consultas.notas_na_lixeira(raiz)

    resumo = " · ".join(p for p in (
        formato.plural(notas, "nota"),
        formato.plural(pastas, "pasta") if pastas else "",
        formato.plural(na_lixeira, "arquivo na lixeira", "arquivos na lixeira")
        if na_lixeira else "") if p)
    if busca:
        resumo += f' · busca: "{busca}"'

    mapa = grafo.mapa(raiz, indice)
    entradas = mapa.entradas(aberto) if aberto else []
    quebrados_todos = mapa.quebrados()
    voltar = (f'<a class="limpar" href="{escape(_href(aberto)) if aberto else "/notas"}">'
              f'voltar às pastas</a>')

    if busca:
        lateral = _busca(ctx, raiz, busca, aberto) + voltar
    elif quebrados:
        lateral = _quebrados(raiz, quebrados_todos) + voltar
    else:
        lateral = _ramo(itens, aberto or "") or (
            '<p class="vazio">Nenhuma nota ainda. Crie a primeira com “+ nota”.</p>')
    if quebrados_todos and not quebrados:
        alvos = len({markdown.chave_link(lig.citacao.caminho_pedido(lig.origem)
                                         .rpartition("/")[2]) for lig in quebrados_todos})
        lateral = (f'<a class="aviso-quebrados" href="/notas?quebrados=1'
                   f'{"&amp;arquivo=" + escape(quote(aberto, safe="/")) if aberto else ""}">'
                   f'{formato.plural(alvos, "link quebrado", "links quebrados")}</a>' + lateral)

    pasta_atual = aberto.rpartition("/")[0] if aberto else ""
    corpo = (_editor(raiz, aberto, agora, indice, _modo(modo), entradas) if aberto else
             '<p class="vazio">Escolha uma nota à esquerda ou crie uma nova.</p>')

    busca_form = (
        f'<form method="get" action="/notas" style="display:flex;gap:6px">'
        f'<input name="busca" value="{escape(busca or "")}" placeholder="buscar nas notas"'
        f' class="campo-busca"></form>')

    return f"""
{cabecalho("Notas", resumo, busca_form)}
<div class="notas">
  <div class="card notas-lateral">
    <div class="notas-botoes">
      <button type="button" id="nova-nota" class="botao-fraco">+ nota</button>
      <button type="button" id="nova-pasta" class="botao-fraco">+ pasta</button>
    </div>
    <form id="criar" class="criar" hidden data-pasta="{escape(pasta_atual)}">
      <input id="criar-nome" autocomplete="off" required>
      <span id="criar-erro" class="erro"></span>
    </form>
    <div class="arvore" aria-label="pastas e notas">{lateral}</div>
  </div>
  <div class="card notas-editor">{corpo}</div>
</div>"""
