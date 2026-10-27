// A tela Arquivos. Separado do app.js porque importa o pdf.js
// (deploy/pdfjs/build.sh) e so esta tela precisa dele. Arquivo, e nao
// <script> embutido, pela CSP (script-src 'self').
//
// Os arquivos ficam na memoria da pagina ate voce escolher a acao: soltar
// nao manda nada para o servidor. O tipo sai da extensao e so decide quais
// acoes acendem; quem confere o conteudo de verdade e o servidor.
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
const caixaInserir = document.getElementById("arq-inserir");
const secaoJuntar = document.getElementById("arq-juntar");
const listaJuntar = document.getElementById("arq-juntar-lista");
const baixarJuntado = document.getElementById("arq-juntar-baixar");
const modeloJuntar = document.getElementById("arq-modelo-juntar");
const secaoLote = document.getElementById("arq-lote");
const listaLote = document.getElementById("arq-lote-lista");
const baixarLote = document.getElementById("arq-lote-baixar");
const escolhaWord = document.getElementById("arq-word-modo");
const inserirPdf = document.getElementById("arq-inserir-pdf");
const inserirImagem = document.getElementById("arq-inserir-imagem");

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

// o nome sem a extensao: a base de todo nome de resultado
function semExtensao(nome) {
  return nome.replace(/\.[^.]+$/, "");
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

// o que a linha diz do arquivo quando nada esta acontecendo com ele
function medida(it) {
  return (it.paginas ? paginas(it.paginas) + " · " : "") + tamanho(it.arquivo.size);
}

// o selo da extensao e o nome, iguais na fila de cima e na lista do lote
function selo(it) {
  const tipo = document.createElement("span");
  tipo.className = "tipo";
  tipo.dataset.tipo = it.tipo;
  tipo.textContent = extensao(it.arquivo.name).toUpperCase();
  return tipo;
}

function rotulo(it) {
  const nome = document.createElement("span");
  nome.className = "nome";
  nome.textContent = it.arquivo.name;
  nome.title = it.arquivo.name;
  return nome;
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
    it.doc = it.arquivo.arrayBuffer().then((dados) => {
      it.tarefa = pdfjs.getDocument({
        data: new Uint8Array(dados),
        // WebAssembly a CSP barra; o pdf.js tem o caminho em JS para o mesmo
        useWasm: false,
        enableXfa: false,
      });
      return it.tarefa.promise;
    });
  }
  return it.doc;
}

