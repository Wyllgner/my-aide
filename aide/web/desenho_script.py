"""O JavaScript da tela de desenho, servido em /desenho.js.

Módulo à parte do /app.js porque importa o Excalidraw (`/vendor/excalidraw/`),
e só esta tela precisa dele: as notas não carregam 3 MB que não usam. Arquivo,
e não <script> embutido, pela mesma CSP (`script-src 'self'`).

Salva sozinho um segundo depois da última mudança, e na hora com Ctrl+S. Se o
arquivo mudou por fora desde que abriu, para e pergunta qual versão fica, como
as notas. A caixa de privado é o único caminho que manda `privada`: o
salvamento comum deixa o servidor manter o que está no disco.

A biblioteca de formas é uma só para todos os desenhos (Biblioteca.excalidrawlib
na raiz do vault) e salva à parte. Se ela não abriu, nunca é gravada: seria
trocar a sua biblioteca por uma vazia.
"""

from __future__ import annotations

JS = r"""
import {
  createElement, createRoot, Excalidraw, exportToBlob, serializeAsJSON,
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
// depois de apagar, nada mais é salvo: o salvamento recriaria o desenho
let apagado = false;
// a caixa mudou e o servidor ainda não confirmou: vai explícito no próximo
// salvamento. Sem ele, o servidor mantém o que está no disco
let privadaPedida = null;

// a prévia em PNG para ![[desenho]] nas notas: a assinatura que falta gerar
// (a do arquivo no disco) e se uma exportação está em andamento
let previaPendente = null;
let exportando = false;

// a biblioteca: versão lida (null = não abriu, então não grava), o último
// texto gravado e o timer próprio
let bibliotecaVersao = null;
let bibliotecaSalva = null;
let bibliotecaTimer = null;
let bibliotecaSalvando = false;
let bibliotecaDeNovo = null;
let bibliotecaAgendada = false;

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
  return api !== null && !apagado && conflito === null
    && (atual() !== salvo || privadaPedida !== null);
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
      if (!dados.previa) pedirPrevia(dados.assinatura);
      // a caixa pode ter mudado de novo enquanto este pedido ia
      if (privadaPedida === pedida) privadaPedida = null;
      if (privadaPedida === null) {
        caixaPrivada.checked = dados.privada;
        corretor(raiz);
      }
      avisar(atual() === salvo ? "salvo" : "alterado");
    } else if (resposta.status === 409) {
      mostrarConflito(dados);
    } else if (resposta.status === 413) {
      // quem recusa é a fronteira, antes da rota: a resposta não é JSON
      avisar("desenho grande demais para salvar (limite de 20 MB)", true);
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
  corretor(raiz);
  conflito = null;
  faixaConflito.hidden = true;
  avisar("salvo");
});

caixaPrivada.addEventListener("change", () => {
  privadaPedida = caixaPrivada.checked;
  corretor(raiz);
  salvar();
});

// apagar: como nas notas, o primeiro clique arma e o segundo manda para a
// lixeira do vault; sem o segundo em 4 s, desarma
const botaoApagar = document.getElementById("apagar");
const rotuloApagar = botaoApagar.querySelector(".rotulo");
let armado = null;

function desarmar() {
  clearTimeout(armado);
  armado = null;
  rotuloApagar.textContent = "apagar";
  delete botaoApagar.dataset.armado;
}

botaoApagar.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") desarmar();
});

botaoApagar.addEventListener("click", async () => {
  if (!armado) {
    rotuloApagar.textContent = "confirmar";
    botaoApagar.dataset.armado = "1";
    armado = setTimeout(desarmar, 4000);
    return;
  }
  desarmar();
  apagado = true;
  clearTimeout(timer);
  try {
    const resposta = await fetch("/api/desenhos/arquivo?caminho=" + encodeURIComponent(caminho),
                                 { method: "DELETE", headers: { "X-Aide": "1" } });
    if (!resposta.ok) {
      const dados = await resposta.json().catch(() => ({}));
      throw new Error(dados.detail || "não consegui apagar");
    }
    // volta para onde o "Notas" da barra levaria
    location.href = document.querySelector(".desenho-barra a.botao").getAttribute("href");
  } catch (e) {
    apagado = false;
    avisar(e.message === "Failed to fetch" ? "sem conexão com o my-aide" : e.message, true);
  }
});

// O corretor do navegador pode mandar o texto para fora (o "corretor
// avançado" do Chrome usa o Google). Em desenho privado, desligado em todo
// campo de texto do editor, como nas notas privadas. O Excalidraw cria o
// campo na hora de editar: vale quando ele entra na página, sem depender de
// evento de foco (que o navegador nem dispara com a janela em segundo plano).
function corretor(onde) {
  const campos = onde.matches && onde.matches("textarea, input")
    ? [onde] : onde.querySelectorAll ? onde.querySelectorAll("textarea, input") : [];
  for (const campo of campos) campo.spellcheck = !caixaPrivada.checked;
}

new MutationObserver((mudancas) => {
  for (const mudanca of mudancas) mudanca.addedNodes.forEach(corretor);
}).observe(raiz, { childList: true, subtree: true });

// em captura, antes do Excalidraw: o Ctrl+S dele abriria "salvar como"
window.addEventListener("keydown", (evento) => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "s") {
    evento.preventDefault();
    evento.stopPropagation();
    salvar();
  }
}, true);

// O Excalidraw só desenha no navegador: a prévia que as notas mostram é
// exportada aqui e vai para o servidor presa à assinatura da versão salva.
// Só quando a tela é essa versão (nada por salvar); senão a imagem mostraria o
// que não está no arquivo, e o próximo salvamento pede outra.
function pedirPrevia(daVersao) {
  previaPendente = daVersao;
  if (!exportando) gerarPrevia();
}

async function gerarPrevia() {
  const daVersao = previaPendente;
  previaPendente = null;
  if (daVersao === null || api === null || apagado || pendente()) return;
  const elementos = api.getSceneElements();
  // desenho vazio não tem o que mostrar
  if (elementos.length === 0) return;
  exportando = true;
  try {
    const png = await exportToBlob({
      elements: elementos,
      appState: { ...api.getAppState(), exportBackground: true, exportWithDarkMode: false },
      files: api.getFiles(),
      mimeType: "image/png",
      maxWidthOrHeight: 1600,
    });
    // a tela mudou durante a exportação: esta imagem já não é a versão salva
    if (!pendente()) {
      await fetch("/api/desenhos/previa?caminho=" + encodeURIComponent(caminho)
                  + "&assinatura=" + encodeURIComponent(daVersao),
                  { method: "PUT", headers: { "Content-Type": "image/png", "X-Aide": "1" },
                    body: png });
    }
  } catch (e) {
    // cache: sem prévia, a nota só mostra "abrir para gerar"
    console.warn("prévia do desenho não gerada", e);
  } finally {
    exportando = false;
    if (previaPendente !== null) gerarPrevia();
  }
}

function textoDaBiblioteca(itens) {
  return JSON.stringify({ type: "excalidrawlib", version: 2, source: "my-aide",
                          libraryItems: itens }, null, 2) + "\n";
}

function mudouBiblioteca(itens) {
  if (bibliotecaVersao === null) return;
  const texto = textoDaBiblioteca(itens);
  if (texto === bibliotecaSalva) return;
  clearTimeout(bibliotecaTimer);
  bibliotecaAgendada = true;
  bibliotecaTimer = setTimeout(() => {
    bibliotecaAgendada = false;
    salvarBiblioteca(texto);
  }, 500);
}

async function salvarBiblioteca(texto) {
  if (bibliotecaSalvando) { bibliotecaDeNovo = texto; return; }
  bibliotecaSalvando = true;
  try {
    const resposta = await pedir("PUT", "/api/desenhos/biblioteca",
                                 { texto: texto, versao: bibliotecaVersao });
    const dados = await resposta.json().catch(() => ({}));
    if (resposta.ok) {
      bibliotecaVersao = dados.versao;
      bibliotecaSalva = texto;
    } else if (resposta.status === 409) {
      // outra aba guardou formas no meio: junta as de lá com as daqui, e o
      // onLibraryChange que isso dispara grava a soma com a versão nova
      bibliotecaVersao = dados.versao;
      bibliotecaSalva = dados.texto;
      const deLa = JSON.parse(dados.texto).libraryItems || [];
      api.updateLibrary({ libraryItems: deLa, merge: true });
    } else {
      avisar(dados.detail || "não consegui salvar a biblioteca", true);
    }
  } catch (e) {
    avisar("sem conexão com o my-aide — a biblioteca não foi salva", true);
  } finally {
    bibliotecaSalvando = false;
    if (bibliotecaDeNovo !== null) {
      const proximo = bibliotecaDeNovo;
      bibliotecaDeNovo = null;
      salvarBiblioteca(proximo);
    }
  }
}

async function abrirBiblioteca() {
  try {
    const resposta = await fetch("/api/desenhos/biblioteca");
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || "");
    bibliotecaVersao = dados.versao;
    bibliotecaSalva = dados.texto;
    return JSON.parse(dados.texto).libraryItems || [];
  } catch (e) {
    avisar("a biblioteca de formas não abriu; ela não será salva", true);
    return [];
  }
}

window.addEventListener("beforeunload", (evento) => {
  // apagado, o desenho não tem mais o que perder; a biblioteca ainda tem
  const desenhoPorSalvar = !apagado && (salvando || conflito !== null || pendente());
  if (desenhoPorSalvar || bibliotecaSalvando || bibliotecaAgendada) {
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
  const formas = await abrirBiblioteca();
  versao = dados.versao;
  caixaPrivada.checked = dados.privada;
  caixaPrivada.disabled = false;
  createRoot(raiz).render(createElement(Excalidraw, {
    langCode: "pt-BR",
    initialData: {
      elements: cena.elements || [],
      appState: cena.appState || {},
      files: cena.files || {},
      libraryItems: formas,
      scrollToContent: true,
    },
    onLibraryChange: mudouBiblioteca,
    excalidrawAPI: (a) => {
      api = a;
    },
    onChange: (elementos, estadoDaTela, arquivos) => {
      if (api === null || conflito !== null) return;
      // a primeira chamada é a cena que acabou de abrir: é o que está no disco
      if (salvo === null) {
        salvo = assinatura(elementos, arquivos);
        // mexido por fora (Obsidian) ou de antes das prévias: gera agora
        if (!dados.previa) pedirPrevia(dados.assinatura);
        return;
      }
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
  // se a biblioteca não abriu, o aviso dela fica
  if (bibliotecaVersao !== null) avisar("aberto");
}

abrir();
"""
