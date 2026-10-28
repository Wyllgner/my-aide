// O que todas as partes das notas usam: pedir ao servidor, ler o erro que ele
// deu, montar enderecos e as listas do vault que a pagina trouxe.

function semAcento(t) {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// a marca que seguranca.py exige em toda escrita
function pedir(metodo, url, corpo) {
  return fetch(url, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Aide": "1" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    credentials: "same-origin",
  });
}

// o nome que aparece na tela: sem a pasta e sem o .md
function nomeCurto(caminho) {
  return caminho.replace(/^.*\//, "").replace(/\.md$/i, "");
}

// a pasta do caminho, sem a barra do fim ("" na raiz do vault)
function pastaDe(caminho) {
  var corte = caminho.lastIndexOf("/");
  return corte < 0 ? "" : caminho.slice(0, corte);
}

// a tela do desenho, com a nota de onde ele foi aberto: o "Notas" de la
// volta para ela
function hrefDoDesenho(caminho, de) {
  return "/desenho?caminho=" + encodeURIComponent(caminho)
    + (de ? "&de=" + encodeURIComponent(de) : "");
}

function abrir(caminho) {
  location.href = "/notas?arquivo=" + encodeURIComponent(caminho).replace(/%2F/g, "/");
}

// o editor (mais abaixo, so na tela de uma nota) publica o salvar em
// window.aideSalvar: quem move, renomeia ou sai manda salvar antes
function salvarAberta() {
  return window.aideSalvar ? window.aideSalvar() : Promise.resolve();
}

// o caminho da nota aberta, ou "" quando a tela e so a lista
function notaAberta() {
  var el = document.getElementById("editor");
  return el ? el.dataset.caminho : "";
}

function erroDe(resposta) {
  return resposta.json().then(
    function (d) { return d.detail || d.erro || "erro " + resposta.status; },
    function () { return "erro " + resposta.status; });
}

// o aviso que a página mostra depois de recarregar, num renomear ou mover
function guardarAviso(d) {
  var n = (d.links_atualizados || []).length;
  var pulou = d.links_nao_atualizados || [];
  var partes = [];
  if (n) { partes.push(n === 1 ? "1 nota teve o link atualizado" : n + " notas tiveram o link atualizado"); }
  var nd = (d.desenhos_atualizados || []).length;
  if (nd) { partes.push(nd === 1 ? "1 desenho teve o link atualizado" : nd + " desenhos tiveram o link atualizado"); }
  if (pulou.length) {
    partes.push("não consegui atualizar o link em " + pulou.join(", ") + " (arquivo ilegível ou sem permissão)");
  }
  try {
    sessionStorage.setItem("aide.notas.aviso", partes.join(" · "));
  } catch (e) { /* sem armazenamento: só não mostra o aviso */ }
}

// as notas e os desenhos do vault, que o servidor pos num data- da pagina:
// o abrir rapido e o autocompletar do [[ procuram neles
var raizNotas = document.querySelector(".notas[data-notas]");
var notasDoVault = [];
try { notasDoVault = JSON.parse((raizNotas && raizNotas.dataset.notas) || "[]"); } catch (e) { notasDoVault = []; }
var desenhosDoVault = [];
try { desenhosDoVault = JSON.parse((raizNotas && raizNotas.dataset.desenhos) || "[]"); } catch (e) { desenhosDoVault = []; }

export { pedir, nomeCurto, pastaDe, hrefDoDesenho, abrir, salvarAberta, notaAberta,
  erroDe, guardarAviso, semAcento, raizNotas, notasDoVault, desenhosDoVault };