// devolve a memória do PDF ao worker. No pdf.js 6 quem tem destroy() é a
// tarefa de carregamento; o documento só tem cleanup()
function liberar(it) {
  if (it.doc) it.doc.then(() => it.tarefa && it.tarefa.destroy(), () => {});
  it.doc = null;
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

// imagem: desenhada direto, sem pdf.js. <img> com blob: a CSP não deixa
async function desenharImagem(it, moldura) {
  const bitmap = await createImageBitmap(it.arquivo, { imageOrientation: "from-image" });
  const dpr = window.devicePixelRatio || 1;
  const escala = Math.min(112 / bitmap.width, 150 / bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.floor(bitmap.width * escala * dpr));
  canvas.height = Math.max(1, Math.floor(bitmap.height * escala * dpr));
  canvas.style.width = Math.floor(bitmap.width * escala) + "px";
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  moldura.replaceChildren(canvas);
}

async function desenharPagina(it, numero, moldura) {
  try {
    if (it.tipo === "imagem") return await desenharImagem(it, moldura);
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
  const fonte = sessao.fontes[p.fonte];
  m.setAttribute("aria-label", fonte.tipo === "imagem" ? "Imagem " + fonte.arquivo.name
    : "Página " + p.pagina + " de " + fonte.arquivo.name);
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
  const era = document.createElement("span");
  era.className = "era";
  if (p.fonte !== 0) {
    const fonte = sessao.fontes[p.fonte];
    era.textContent = " · " + fonte.arquivo.name + (fonte.tipo === "pdf" ? " p." + p.pagina : "");
    div.dataset.deFora = "1";
    div.title = fonte.arquivo.name;
  } else if (foraDeOrdem.has(i)) {
    era.textContent = " · era " + p.pagina;
  }
  if (era.textContent) num.append(era);
  if (sessao.movida === chave(p)) div.dataset.movida = "1";
  div.querySelector(".tirar-pagina").addEventListener("click", () => excluir(i));
  const mais = div.querySelector(".inserir-antes");
  mais.addEventListener("click", (e) => { e.stopPropagation(); abrirInserir(i, mais); });
  return div;
}

function resumir() {
  const n = sessao.original;
  const atuais = sessao.paginas.filter((p) => p.fonte === 0);
  const partes = [n === sessao.paginas.length ? paginas(n) : paginas(n) + " → " + sessao.paginas.length];
  const excluidas = n - atuais.length;
  if (excluidas) partes.push(excluidas === 1 ? "1 excluída" : excluidas + " excluídas");
  const inseridas = sessao.paginas.length - atuais.length;
  if (inseridas) partes.push(inseridas === 1 ? "1 inserida" : inseridas + " inseridas");
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

// ---------- inserir: de outro PDF ou de uma imagem ----------

let ondeInserir = null;  // posição na lista onde as páginas novas entram

function abrirInserir(posicao, ancora) {
  fecharInserir();
  ondeInserir = posicao;
  document.getElementById("arq-inserir-onde").textContent =
    posicao >= sessao.paginas.length ? "Inserir no fim" : "Inserir antes da página " + (posicao + 1);
  const caixa = ancora.getBoundingClientRect();
  const base = editor.getBoundingClientRect();
  caixaInserir.style.left = Math.min(caixa.left - base.left, base.width - 260) + "px";
  caixaInserir.style.top = (caixa.bottom - base.top + 6) + "px";
  caixaInserir.hidden = false;
  caixaInserir._ancora = ancora;
  ancora.setAttribute("aria-expanded", "true");
  caixaInserir.querySelector("button").focus();
}

function fecharInserir() {
  if (caixaInserir._ancora) caixaInserir._ancora.removeAttribute("aria-expanded");
  caixaInserir._ancora = null;
  caixaInserir.hidden = true;
}

function inserir(fonte, quantas) {
  const indice = sessao.fontes.push(fonte) - 1;
  const novas = sessao.paginas.slice();
  const onde = Math.min(ondeInserir, novas.length);
  novas.splice(onde, 0, ...Array.from({ length: quantas }, (_, k) => ({ fonte: indice, pagina: k + 1 })));
  mudar(novas, null, onde);
}

async function inserirArquivo(arquivo, tipo) {
  fecharInserir();
  if (!sessao || !arquivo) return;
  if (tipoDe(arquivo.name) !== tipo) {
    avisar(arquivo.name + (tipo === "pdf" ? " não é um PDF." : " não é .jpg nem .png."), true);
    return desenhar();
  }
  const fonte = { arquivo, tipo, doc: null, paginas: null, erro: null };
  if (tipo === "imagem") return inserir(fonte, 1);
  const atual = sessao;
  try {
    const doc = await abrir(fonte);
    if (sessao !== atual) return;
    fonte.paginas = doc.numPages;
    inserir(fonte, doc.numPages);
    avisar(paginas(doc.numPages) + " de " + arquivo.name + " entraram. Tire com a lixeira as que não quiser.");
  } catch (erro) {
    avisar(arquivo.name + (erro && erro.name === "PasswordException"
      ? " está protegido por senha." : " não abriu como PDF."), true);
  }
  desenhar();
}

for (const botao of caixaInserir.querySelectorAll("[data-inserir]")) {
  botao.addEventListener("click", () => {
    (botao.dataset.inserir === "pdf" ? inserirPdf : inserirImagem).click();
  });
}
inserirPdf.addEventListener("change", () => {
  const arquivo = inserirPdf.files[0];
  inserirPdf.value = "";
  inserirArquivo(arquivo, "pdf");
});
inserirImagem.addEventListener("change", () => {
  const arquivo = inserirImagem.files[0];
  inserirImagem.value = "";
  inserirArquivo(arquivo, "imagem");
});
document.getElementById("arq-inserir-fim").addEventListener("click", (e) => {
  e.stopPropagation();
  if (sessao) abrirInserir(sessao.paginas.length, e.currentTarget);
});
document.addEventListener("click", (e) => {
  if (!caixaInserir.hidden && !caixaInserir.contains(e.target)) fecharInserir();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !caixaInserir.hidden) {
    const ancora = caixaInserir._ancora;
    fecharInserir();
    if (ancora) ancora.focus();
  }
});

function abrirSessao(alvo) {
  fecharInserir();
  if (sessao) sessao.fontes.slice(1).forEach(liberar);
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

function nomeDoResultado(nome, sufixo) {
  return semExtensao(nome) + "-" + sufixo + ".pdf";
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

// o corpo é a linha do plano e os arquivos colados em seguida; devolve o
// resultado ou lança com o motivo que o servidor deu
async function enviar(rota, arquivos, extra) {
  const plano = { arquivos: arquivos.map((a) => a.size), ...extra };
  const resposta = await fetch(rota, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", "X-Aide": "1" },
    body: new Blob([JSON.stringify(plano) + "\n", ...arquivos]),
    credentials: "same-origin",
  });
  if (!resposta.ok) {
    throw new Error(await resposta.json().then((d) => d.detail, () => "erro " + resposta.status));
  }
  return resposta.blob();
}

// organizar, juntar e imagens → PDF são a mesma rota: o que muda é a lista
function montar(arquivos, lista, extra) {
  return enviar("/api/arquivos/montar", arquivos, { paginas: lista, ...extra });
}

baixar.addEventListener("click", async () => {
  if (!sessao || !sessao.paginas.length || sessao.enviando) return;
  const atual = sessao;
  // só vai o que alguma página usa: uma inserção desfeita não sobe à toa
  const usadas = [...new Set(atual.paginas.map((p) => p.fonte))].sort((x, y) => x - y);
  const arquivos = usadas.map((f) => atual.fontes[f].arquivo);
  const lista = atual.paginas.map((p) => [usadas.indexOf(p.fonte), p.pagina - 1]);
  const nome = nomeDoResultado(atual.item.arquivo.name, "organizado");
  atual.enviando = true;
  baixar.disabled = true;
  avisar("Montando o PDF…");
  desenhar();
  try {
    entregar(await montar(arquivos, lista), nome);
    avisar("Pronto: " + paginas(atual.paginas.length) + " em " + nome + ".");
  } catch (erro) {
    avisar("Não deu para montar: " + erro.message, true);
  } finally {
    atual.enviando = false;
    desenhar();
    if (sessao === atual) redesenharGrade();
  }
});

// ---------- juntar e imagens → PDF: os marcados, na ordem que você arrumar ----------
// A mesma lista serve às duas ações: muda o tipo aceito, o título, o botão e
// o pedido. Imagem é uma página só, na orientação dela.

const LISTAS = {
  "juntar": {
    tipo: "pdf", minimo: 2, titulo: "Juntar PDFs", botao: "Baixar PDF juntado",
    verbo: "Juntando", falha: "Não deu para juntar",
    nome: (ordem) => nomeDoResultado(ordem[0].arquivo.name, "juntado"),
    paginas: (ordem) => ordem.flatMap((it, f) => Array.from({ length: it.paginas }, (_, p) => [f, p])),
    extra: {},
  },
  "imagens-pdf": {
    tipo: "imagem", minimo: 1, titulo: "Imagens → PDF", botao: "Baixar PDF",
    verbo: "Montando o PDF com", falha: "Não deu para montar",
    nome: (ordem) => semExtensao(ordem[0].arquivo.name) + ".pdf",
    paginas: (ordem) => ordem.map((_, f) => [f, 0]),
    extra: { imagens: "proprias" },
  },
};

function paginasDe(it) {
  return it.tipo === "pdf" ? it.paginas : 1;
}

function somaPaginas(lista) {
  return lista.reduce((soma, it) => soma + paginasDe(it), 0);
}

let ordemJuntar = [];
let juntando = false;

function sincronizarJuntar(marcados) {
  // quem continua marcado mantém o lugar; quem chegou entra no fim
  const modo = LISTAS[escolhida];
  if (!modo) return;
  const validos = marcados.filter((it) => serveAoTipo(it, modo.tipo));
  ordemJuntar = ordemJuntar.filter((it) => validos.includes(it))
    .concat(validos.filter((it) => !ordemJuntar.includes(it)));
}

function linhaJuntar(it, i) {
  const div = modeloJuntar.content.firstElementChild.cloneNode(true);
  div.dataset.indice = i;
  div.querySelector(".nome").textContent = it.arquivo.name;
  div.querySelector(".nome").title = it.arquivo.name;
  const tipo = div.querySelector(".tipo");
  tipo.dataset.tipo = it.tipo;
  tipo.textContent = extensao(it.arquivo.name).toUpperCase();
  const antes = somaPaginas(ordemJuntar.slice(0, i));
  div.querySelector(".quando").textContent = paginasDe(it) === 1 ? "pág " + (antes + 1)
    : "págs " + (antes + 1) + "–" + (antes + paginasDe(it));
  const subir = div.querySelector('[data-mover="-1"]');
  const descer = div.querySelector('[data-mover="1"]');
  subir.disabled = i === 0;
  descer.disabled = i === ordemJuntar.length - 1;
  subir.setAttribute("aria-label", "Subir " + it.arquivo.name);
  descer.setAttribute("aria-label", "Descer " + it.arquivo.name);
  subir.addEventListener("click", () => moverJuntar(i, i - 1, "-1"));
  descer.addEventListener("click", () => moverJuntar(i, i + 1, "1"));
  return div;
}

function desenharJuntar(foco) {
  const modo = LISTAS[escolhida];
  const visivel = Boolean(modo) && ordemJuntar.length >= modo.minimo;
  secaoJuntar.hidden = !visivel;
  if (!visivel) return;
  listaJuntar.replaceChildren(...ordemJuntar.map(linhaJuntar));
  const total = somaPaginas(ordemJuntar);
  document.getElementById("arq-juntar-titulo").textContent = modo.titulo;
  document.getElementById("arq-juntar-resumo").textContent = (modo.tipo === "pdf"
    ? ordemJuntar.length + " PDFs · " : "") + paginas(total) + " no total";
  baixarJuntado.lastChild.textContent = modo.botao;
  baixarJuntado.disabled = juntando;
  if (foco) {
    const alvo = listaJuntar.querySelector('[data-indice="' + foco.indice + '"]');
    const botao = alvo && foco.botao && alvo.querySelector('[data-mover="' + foco.botao + '"]');
    if (botao && !botao.disabled) botao.focus(); else if (alvo) alvo.focus();
  }
}

function moverJuntar(de, para, botao) {
  if (para < 0 || para >= ordemJuntar.length || de === para) return;
  const [it] = ordemJuntar.splice(de, 1);
  ordemJuntar.splice(para, 0, it);
  desenharJuntar({ indice: para, botao });
}

let arrastadaJuntar = null;

listaJuntar.addEventListener("dragstart", (e) => {
  const l = e.target.closest(".linha");
  if (!l) return;
  arrastadaJuntar = Number(l.dataset.indice);
  l.dataset.arrastando = "1";
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", ordemJuntar[arrastadaJuntar].arquivo.name);
});
listaJuntar.addEventListener("dragover", (e) => {
  if (arrastadaJuntar === null) return;
  e.preventDefault();
  const l = e.target.closest(".linha");
  for (const x of listaJuntar.querySelectorAll("[data-cair]")) if (x !== l) delete x.dataset.cair;
  if (!l) return;
  const caixa = l.getBoundingClientRect();
  l.dataset.cair = e.clientY > caixa.top + caixa.height / 2 ? "depois" : "antes";
});
listaJuntar.addEventListener("drop", (e) => {
  if (arrastadaJuntar === null) return;
  e.preventDefault();
  e.stopPropagation();
  const l = e.target.closest(".linha");
  const de = arrastadaJuntar;
  arrastadaJuntar = null;
  if (!l) return desenharJuntar();
  const caixa = l.getBoundingClientRect();
  let para = Number(l.dataset.indice) + (e.clientY > caixa.top + caixa.height / 2 ? 1 : 0);
  if (para > de) para--;
  if (para === de) return desenharJuntar();
  moverJuntar(de, para);
});
listaJuntar.addEventListener("dragend", () => { arrastadaJuntar = null; desenharJuntar(); });
listaJuntar.addEventListener("keydown", (e) => {
  const l = e.target.closest(".linha");
  if (!l || e.target !== l || !e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
  e.preventDefault();
  const i = Number(l.dataset.indice);
  moverJuntar(i, i + (e.key === "ArrowUp" ? -1 : 1));
});

baixarJuntado.addEventListener("click", async () => {
  const modo = LISTAS[escolhida];
  if (juntando || !modo || ordemJuntar.length < modo.minimo) return;
  const ordem = ordemJuntar.slice();
  const lista = modo.paginas(ordem);
  const nome = modo.nome(ordem);
  juntando = true;
  avisar(modo.verbo + " " + ordem.length + (modo.tipo === "pdf" ? " PDFs…" : " imagens…"));
  desenhar();
  try {
    const blob = await montar(ordem.map((it) => it.arquivo), lista, modo.extra);
    entregar(blob, nome);
    avisar("Pronto: " + paginas(lista.length) + " em " + nome + ".");
  } catch (erro) {
    avisar(modo.falha + ": " + erro.message, true);
  } finally {
    juntando = false;
    desenhar();
  }
});

// ---------- converter em lote: cada marcado vira outro arquivo ----------
// Documentos em PDF e PDFs em imagens: a mesma lista com a situação de cada
// um. Um resultado só volta direto; vários, num .zip.

const LOTES = {
  "converter": {
    tipo: "documento", titulo: "Converter para PDF", rota: "/api/arquivos/converter",
    nota: "pelo LibreOffice desta máquina",
    rodape: "vários documentos voltam num .zip, um PDF para cada",
    andando: "convertendo…", falha: "não converteu",
    botao: (docs) => docs.length === 1 ? "Converter e baixar PDF"
      : "Converter e baixar .zip com " + docs.length + " PDFs",
    aviso: (docs) => docs.length === 1 ? "Convertendo pelo LibreOffice…"
      : "Convertendo " + docs.length + " documentos pelo LibreOffice, um de cada vez…",
    nome: (docs) => docs.length === 1 ? semExtensao(docs[0].arquivo.name) + ".pdf"
      : "convertidos.zip",
  },
  "pdf-imagens": {
    tipo: "pdf", titulo: "PDF → imagens", rota: "/api/arquivos/imagens",
    nota: "uma PNG por página, a 150 dpi",
    rodape: "várias páginas voltam num .zip, numeradas",
    andando: "desenhando…", falha: "não desenhou",
    botao: (docs) => somaPaginas(docs) === 1 ? "Baixar PNG"
      : "Baixar .zip com " + somaPaginas(docs) + " imagens",
    aviso: () => "Desenhando as páginas…",
    nome: (docs) => somaPaginas(docs) === 1 ? semExtensao(docs[0].arquivo.name) + ".png"
      : (docs.length === 1 ? semExtensao(docs[0].arquivo.name) + "-imagens.zip" : "imagens.zip"),
  },
  "pdf-word": {
    tipo: "pdf", titulo: "PDF → Word", rota: "/api/arquivos/word",
    nota: "PDF escaneado não tem texto para tirar: ali o texto é foto",
    rodape: "vários PDFs voltam num .zip, um .docx para cada",
    andando: "convertendo…", falha: "não converteu",
    botao: (docs) => docs.length === 1 ? "Baixar .docx" : "Baixar .zip com " + docs.length + " .docx",
    aviso: () => "Convertendo para Word pelo LibreOffice…",
    nome: (docs) => docs.length === 1 ? semExtensao(docs[0].arquivo.name) + ".docx"
      : "convertidos.zip",
    extra: () => ({ modo: modoWord }),
  },
};

// PDF → Word: nenhum jeito serve para tudo, então a escolha é sua
const EXPLICA_WORD = {
  aparencia: "Fica igual ao PDF, com imagens e posições; cada linha vira uma caixa de texto — bom para retocar.",
  texto: "Só o texto, corrido, como um documento comum — edita fácil, mas perde imagens e diagramação.",
};
let modoWord = "aparencia";

for (const b of escolhaWord.querySelectorAll("[data-modo]")) {
  b.addEventListener("click", () => { modoWord = b.dataset.modo; situacao.clear(); desenhar(); });
}

let convertendo = false;
const situacao = new Map();  // item -> "pronto" | "erro" enquanto a lista não muda

function doLote(lote) {
  return itens.filter((it) => it.marcado && serveAoTipo(it, lote.tipo));
}

function desenharLote() {
  const lote = LOTES[escolhida];
  const docs = lote ? doLote(lote) : [];
  const visivel = docs.length > 0;
  secaoLote.hidden = !visivel;
  if (!visivel) return;
  document.getElementById("arq-lote-titulo").textContent = lote.titulo;
  document.getElementById("arq-lote-nota").textContent = lote.nota;
  document.getElementById("arq-lote-rodape").textContent = lote.rodape;
  escolhaWord.hidden = escolhida !== "pdf-word";
  for (const b of escolhaWord.querySelectorAll("[data-modo]")) {
    b.setAttribute("aria-pressed", String(b.dataset.modo === modoWord));
  }
  document.getElementById("arq-word-explica").textContent = EXPLICA_WORD[modoWord];
  listaLote.replaceChildren(...docs.map((it) => {
    const div = document.createElement("div");
    div.className = "linha";
    const estado = document.createElement("span");
    estado.className = "quando";
    const s = convertendo ? "convertendo" : situacao.get(it);
    estado.dataset.estado = s || "esperando";
    estado.textContent = { convertendo: lote.andando, pronto: "pronto", erro: lote.falha }[s]
      || medida(it);
    div.append(selo(it), rotulo(it), estado);
    return div;
  }));
  baixarLote.disabled = convertendo;
  baixarLote.lastChild.textContent = lote.botao(docs);
}

baixarLote.addEventListener("click", async () => {
  const lote = LOTES[escolhida];
  const docs = lote ? doLote(lote) : [];
  if (convertendo || !docs.length) return;
  const nome = lote.nome(docs);
  convertendo = true;
  situacao.clear();
  avisar(lote.aviso(docs));
  desenhar();
  try {
    const blob = await enviar(lote.rota, docs.map((it) => it.arquivo),
      { nomes: docs.map((it) => it.arquivo.name), ...(lote.extra ? lote.extra() : {}) });
    for (const it of docs) situacao.set(it, "pronto");
    entregar(blob, nome);
    avisar("Pronto: " + nome + ".");
  } catch (erro) {
    // o servidor diz qual falhou; os outros ficam como estavam
    for (const it of docs) if (erro.message.includes(it.arquivo.name)) situacao.set(it, "erro");
    avisar("Não deu: " + erro.message, true);
  } finally {
    convertendo = false;
    desenhar();
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
  const quanto = document.createElement("span");
  quanto.className = "quando mono";
  quanto.textContent = it.erro ? it.erro : medida(it);
  if (it.erro) div.dataset.erro = "1";
  const tirar = document.createElement("button");
  tirar.type = "button";
  tirar.className = "botao tirar-arq";
  tirar.title = "Tirar da lista";
  tirar.setAttribute("aria-label", "Tirar " + it.arquivo.name + " da lista");
  tirar.textContent = "×";
  tirar.addEventListener("click", () => {
    itens.splice(i, 1);
    liberar(it);
    avisar("");
    desenhar();
  });
  div.append(caixa, selo(it), rotulo(it), quanto, tirar);
  return div;
}

// pronto para a acao: do tipo pedido, aberto, e PDF com as paginas contadas
function serveAoTipo(it, tipo) {
  return it.tipo === tipo && !it.erro && (it.tipo !== "pdf" || Boolean(it.paginas));
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
  sincronizarJuntar(marcados);
  desenharJuntar();
  desenharLote();
}

for (const botao of botoes) {
  botao.addEventListener("click", () => {
    escolhida = botao.dataset.acao;
    avisar("");
    desenhar();
  });
}

limpar.addEventListener("click", () => {
  for (const it of itens) liberar(it);
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
