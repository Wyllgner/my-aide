"""O JavaScript da tela de desenho, servido em /desenho.js.

Módulo à parte do /app.js porque importa o Excalidraw (`/vendor/excalidraw/`),
e só esta tela precisa dele: as notas não carregam 3 MB que não usam. Arquivo,
e não <script> embutido, pela mesma CSP (`script-src 'self'`).

Salva sozinho um segundo depois da última mudança, e na hora com Ctrl+S. Se o
arquivo mudou por fora desde que abriu, para e pergunta qual versão fica, como
as notas. A caixa de privado é o único caminho que manda `privada`: o
salvamento comum deixa o servidor manter o que está no disco.
"""

from __future__ import annotations

JS = r"""
import {
  createElement, createRoot, Excalidraw, serializeAsJSON,
} from "/vendor/excalidraw/excalidraw.js";

const raiz = document.getElementById("desenho");
const estado = document.getElementById("desenho-estado");
const faixaConflito = document.getElementById("conflito");
const caixaPrivada = document.getElementById("privada");
const caminho = raiz.dataset.caminho;
const ESPERA = 1000;

let api = null;
let versao = null;
// o que está no disco, em "assinatura"; o que o editor tem agora é comparado
// com ela para saber se há algo a salvar
let salvo = null;
let timer = null;
let salvando = false;
let deNovo = false;
let conflito = null;
// a caixa mudou e o servidor ainda não confirmou: vai explícito no próximo
// salvamento. Sem ele, o servidor mantém o que está no disco
let privadaPedida = null;

function avisar(texto, erro) {
  estado.textContent = texto;
  estado.classList.toggle("erro", !!erro);
}

// Muda quando um elemento muda, entra ou sai (versão só cresce; apagado
// continua na lista com a versão nova) ou quando entra imagem. Rolar a tela e
// selecionar não mudam: não é motivo para gravar.
function assinatura(elementos, arquivos) {
  let soma = 0;
  for (const e of elementos) soma += e.version;
  return soma + ":" + elementos.length + ":" + Object.keys(arquivos || {}).length;
}

function atual() {
  return assinatura(api.getSceneElementsIncludingDeleted(), api.getFiles());
}

function pendente() {
  return api !== null && conflito === null && (atual() !== salvo || privadaPedida !== null);
}

function pedir(metodo, url, corpo) {
  return fetch(url, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Aide": "1" },
    body: JSON.stringify(corpo),
  });
}

function agendar() {
  clearTimeout(timer);
  timer = setTimeout(salvar, ESPERA);
}

async function salvar() {
  clearTimeout(timer);
  if (!pendente()) return;
  if (salvando) { deNovo = true; return; }
  salvando = true;
  const elementos = api.getSceneElementsIncludingDeleted();
  const arquivos = api.getFiles();
  const enviada = assinatura(elementos, arquivos);
  const texto = serializeAsJSON(elementos, api.getAppState(), arquivos, "local");
  const corpo = { caminho: caminho, texto: texto, versao: versao };
  const pedida = privadaPedida;
  if (pedida !== null) corpo.privada = pedida;
  avisar("salvando…");
  try {
    const resposta = await pedir("PUT", "/api/desenhos/arquivo", corpo);
    const dados = await resposta.json().catch(() => ({}));
    if (resposta.ok) {
      versao = dados.versao;
      salvo = enviada;
      // a caixa pode ter mudado de novo enquanto este pedido ia
      if (privadaPedida === pedida) privadaPedida = null;
      if (privadaPedida === null) caixaPrivada.checked = dados.privada;
      avisar(atual() === salvo ? "salvo" : "alterado");
    } else if (resposta.status === 409) {
      mostrarConflito(dados);
    } else {
      avisar(dados.detail || "não consegui salvar", true);
    }
  } catch (e) {
    avisar("sem conexão com o my-aide — tento de novo", true);
    timer = setTimeout(salvar, 5000);
  } finally {
    salvando = false;
    if (deNovo) { deNovo = false; salvar(); }
  }
}

function mostrarConflito(dados) {
  conflito = dados;
  faixaConflito.hidden = false;
  avisar("não salvo: mudou por fora", true);
}

document.getElementById("usar-meu").addEventListener("click", () => {
  // grava o que está na tela por cima do que está no disco
  versao = conflito.versao;
  conflito = null;
  faixaConflito.hidden = true;
  salvar();
});

document.getElementById("usar-disco").addEventListener("click", () => {
  const cena = JSON.parse(conflito.texto);
  const arquivos = cena.files || {};
  api.addFiles(Object.values(arquivos));
  api.updateScene({ elements: cena.elements || [] });
  versao = conflito.versao;
  salvo = atual();
  privadaPedida = null;
  caixaPrivada.checked = conflito.privada;
  conflito = null;
  faixaConflito.hidden = true;
  avisar("salvo");
});

caixaPrivada.addEventListener("change", () => {
  privadaPedida = caixaPrivada.checked;
  salvar();
});

// em captura, antes do Excalidraw: o Ctrl+S dele abriria "salvar como"
window.addEventListener("keydown", (evento) => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "s") {
    evento.preventDefault();
    evento.stopPropagation();
    salvar();
  }
}, true);

window.addEventListener("beforeunload", (evento) => {
  if (salvando || conflito !== null || pendente()) {
    evento.preventDefault();
    evento.returnValue = "";
  }
});

async function abrir() {
  let resposta;
  try {
    resposta = await fetch("/api/desenhos/arquivo?caminho=" + encodeURIComponent(caminho));
  } catch (e) {
    avisar("sem conexão com o my-aide", true);
    return;
  }
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    avisar(dados.detail || "não consegui abrir o desenho", true);
    return;
  }
  const cena = JSON.parse(dados.texto);
  versao = dados.versao;
  caixaPrivada.checked = dados.privada;
  caixaPrivada.disabled = false;
  createRoot(raiz).render(createElement(Excalidraw, {
    langCode: "pt-BR",
    initialData: {
      elements: cena.elements || [],
      appState: cena.appState || {},
      files: cena.files || {},
      scrollToContent: true,
    },
    excalidrawAPI: (a) => {
      api = a;
    },
    onChange: (elementos, estadoDaTela, arquivos) => {
      if (api === null || conflito !== null) return;
      // a primeira chamada é a cena que acabou de abrir: é o que está no disco
      if (salvo === null) { salvo = assinatura(elementos, arquivos); return; }
      if (assinatura(elementos, arquivos) !== salvo) {
        avisar("alterado");
        agendar();
      }
    },
    UIOptions: {
      canvasActions: {
        // quem salva é o my-aide; o "salvar como" do Excalidraw iria para o disco
        saveToActiveFile: false,
        // a página não tem tema escuro, e o tema iria para dentro do arquivo
        toggleTheme: false,
      },
    },
  }));
  avisar("aberto");
}

abrir();
"""
