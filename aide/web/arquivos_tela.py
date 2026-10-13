"""A tela Arquivos: soltar arquivos e escolher o que fazer com eles.

Converter documento e imagem em PDF, organizar as páginas de um PDF, juntar
vários. Nada fica guardado: os arquivos vivem na página até o download, e o
servidor só os vê durante a operação que você pediu.

O servidor monta a moldura; a lista e os botões são de /arquivos.js, porque os
arquivos nunca saem do navegador antes de você escolher a ação.
"""

from __future__ import annotations

from html import escape

from aide.web.icones import icone
from aide.web.paginas import cabecalho

# (ação, rótulo, ícone, explicação). Quais valem para os marcados é decisão
# de /arquivos.js, que sabe o tipo de cada arquivo
ACOES = (
    ("organizar", "Organizar páginas", "paginas",
     "reordenar, excluir e inserir páginas de um PDF"),
    ("juntar", "Juntar PDFs", "juntar", "os marcados viram um só, na ordem da lista"),
    ("converter", "Converter para PDF", "exportar", ".docx .odt .rtf .txt .xlsx .pptx…"),
    ("imagens-pdf", "Imagens → PDF", "imagem", "uma imagem por página"),
    ("pdf-imagens", "PDF → imagens", "imagem", "cada página um .png, num .zip"),
    ("pdf-word", "PDF → Word", "word", ".docx editável; a formatação pode mudar"),
)


def _acao(chave: str, rotulo: str, nome_icone: str, dica: str) -> str:
    return (f'<button type="button" class="acao" data-acao="{chave}" disabled '
            f'aria-pressed="false"><strong>{icone(nome_icone)}{escape(rotulo)}</strong>'
            f'<span>{escape(dica)}</span></button>')


def tela(ctx, registry, agora) -> str:
    acoes = "".join(_acao(*a) for a in ACOES)
    return f"""{cabecalho("Arquivos", "converter e organizar")}
<div class="arq-topo">
  <label class="soltar" id="arq-soltar">
    {icone("arquivos", 30)}
    <strong>Solte os arquivos aqui</strong>
    <span>ou <span class="link">escolha no computador</span> · Word, LibreOffice, planilhas,
      apresentações, PDF e imagens</span>
    <span class="mono soltar-aviso">nada fica guardado: o resultado vem como download
      e os temporários são apagados na hora</span>
    <input type="file" id="arq-escolher" multiple hidden>
  </label>
  <div class="card fila-arq">
    <div class="linha fila-topo">
      <span class="eyebrow" id="arq-fila-resumo">nenhum arquivo</span>
      <button type="button" class="botao-fraco" id="arq-limpar" hidden>Limpar</button>
    </div>
    <div id="arq-fila"><p class="vazio">Os arquivos que você soltar aparecem aqui.</p></div>
  </div>
</div>
<p class="eyebrow" style="margin-bottom:10px">O que fazer com os marcados</p>
<div class="acoes" id="arq-acoes">{acoes}</div>
<p class="arq-aviso" id="arq-aviso" role="status"></p>
<section class="card editor-pdf" id="arq-editor" hidden>
  <div class="editor-topo">
    <h2 id="arq-editor-nome"></h2>
    <span class="resumo mono" id="arq-editor-resumo"></span>
    <button type="button" class="botao" id="arq-desfazer" disabled
      title="Desfazer (Ctrl+Z)">{icone("desfazer")}Desfazer</button>
    <button type="button" class="botao" id="arq-recomecar" disabled>Recomeçar</button>
    <button type="button" class="botao" id="arq-inserir-fim">{icone("mais")}Inserir no fim</button>
  </div>
  <div class="grade" id="arq-grade"></div>
  <div class="card inserir" id="arq-inserir" hidden>
    <p class="eyebrow" id="arq-inserir-onde"></p>
    <button type="button" class="botao" data-inserir="pdf">{icone("paginas")}Páginas de outro PDF…</button>
    <button type="button" class="botao" data-inserir="imagem">{icone("imagem")}Uma imagem…</button>
    <input type="file" id="arq-inserir-pdf" accept=".pdf,application/pdf" hidden>
    <input type="file" id="arq-inserir-imagem" accept=".jpg,.jpeg,.png,image/jpeg,image/png" hidden>
  </div>
  <div class="rodape-editor">
    <span class="mono">arraste para mover · + insere antes da página · lixeira exclui ·
      com a página em foco, Alt+← → move e Delete exclui</span>
    <button type="button" class="botao botao-principal" id="arq-baixar">
      {icone("exportar")}Baixar PDF</button>
  </div>
</section>
<section class="card juntar" id="arq-juntar" hidden>
  <div class="editor-topo">
    <h2 id="arq-juntar-titulo">Juntar PDFs</h2>
    <span class="resumo mono" id="arq-juntar-resumo"></span>
  </div>
  <div id="arq-juntar-lista"></div>
  <div class="rodape-editor">
    <span class="mono">arraste para mudar a ordem · com a linha em foco, Alt+↑ ↓ move</span>
    <button type="button" class="botao botao-principal" id="arq-juntar-baixar">
      {icone("exportar")}<span>Baixar PDF juntado</span></button>
  </div>
</section>
<section class="card juntar" id="arq-converter" hidden>
  <div class="editor-topo">
    <h2>Converter para PDF</h2>
    <span class="resumo mono">pelo LibreOffice desta máquina</span>
  </div>
  <div id="arq-converter-lista"></div>
  <div class="rodape-editor">
    <span class="mono">vários documentos voltam num .zip, um PDF para cada</span>
    <button type="button" class="botao botao-principal" id="arq-converter-baixar">
      {icone("exportar")}<span>Converter e baixar PDF</span></button>
  </div>
</section>
<template id="arq-modelo-juntar">
  <div class="linha" draggable="true" tabindex="0">
    <span class="alca" aria-hidden="true">⋮⋮</span>
    <span class="tipo" data-tipo="pdf">PDF</span>
    <span class="nome"></span>
    <span class="quando mono"></span>
    <button type="button" class="botao mover" data-mover="-1" title="Subir">↑</button>
    <button type="button" class="botao mover" data-mover="1" title="Descer">↓</button>
  </div>
</template>
<template id="arq-modelo-folha">
  <div class="folha" draggable="true" tabindex="0">
    <div class="miniatura" role="img"></div>
    <button type="button" class="tirar-pagina" title="Excluir página">{icone("lixeira", 14)}</button>
    <button type="button" class="inserir-antes" title="Inserir antes desta página">{icone("mais", 14)}</button>
    <span class="num"></span>
  </div>
</template>
<script type="module" src="/arquivos.js"></script>"""
