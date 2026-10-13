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
const desfazer = document.getElementById("arq-desfazer");
const recomecar = document.getElementById("arq-recomecar");
const baixar = document.getElementById("arq-baixar");
const modeloFolha = document.getElementById("arq-modelo-folha");

// { arquivo: File, tipo, marcado, doc (promessa do pdf.js), paginas, erro }
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

// ---------- organizar: a sessão de um PDF ----------
// fontes[0] é o PDF aberto; as páginas são { fonte, pagina } contadas do 1.
// Baixar manda as fontes e essa lista para /api/arquivos/montar.

let sessao = null;
const molduras = new Map();  // "fonte:pagina" -> a miniatura já desenhada

function chave(p) {
  return p.fonte + ":" + p.pagina;
}

function moldura(p) {
  let m = molduras.get(chave(p));
  if (!m) {
    m = document.createElement("div");
    m.className = "miniatura";
    m.setAttribute("role", "img");
    m._origem = { item: sessao.fontes[p.fonte], pagina: p.pagina };
    molduras.set(chave(p), m);
    aVista.observe(m);
  }
  m.setAttribute("aria-label", "Página " + p.pagina + " de " + sessao.fontes[p.fonte].arquivo.name);
  return m;
}

// As páginas que você moveu são as que estão fora da maior sequência que
// continua em ordem: arrastar a 2 para depois da 5 marca só a 2, e excluir
// uma página não marca as que só andaram uma casa
function movidas(lista) {
  const seq = lista.map((p, i) => (p.fonte === 0 ? { valor: p.pagina, i } : null)).filter(Boolean);
  const fins = [];      // fins[k]: posição em seq do menor fim de sequência de tamanho k+1
  const antes = [];
  for (let j = 0; j < seq.length; j++) {
    let lo = 0, hi = fins.length;
    while (lo < hi) {
      const meio = (lo + hi) >> 1;
      if (seq[fins[meio]].valor < seq[j].valor) lo = meio + 1; else hi = meio;
    }
    antes[j] = lo ? fins[lo - 1] : -1;
    fins[lo] = j;
  }
  const emOrdem = new Set();
  for (let j = fins.length ? fins[fins.length - 1] : -1; j >= 0; j = antes[j]) emOrdem.add(seq[j].i);
  return new Set(seq.filter((x) => !emOrdem.has(x.i)).map((x) => x.i));
}

function folha(p, i, foraDeOrdem) {
  const div = modeloFolha.content.firstElementChild.cloneNode(true);
  div.dataset.indice = i;
  div.querySelector(".miniatura").replaceWith(moldura(p));
  const num = div.querySelector(".num");
  const n = document.createElement("b");
  n.textContent = i + 1;
  num.append(n);
  if (foraDeOrdem.has(i)) {
    const era = document.createElement("span");
    era.className = "era";
    era.textContent = " · era " + p.pagina;
    num.append(era);
  }
  if (sessao.movida === chave(p)) div.dataset.movida = "1";
  div.querySelector(".tirar-pagina").addEventListener("click", () => excluir(i));
  return div;
}

function resumir() {
  const n = sessao.original;
  const atuais = sessao.paginas.filter((p) => p.fonte === 0);
  const partes = [n === sessao.paginas.length ? paginas(n) : paginas(n) + " → " + sessao.paginas.length];
  const excluidas = n - atuais.length;
  if (excluidas) partes.push(excluidas === 1 ? "1 excluída" : excluidas + " excluídas");
  if (atuais.some((p, i) => i > 0 && p.pagina < atuais[i - 1].pagina)) partes.push("ordem mudada");
  return partes.join(" · ");
}

function redesenharGrade(foco) {
  const foraDeOrdem = movidas(sessao.paginas);
  grade.replaceChildren(...sessao.paginas.map((p, i) => folha(p, i, foraDeOrdem)));
  if (!sessao.paginas.length) {
    const vazio = document.createElement("p");
    vazio.className = "vazio";
    vazio.textContent = "Nenhuma página sobrou. Desfaça para trazer de volta.";
    grade.append(vazio);
  }
  document.getElementById("arq-editor-resumo").textContent = resumir();
  desfazer.disabled = !sessao.historico.length;
  recomecar.disabled = !sessao.historico.length;
  baixar.disabled = !sessao.paginas.length || sessao.enviando;
  if (foco !== undefined) {
    const alvo = grade.querySelector('.folha[data-indice="' + foco + '"]');
    if (alvo) alvo.focus();
  }
}

function mudar(novas, movida, foco) {
  sessao.historico.push(sessao.paginas);
  sessao.paginas = novas;
  sessao.movida = movida || null;
  redesenharGrade(foco);
}

function mover(de, para) {
  if (de === para || para < 0 || para >= sessao.paginas.length) return;
  const novas = sessao.paginas.slice();
  const [p] = novas.splice(de, 1);
  novas.splice(para, 0, p);
  mudar(novas, chave(p), para);
}

function excluir(i) {
  const novas = sessao.paginas.slice();
  novas.splice(i, 1);
  mudar(novas, null, Math.min(i, novas.length - 1));
}

