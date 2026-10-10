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

O link de um elemento (Ctrl+K) que é [[Nota]], Nota.md ou [[x.excalidraw]]
abre aqui mesmo, depois de salvar; site de fora, em outra aba sem `opener`.
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
// depois de renomear, este caminho não existe mais: nada é salvo nele
let movido = false;
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
  return api !== null && !apagado && !movido && conflito === null
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

// renomear: o campo troca o nome (e a pasta, se quiser) na barra. Antes de
// mover, o que estiver por salvar vai para o caminho de agora; depois, a
// tela reabre no caminho novo. Os links das notas o servidor conserta.
const formRenomear = document.getElementById("renomear-form");
const campoRenomear = document.getElementById("renomear-nome");
const nomeNaBarra = document.getElementById("desenho-nome");

function mostrarRenomear(sim) {
  formRenomear.hidden = !sim;
  nomeNaBarra.hidden = sim;
  if (sim) { campoRenomear.focus(); campoRenomear.select(); }
}

async function esperarSalvar() {
  clearTimeout(timer);
  if (pendente()) await salvar();
  while (salvando) await new Promise((r) => setTimeout(r, 50));
}

document.getElementById("renomear").addEventListener("click", () => mostrarRenomear(true));
campoRenomear.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") mostrarRenomear(false);
});

formRenomear.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const novo = campoRenomear.value.trim().replace(/\.excalidraw$/i, "") + ".excalidraw";
  if (novo === caminho) { mostrarRenomear(false); return; }
  if (conflito !== null) {
    avisar("resolva o conflito antes de renomear", true);
    return;
  }
  try {
    await esperarSalvar();
    movido = true;
    const resposta = await pedir("POST", "/api/desenhos/mover", { de: caminho, para: novo });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(dados.detail || "não consegui renomear");
    const de = new URLSearchParams(location.search).get("de");
    location.replace("/desenho?caminho=" + encodeURIComponent(dados.caminho)
                     + (de ? "&de=" + encodeURIComponent(de) : ""));
  } catch (e) {
    movido = false;
    avisar(e.message === "Failed to fetch" ? "sem conexão com o my-aide" : e.message, true);
  }
});

// Links dos elementos (Ctrl+K no Excalidraw). [[Nota]], Nota.md ou
// [[Outro.excalidraw]] abrem aqui mesmo, resolvidos pelo servidor a partir da
// pasta do desenho, como um [[link]] numa nota de lá — depois de salvar.
// Site de fora abre em outra aba sem `opener` nem Referer; "//site" conta
// como de fora (o Excalidraw o abriria nesta aba, como endereço daqui).
const ESQUEMA = /^[a-z][a-z0-9+.-]*:/i;
const SITE = /^(https?|mailto):/i;

function linkDoElemento(elemento) {
  // o Excalidraw passa o link já trocado (" vira %22): o cru está na cena
  const naCena = api && api.getSceneElements().find((e) => e.id === elemento.id);
  return ((naCena && naCena.link) || elemento.link || "").trim();
}

function abrirLink(elemento, evento) {
  const link = linkDoElemento(elemento);
  if (!link) return;
  evento.preventDefault();
  if (ESQUEMA.test(link) || link.startsWith("//") || link.startsWith("/\\")) {
    if (SITE.test(link)) window.open(link, "_blank", "noopener,noreferrer");
    else avisar("esse link não abre daqui", true);
    return;
  }
  if (link.startsWith("/")) {
    // o navegador tira tab e quebra de linha do endereço: "/\t/site" vira
    // "//site", outro servidor. Sai só se o endereço montado for daqui
    const url = new URL(link, location.origin);
    if (url.origin !== location.origin) {
      avisar("esse link não abre daqui", true);
      return;
    }
    sair(url.pathname + url.search + url.hash);
    return;
  }
  irPeloVault(link);
}

async function irPeloVault(link) {
  let dados;
  try {
    const resposta = await fetch("/api/desenhos/link?caminho=" + encodeURIComponent(caminho)
                                 + "&alvo=" + encodeURIComponent(link));
    dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(dados.detail || "não consegui abrir o link");
  } catch (e) {
    avisar(e.message === "Failed to fetch" ? "sem conexão com o my-aide" : e.message, true);
    return;
  }
  if (!dados.existe) {
    oferecerCriar(dados);
    return;
  }
  sair(hrefDe(dados.tipo, dados.href));
}

function hrefDe(tipo, href) {
  // de desenho em desenho, o "Notas" continua voltando para a nota de origem
  const de = new URLSearchParams(location.search).get("de");
  return tipo === "desenho" && de ? href + "&de=" + encodeURIComponent(de) : href;
}

// o link pede o que não existe: como nas notas, dá para criar — mas aqui
// pergunta antes, porque o clique no link não diz que vai criar arquivo
const faixaFaltando = document.getElementById("link-faltando");
const botaoCriar = document.getElementById("link-criar");
let faltando = null;

function oferecerCriar(dados) {
  faltando = dados;
  document.getElementById("link-faltando-texto").textContent =
    (dados.tipo === "desenho" ? "O desenho " : "A nota ") + dados.caminho + " ainda não existe.";
  botaoCriar.disabled = false;
  faixaFaltando.hidden = false;
  botaoCriar.focus();
}

function esconderFaltando() {
  faltando = null;
  faixaFaltando.hidden = true;
}

document.getElementById("link-deixar").addEventListener("click", esconderFaltando);
faixaFaltando.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") esconderFaltando();
});

botaoCriar.addEventListener("click", async () => {
  if (faltando === null) return;
  const { tipo, caminho: novo } = faltando;
  botaoCriar.disabled = true;
  try {
    const resposta = await pedir("POST", tipo === "desenho" ? "/api/desenhos/arquivo"
                                                             : "/api/notas/arquivo", { caminho: novo });
    // 409: alguém criou no meio; abre o que já existe
    if (!resposta.ok && resposta.status !== 409) {
      const dados = await resposta.json().catch(() => ({}));
      throw new Error(dados.detail || "não consegui criar");
    }
  } catch (e) {
    botaoCriar.disabled = false;
    avisar(e.message === "Failed to fetch" ? "sem conexão com o my-aide" : e.message, true);
    return;
  }
  esconderFaltando();
  sair(hrefDe(tipo, tipo === "desenho" ? "/desenho?caminho=" + encodeURIComponent(novo)
                                       : "/notas?arquivo=" + encodeURIComponent(novo)));
});

// sai da tela só com tudo salvo; com conflito, ou se o salvamento falhou,
// fica (o aviso do salvamento já está na barra)
async function sair(href) {
  if (conflito !== null) {
    avisar("resolva o conflito antes de sair", true);
    return;
  }
  await esperarSalvar();
  if (pendente()) return;
  location.href = href;
}

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

// "N notas citam" fecha com clique fora ou Esc, como um menu; sem isso fica
// aberto por cima do desenho
const citadoPor = document.getElementById("citado-por");
if (citadoPor) {
  document.addEventListener("pointerdown", (evento) => {
    if (citadoPor.open && !citadoPor.contains(evento.target)) citadoPor.open = false;
  }, true);
  citadoPor.addEventListener("keydown", (evento) => {
    if (evento.key !== "Escape" || !citadoPor.open) return;
    citadoPor.open = false;
    citadoPor.querySelector("summary").focus();
  });
}

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
  const desenhoPorSalvar = !apagado && !movido
    && (salvando || conflito !== null || pendente());
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
    onLinkOpen: abrirLink,
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
