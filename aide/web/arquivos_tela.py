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
  <label class="soltar" id="soltar">
    {icone("arquivos", 30)}
    <strong>Solte os arquivos aqui</strong>
    <span>ou <span class="link">escolha no computador</span> · Word, LibreOffice, planilhas,
      apresentações, PDF e imagens</span>
    <span class="mono soltar-aviso">nada fica guardado: o resultado vem como download
      e os temporários são apagados na hora</span>
    <input type="file" id="escolher" multiple hidden>
  </label>
  <div class="card fila-arq">
    <div class="linha fila-topo">
      <span class="eyebrow" id="fila-resumo">nenhum arquivo</span>
      <button type="button" class="botao-fraco" id="limpar" hidden>Limpar</button>
    </div>
    <div id="fila"><p class="vazio">Os arquivos que você soltar aparecem aqui.</p></div>
  </div>
</div>
<p class="eyebrow" style="margin-bottom:10px">O que fazer com os marcados</p>
<div class="acoes" id="acoes">{acoes}</div>
<p class="arq-aviso" id="arq-aviso" role="status"></p>"""
