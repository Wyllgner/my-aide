"""O JavaScript da tela Arquivos, servido em /arquivos.js.

Módulo à parte do /app.js pela mesma razão do desenho: só esta tela usa, e
as próximas etapas trazem o leitor de PDF, que as notas não precisam
carregar. Arquivo, e não <script> embutido, pela CSP (`script-src 'self'`).

Os arquivos ficam na memória da página até você escolher a ação: soltar não
manda nada para o servidor. O tipo aqui sai da extensão e só decide quais
ações acendem; quem confere o conteúdo de verdade é o servidor, na hora da
operação.
"""

from __future__ import annotations

JS = r"""
const TIPOS = {
  pdf: ["pdf"],
  documento: ["doc", "docx", "odt", "rtf", "txt", "xls", "xlsx", "ods", "ppt", "pptx", "odp"],
  imagem: ["jpg", "jpeg", "png"],
};

// cada ação diz que tipo aceita e quantos marcados precisa
const REGRAS = {
  "organizar": { tipo: "pdf", min: 1, max: 1 },
  "juntar": { tipo: "pdf", min: 2 },
  "converter": { tipo: "documento", min: 1 },
  "imagens-pdf": { tipo: "imagem", min: 1 },
  "pdf-imagens": { tipo: "pdf", min: 1 },
  "pdf-word": { tipo: "pdf", min: 1 },
};

const soltar = document.getElementById("soltar");
const escolher = document.getElementById("escolher");
const fila = document.getElementById("fila");
const resumo = document.getElementById("fila-resumo");
const limpar = document.getElementById("limpar");
const aviso = document.getElementById("arq-aviso");
const botoes = Array.from(document.querySelectorAll("#acoes .acao"));

// { arquivo: File, tipo, marcado }
let itens = [];
let escolhida = null;

function extensao(nome) {
  const i = nome.lastIndexOf(".");
  return i < 0 ? "" : nome.slice(i + 1).toLowerCase();
}

function tipoDe(nome) {
  const ext = extensao(nome);
  for (const [tipo, lista] of Object.entries(TIPOS)) {
    if (lista.includes(ext)) return tipo;
  }
  return null;
}

function tamanho(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / 1024 / 1024).toFixed(1).replace(".", ",") + " MB";
}

// o que o último gesto tem a dizer; vale até o próximo
let recado = { texto: "", erro: false };

function avisar(texto, erro) {
  recado = { texto: texto || "", erro: Boolean(erro) };
}

function mesmo(a, b) {
  return a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;
}

function acrescentar(arquivos) {
  const recusados = [];
  let repetidos = 0;
  for (const arquivo of arquivos) {
    const tipo = tipoDe(arquivo.name);
    if (!tipo) { recusados.push(arquivo.name); continue; }
    if (itens.some((it) => mesmo(it.arquivo, arquivo))) { repetidos++; continue; }
    itens.push({ arquivo, tipo, marcado: true });
  }
  if (recusados.length) {
    avisar("Não sei o que fazer com: " + recusados.join(", ")
      + ". Aceito PDF, documentos, planilhas, apresentações, .jpg e .png.", true);
  } else if (repetidos) {
    avisar(repetidos === 1 ? "Esse arquivo já estava na lista." : repetidos + " arquivos já estavam na lista.");
  } else {
    avisar("");
  }
  desenhar();
}

function linha(it, i) {
  const div = document.createElement("div");
  div.className = "linha";
  const caixa = document.createElement("input");
  caixa.type = "checkbox";
  caixa.className = "marcar";
  caixa.checked = it.marcado;
  caixa.setAttribute("aria-label", "Marcar " + it.arquivo.name);
  caixa.addEventListener("change", () => { it.marcado = caixa.checked; avisar(""); desenhar(); });
  const tipo = document.createElement("span");
  tipo.className = "tipo";
  tipo.dataset.tipo = it.tipo;
  tipo.textContent = extensao(it.arquivo.name).toUpperCase();
  const nome = document.createElement("span");
  nome.className = "nome";
  nome.textContent = it.arquivo.name;
  nome.title = it.arquivo.name;
  const quanto = document.createElement("span");
  quanto.className = "quando mono";
  quanto.textContent = tamanho(it.arquivo.size);
  const tirar = document.createElement("button");
  tirar.type = "button";
  tirar.className = "botao tirar-arq";
  tirar.title = "Tirar da lista";
  tirar.setAttribute("aria-label", "Tirar " + it.arquivo.name + " da lista");
  tirar.textContent = "×";
  tirar.addEventListener("click", () => { itens.splice(i, 1); avisar(""); desenhar(); });
  div.append(caixa, tipo, nome, quanto, tirar);
  return div;
}

function serve(acao, marcados) {
  const regra = REGRAS[acao];
  if (marcados.length < regra.min) return false;
  if (regra.max && marcados.length > regra.max) return false;
  return marcados.every((it) => it.tipo === regra.tipo);
}

function desenhar() {
  fila.replaceChildren();
  if (!itens.length) {
    const vazio = document.createElement("p");
    vazio.className = "vazio";
    vazio.textContent = "Os arquivos que você soltar aparecem aqui.";
    fila.append(vazio);
  }
  itens.forEach((it, i) => fila.append(linha(it, i)));
  const marcados = itens.filter((it) => it.marcado);
  resumo.textContent = !itens.length ? "nenhum arquivo"
    : (itens.length === 1 ? "1 arquivo" : itens.length + " arquivos")
      + " · " + (marcados.length === 1 ? "1 marcado" : marcados.length + " marcados");
  limpar.hidden = !itens.length;
  // tipos misturados apagam todas as ações; sem explicar, parece defeito
  const misturado = new Set(marcados.map((it) => it.tipo)).size > 1;
  const texto = recado.texto
    || (misturado ? "Os marcados misturam tipos: marque só PDFs, só documentos ou só imagens." : "");
  aviso.textContent = texto;
  if (recado.erro) aviso.dataset.erro = "1"; else delete aviso.dataset.erro;
  for (const botao of botoes) {
    const acao = botao.dataset.acao;
    botao.disabled = !serve(acao, marcados);
    if (botao.disabled && escolhida === acao) escolhida = null;
    botao.setAttribute("aria-pressed", String(escolhida === acao));
  }
}

for (const botao of botoes) {
  botao.addEventListener("click", () => {
    escolhida = botao.dataset.acao;
    avisar("Esta ação ainda está sendo construída.");
    desenhar();
  });
}

limpar.addEventListener("click", () => { itens = []; escolhida = null; avisar(""); desenhar(); });
escolher.addEventListener("change", () => { acrescentar(escolher.files); escolher.value = ""; });

// soltar fora da área não pode abrir o arquivo no lugar da página
for (const evento of ["dragover", "drop"]) {
  window.addEventListener(evento, (e) => e.preventDefault());
}
let dentro = 0;
soltar.addEventListener("dragenter", () => { dentro++; soltar.dataset.sobre = "1"; });
soltar.addEventListener("dragleave", () => { if (--dentro <= 0) { dentro = 0; delete soltar.dataset.sobre; } });
soltar.addEventListener("drop", (e) => {
  dentro = 0;
  delete soltar.dataset.sobre;
  if (e.dataTransfer && e.dataTransfer.files.length) acrescentar(e.dataTransfer.files);
});
"""
