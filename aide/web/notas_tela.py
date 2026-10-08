"""A tela de notas: o vault como pastas e arquivos, com o editor ao lado.

Igual ao Obsidian no que importa: a árvore é o disco, o nome do arquivo é o
título, e o que se edita é o arquivo inteiro, frontmatter incluído. Nada aqui
existe só no banco — abrir o `vault/` no Obsidian mostra exatamente o mesmo.

A árvore e o editor saem prontos do servidor; o `/app.js` só cuida de salvar
enquanto você digita e dos botões de criar e apagar.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from aide.channels import formato
from aide.storage import vault
from aide.web import consultas
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


def _mais_recente(raiz: Path) -> str | None:
    arquivos = vault.arquivos(raiz)
    validos = []
    for caminho in arquivos:
        relativo = vault.relativo_de(raiz, caminho)
        try:
            vault.resolver(raiz, relativo)
        except vault.ForaDoVault:
            continue
        validos.append((caminho.stat().st_mtime, relativo))
    return max(validos)[1] if validos else None


def _escolher(ctx, raiz: Path, arquivo: str | None, nota: int | None) -> str | None:
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
    return _mais_recente(raiz)


def _busca(ctx, registry, raiz: Path, busca: str, aberto: str | None) -> str:
    achados = registry.call("notes.search", {"query": busca, "limit": 20}, ctx)
    itens = ""
    for a in achados.data or []:
        if a.get("tipo") != "nota" or not a.get("id"):
            continue
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


def _editor(raiz: Path, aberto: str, agora: datetime) -> str:
    """O editor da nota aberta.

    Corretor desligado em nota privada: o "corretor avançado" do Chrome manda
    o que você digita para o Google. A quebra de linha logo depois de
    <textarea> é de propósito: o HTML descarta a primeira, e sem ela uma nota
    que começa em linha vazia perderia essa linha ao ser salva."""
    arquivo = vault.resolver(raiz, aberto)
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
    <h2 style="margin:0;font-size:20px;font-weight:600">{escape(arquivo.stem)}</h2>
  </div>
  <div class="editor-acoes">
    <label class="privada"><input type="checkbox" id="privada"{" checked" if privada else ""}>
      privada</label>
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
<textarea id="editor" spellcheck="{"false" if privada else "true"}" data-caminho="{escape(aberto)}"
  data-versao="{escape(str(arquivo.stat().st_mtime_ns))}">{escape(texto)}</textarea>"""


def tela(ctx, registry, agora: datetime, nota: int | None = None,
         busca: str | None = None, arquivo: str | None = None) -> str:
    raiz = Path(ctx.config.vault_dir)
    itens = vault.arvore(raiz)
    aberto = _escolher(ctx, raiz, arquivo, nota)
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

    if busca:
        lateral = (_busca(ctx, registry, raiz, busca, aberto)
                   + f'<a class="limpar" href="{escape(_href(aberto)) if aberto else "/notas"}">'
                     f'voltar às pastas</a>')
    else:
        lateral = _ramo(itens, aberto or "") or (
            '<p class="vazio">Nenhuma nota ainda. Crie a primeira com “+ nota”.</p>')

    pasta_atual = aberto.rpartition("/")[0] if aberto else ""
    corpo = (_editor(raiz, aberto, agora) if aberto else
             '<p class="vazio">Escolha uma nota à esquerda ou crie uma nova.</p>')

    busca_form = (
        f'<form method="get" action="/notas" style="display:flex;gap:6px">'
        f'<input name="busca" value="{escape(busca or "")}" placeholder="buscar por significado"'
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