function abrirSessao(alvo) {
  aVista.disconnect();
  molduras.clear();
  sessao = null;
  editor.hidden = !alvo;
  grade.replaceChildren();
  if (!alvo) return;
  sessao = {
    item: alvo,
    fontes: [alvo],
    original: alvo.paginas,
    paginas: Array.from({ length: alvo.paginas }, (_, i) => ({ fonte: 0, pagina: i + 1 })),
    historico: [],
    movida: null,
    enviando: false,
  };
  document.getElementById("arq-editor-nome").textContent = alvo.arquivo.name;
  redesenharGrade();
}

function desenharEditor() {
  const marcados = itens.filter((it) => it.marcado);
  const alvo = escolhida === "organizar" && marcados[0] && marcados[0].paginas ? marcados[0] : null;
  if (alvo !== (sessao && sessao.item)) abrirSessao(alvo);
}

// arrastar: a barra mostra de que lado da vizinha a página cai
let arrastada = null;

function limparMarcas() {
  for (const f of grade.querySelectorAll("[data-cair], [data-arrastando]")) {
    delete f.dataset.cair;
    delete f.dataset.arrastando;
  }
}

function destino(e) {
  const alvo = e.target.closest(".folha");
  if (!alvo) return null;
  const caixa = alvo.getBoundingClientRect();
  const depois = e.clientX > caixa.left + caixa.width / 2;
  return { alvo, depois, indice: Number(alvo.dataset.indice) + (depois ? 1 : 0) };
}

grade.addEventListener("dragstart", (e) => {
  const f = e.target.closest(".folha");
  if (!f) return;
  arrastada = Number(f.dataset.indice);
  f.dataset.arrastando = "1";
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", "página " + (arrastada + 1));
});
grade.addEventListener("dragover", (e) => {
  if (arrastada === null) return;
  e.preventDefault();
  const d = destino(e);
  for (const f of grade.querySelectorAll("[data-cair]")) if (!d || f !== d.alvo) delete f.dataset.cair;
  if (d) d.alvo.dataset.cair = d.depois ? "depois" : "antes";
});
grade.addEventListener("drop", (e) => {
  if (arrastada === null) return;
  e.preventDefault();
  e.stopPropagation();
  const d = destino(e);
  const de = arrastada;
  arrastada = null;
  limparMarcas();
  if (d) mover(de, d.indice > de ? d.indice - 1 : d.indice);
});
grade.addEventListener("dragend", () => { arrastada = null; limparMarcas(); });

grade.addEventListener("keydown", (e) => {
  const f = e.target.closest(".folha");
  if (!f || e.target !== f) return;
  const i = Number(f.dataset.indice);
  if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
    e.preventDefault();
    mover(i, i + (e.key === "ArrowLeft" ? -1 : 1));
  } else if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault();
    excluir(i);
  }
});

desfazer.addEventListener("click", () => {
  if (!sessao || !sessao.historico.length) return;
  sessao.paginas = sessao.historico.pop();
  sessao.movida = null;
  redesenharGrade();
});
recomecar.addEventListener("click", () => {
  if (!sessao) return;
  mudar(Array.from({ length: sessao.original }, (_, i) => ({ fonte: 0, pagina: i + 1 })));
});
document.addEventListener("keydown", (e) => {
  if (!sessao || editor.hidden || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
  if (e.target.closest("input, textarea")) return;
  e.preventDefault();
  desfazer.click();
});

// baixar: o corpo é a linha do plano e as fontes coladas na ordem
function nomeDoResultado(nome) {
  return nome.replace(/\.pdf$/i, "") + "-organizado.pdf";
}

function entregar(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

baixar.addEventListener("click", async () => {
  if (!sessao || !sessao.paginas.length || sessao.enviando) return;
  const atual = sessao;
  const arquivos = atual.fontes.map((f) => f.arquivo);
  const plano = {
    arquivos: arquivos.map((a) => a.size),
    paginas: atual.paginas.map((p) => [p.fonte, p.pagina - 1]),
  };
  atual.enviando = true;
  baixar.disabled = true;
  avisar("Montando o PDF…");
  desenhar();
  try {
    const resposta = await fetch("/api/arquivos/montar", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream", "X-Aide": "1" },
      body: new Blob([JSON.stringify(plano) + "\n", ...arquivos]),
      credentials: "same-origin",
    });
    if (!resposta.ok) {
      const motivo = await resposta.json().then((d) => d.detail, () => "erro " + resposta.status);
      throw new Error(motivo);
    }
    entregar(await resposta.blob(), nomeDoResultado(atual.item.arquivo.name));
    avisar("Pronto: " + paginas(atual.paginas.length) + " em " + nomeDoResultado(atual.item.arquivo.name) + ".");
  } catch (erro) {
    avisar("Não deu para montar: " + erro.message, true);
  } finally {
    atual.enviando = false;
    desenhar();
    if (sessao === atual) redesenharGrade();
  }
});

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
