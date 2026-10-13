"""O JavaScript da tela Arquivos, servido em /arquivos.js.

Módulo à parte do /app.js pela mesma razão do desenho: importa o pdf.js
(`/vendor/pdfjs/`, deploy/pdfjs/build.sh), e só esta tela precisa dele.
Arquivo, e não <script> embutido, pela CSP (`script-src 'self'`).

Os arquivos ficam na memória da página até você escolher a ação: soltar não
manda nada para o servidor. O PDF é lido aqui mesmo, pelo pdf.js, para contar
as páginas e desenhar as miniaturas. O tipo aqui sai da extensão e só decide quais
ações acendem; quem confere o conteúdo de verdade é o servidor, na hora da
operação.
"""

from __future__ import annotations

JS = r"""
import * as pdfjs from "/vendor/pdfjs/pdf.js";

pdfjs.GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/pdf.worker.js";

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

const soltar = document.getElementById("arq-soltar");
const escolher = document.getElementById("arq-escolher");
const fila = document.getElementById("arq-fila");
const resumo = document.getElementById("arq-fila-resumo");
const limpar = document.getElementById("arq-limpar");
const aviso = document.getElementById("arq-aviso");
const botoes = Array.from(document.querySelectorAll("#arq-acoes .acao"));
const editor = document.getElementById("arq-editor");
const grade = document.getElementById("arq-grade");

// { arquivo: File, tipo, marcado, doc (promessa do pdf.js), paginas, erro }
let itens = [];
let escolhida = null;
// o PDF que a grade mostra agora: redesenhar a lista não refaz as miniaturas
let noEditor = null;

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
    const it = { arquivo, tipo, marcado: true, doc: null, paginas: null, erro: null };
    itens.push(it);
    if (tipo === "pdf") contarPaginas(it);
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

// ---------- PDF: abrir no navegador, contar, desenhar páginas ----------

function abrir(it) {
  if (!it.doc) {
    it.doc = it.arquivo.arrayBuffer().then((dados) => pdfjs.getDocument({
      data: new Uint8Array(dados),
      // WebAssembly a CSP barra; o pdf.js tem o caminho em JS para o mesmo
      useWasm: false,
      enableXfa: false,
    }).promise);
  }
  return it.doc;
}

function contarPaginas(it) {
  abrir(it).then((doc) => {
    it.paginas = doc.numPages;
  }, (erro) => {
    it.erro = erro && erro.name === "PasswordException" ? "protegido por senha" : "PDF não abriu";
    it.doc = null;
  }).then(desenhar);
}

function paginas(n) {
  return n === 1 ? "1 pág" : n + " págs";
}

// a miniatura é desenhada quando aparece na tela: um PDF de 300 páginas não
// pode travar a página desenhando tudo de uma vez
const aVista = new IntersectionObserver((entradas) => {
  for (const entrada of entradas) {
    if (!entrada.isIntersecting) continue;
    aVista.unobserve(entrada.target);
    const { item, pagina } = entrada.target._origem;
    desenharPagina(item, pagina, entrada.target);
  }
}, { rootMargin: "300px" });

async function desenharPagina(it, numero, moldura) {
  try {
    const doc = await abrir(it);
    const pagina = await doc.getPage(numero);
    const base = pagina.getViewport({ scale: 1 });
    const escala = Math.min(112 / base.width, 150 / base.height) * (window.devicePixelRatio || 1);
    const viewport = pagina.getViewport({ scale: escala });
    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = Math.floor(viewport.width / (window.devicePixelRatio || 1)) + "px";
    await pagina.render({ canvas, canvasContext: canvas.getContext("2d"), viewport }).promise;
    moldura.replaceChildren(canvas);
  } catch (erro) {
    moldura.textContent = "não abriu";
  }
}

function folha(it, numero) {
  const div = document.createElement("div");
  div.className = "folha";
  const moldura = document.createElement("div");
  moldura.className = "miniatura";
  moldura.setAttribute("role", "img");
  moldura.setAttribute("aria-label", "Página " + numero);
  moldura._origem = { item: it, pagina: numero };
  aVista.observe(moldura);
  const num = document.createElement("span");
  num.className = "num mono";
  num.textContent = numero;
  div.append(moldura, num);
  return div;
}

function desenharEditor() {
  const marcados = itens.filter((it) => it.marcado);
  const alvo = escolhida === "organizar" && marcados[0] && marcados[0].paginas ? marcados[0] : null;
  if (alvo === noEditor) return;
  noEditor = alvo;
  aVista.disconnect();
  grade.replaceChildren();
  editor.hidden = !alvo;
  if (!alvo) return;
  document.getElementById("arq-editor-nome").textContent = alvo.arquivo.name;
  document.getElementById("arq-editor-resumo").textContent = paginas(alvo.paginas);
  for (let n = 1; n <= alvo.paginas; n++) grade.append(folha(alvo, n));
}

// ---------- a lista ----------

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
  quanto.textContent = it.erro ? it.erro
    : (it.paginas ? paginas(it.paginas) + " · " : "") + tamanho(it.arquivo.size);
  if (it.erro) div.dataset.erro = "1";
  const tirar = document.createElement("button");
  tirar.type = "button";
  tirar.className = "botao tirar-arq";
  tirar.title = "Tirar da lista";
  tirar.setAttribute("aria-label", "Tirar " + it.arquivo.name + " da lista");
  tirar.textContent = "×";
  tirar.addEventListener("click", () => {
    itens.splice(i, 1);
    if (it.doc) it.doc.then((doc) => doc.destroy(), () => {});
    avisar("");
    desenhar();
  });
  div.append(caixa, tipo, nome, quanto, tirar);
  return div;
}

function serve(acao, marcados) {
  const regra = REGRAS[acao];
  if (marcados.length < regra.min) return false;
  if (regra.max && marcados.length > regra.max) return false;
  return marcados.every((it) => it.tipo === regra.tipo && !it.erro);
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
  const quebrados = marcados.filter((it) => it.erro).length;
  const texto = recado.texto
    || (misturado ? "Os marcados misturam tipos: marque só PDFs, só documentos ou só imagens."
      : quebrados ? "Desmarque o que não abriu: não dá para fazer nada com ele." : "");
  aviso.textContent = texto;
  if (recado.erro) aviso.dataset.erro = "1"; else delete aviso.dataset.erro;
  for (const botao of botoes) {
    const acao = botao.dataset.acao;
    botao.disabled = !serve(acao, marcados);
    if (botao.disabled && escolhida === acao) escolhida = null;
    botao.setAttribute("aria-pressed", String(escolhida === acao));
  }
  desenharEditor();
}

for (const botao of botoes) {
  botao.addEventListener("click", () => {
    escolhida = botao.dataset.acao;
    avisar(escolhida === "organizar" ? "" : "Esta ação ainda está sendo construída.");
    desenhar();
  });
}

limpar.addEventListener("click", () => {
  for (const it of itens) if (it.doc) it.doc.then((doc) => doc.destroy(), () => {});
  itens = [];
  escolhida = null;
  avisar("");
  desenhar();
});
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
