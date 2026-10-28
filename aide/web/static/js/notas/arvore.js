import {
  pedir, erroDe, abrir, pastaDe, guardarAviso, salvarAberta, notaAberta, semAcento,
} from "/js/notas/comum.js";

// ---------- árvore: a nota aberta à vista ----------
// num vault grande, a nota aberta pode estar lá embaixo na lateral
(function mostrarAberta() {
  var lateral = document.querySelector(".notas-lateral");
  var aberta = lateral && lateral.querySelector('.arvore .arquivo[aria-current="page"]');
  if (!aberta) { return; }
  var topo = aberta.offsetTop;
  if (topo < lateral.scrollTop || topo > lateral.scrollTop + lateral.clientHeight - 40) {
    lateral.scrollTop = topo - lateral.clientHeight / 2;
  }
})();

// ---------- árvore: filtrar por nome ----------
// esconde o que não bate (nome ou caminho, sem acento) e abre as pastas onde
// há resultado; limpo, as pastas voltam como estavam. Enter abre a primeira
// nota que sobrou, Esc limpa
var filtro = document.querySelector(".filtro-arvore");
if (filtro) {
  var arvore = filtro.closest(".arvore");
  var semResultado = arvore.querySelector(".filtro-vazio");
  var abertasAntes = null;
  var filtrarArvore = function () {
    var busca = semAcento(filtro.value.trim());
    var pastas = arvore.querySelectorAll("details");
    if (busca && abertasAntes === null) {
      abertasAntes = Array.prototype.filter.call(pastas, function (d) { return d.open; });
    }
    var algum = false;
    arvore.querySelectorAll(".arquivo").forEach(function (a) {
      var bate = !busca || semAcento(a.getAttribute("title") || a.textContent).indexOf(busca) >= 0;
      a.hidden = !bate;
      algum = algum || bate;
    });
    // de dentro para fora: a pasta aparece se tem nota que bate lá dentro
    Array.prototype.slice.call(pastas).reverse().forEach(function (d) {
      if (!busca) { d.hidden = false; return; }
      var tem = d.querySelector(".arquivo:not([hidden])") !== null;
      d.hidden = !tem;
      d.open = tem;
    });
    if (!busca && abertasAntes !== null) {
      pastas.forEach(function (d) { d.open = abertasAntes.indexOf(d) >= 0; });
      abertasAntes = null;
    }
    semResultado.hidden = !busca || algum;
  };
  filtro.addEventListener("input", filtrarArvore);
  filtro.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      filtro.value = "";
      filtrarArvore();
    } else if (e.key === "Enter") {
      var primeira = arvore.querySelector(".arquivo:not([hidden])");
      if (primeira && filtro.value.trim()) { e.preventDefault(); primeira.click(); }
    }
  });
}

// ---------- árvore: as pastas abertas ficam abertas ----------
// trocar de nota recarrega a página, e as pastas que você abriu fechavam.
// Ficam lembradas neste navegador (comodidade: sem isso, só fecham)
var PASTAS = "aide.notas.pastas";
var arvorePastas = document.querySelector(".arvore");
if (arvorePastas && arvorePastas.querySelector(".arvore-topo")) {
  var lembradas = [];
  try { lembradas = JSON.parse(localStorage.getItem(PASTAS) || "[]"); } catch (e) { lembradas = []; }
  arvorePastas.querySelectorAll("details[data-pasta]").forEach(function (d) {
    if (lembradas.indexOf(d.dataset.pasta) >= 0) { d.open = true; }
  });
  var guardarPastas = function () {
    // o filtro abre e fecha pastas sozinho: isso não é escolha sua
    if (filtro && filtro.value.trim()) { return; }
    var abertas = Array.prototype.filter.call(arvorePastas.querySelectorAll("details[data-pasta]"),
      function (d) { return d.open; }).map(function (d) { return d.dataset.pasta; });
    try { localStorage.setItem(PASTAS, JSON.stringify(abertas)); } catch (e) { /* sem armazenamento */ }
  };
  // toggle não sobe pela árvore: escuta na fase de captura
  arvorePastas.addEventListener("toggle", guardarPastas, true);
  document.getElementById("recolher-pastas").addEventListener("click", function () {
    if (filtro && filtro.value.trim()) { filtro.value = ""; filtrarArvore(); }
    arvorePastas.querySelectorAll("details[data-pasta]").forEach(function (d) { d.open = false; });
    guardarPastas();
  });
}

// ---------- árvore: arrastar nota ou pasta para outra pasta ----------
// solta em qualquer ponto de uma pasta — no nome dela, numa nota de dentro,
// no vazio dela — e o item vai para lá; fora de qualquer pasta, vai para a
// raiz do vault. Os links das outras notas acompanham, como no renomear.
// Parada em cima de uma pasta fechada, ela abre
var TIPO_NOTA = "application/x-aide-nota";
var TIPO_PASTA = "application/x-aide-pasta";
var arvoreArrasto = document.querySelector(".arvore");
if (arvoreArrasto && arvoreArrasto.querySelector(".arvore-topo")) {
  var abrirAoParar = null;
  // o que está sendo arrastado: o dataTransfer só se lê no drop
  var arrastado = null;
  var tipoDe = function (e) {
    var tipos = Array.prototype.slice.call((e.dataTransfer && e.dataTransfer.types) || []);
    return tipos.indexOf(TIPO_PASTA) >= 0 ? "pasta" : tipos.indexOf(TIPO_NOTA) >= 0 ? "nota" : null;
  };
  // a pasta onde cai: a <details> mais próxima, ou a raiz ("")
  var destinoDe = function (e) {
    if (!e.target.closest || !arvoreArrasto.contains(e.target)) { return null; }
    if (e.target.closest(".filtro-arvore")) { return null; }
    var pasta = e.target.closest("details[data-pasta]");
    return pasta && arvoreArrasto.contains(pasta) ? pasta : arvoreArrasto;
  };
  var marcaDe = function (destino) {
    return destino === arvoreArrasto ? arvoreArrasto.querySelector(".arvore-topo")
                                     : destino.querySelector(":scope > summary");
  };
  // a pasta não entra nela mesma nem em uma de dentro; e soltar onde já
  // está não muda nada
  var aceita = function (destino) {
    if (!arrastado) { return false; }
    var pasta = destino === arvoreArrasto ? "" : destino.dataset.pasta;
    if (pasta === pastaDe(arrastado.caminho)) { return false; }
    if (arrastado.tipo === "pasta" &&
        (pasta === arrastado.caminho || pasta.indexOf(arrastado.caminho + "/") === 0)) { return false; }
    return true;
  };
  var limparAlvos = function () {
    arvoreArrasto.querySelectorAll(".alvo-soltar").forEach(function (el) { el.classList.remove("alvo-soltar"); });
  };
  var comecar = function (el, tipo, caminho) {
    el.addEventListener("dragstart", function (e) {
      e.stopPropagation();
      arrastado = { tipo: tipo, caminho: caminho };
      e.dataTransfer.setData(tipo === "pasta" ? TIPO_PASTA : TIPO_NOTA, caminho);
      e.dataTransfer.effectAllowed = "move";
      el.classList.add("arrastando");
    });
    el.addEventListener("dragend", function () {
      el.classList.remove("arrastando");
      arrastado = null;
      limparAlvos();
      clearTimeout(abrirAoParar);
    });
  };
  arvoreArrasto.querySelectorAll(".arquivo[title]").forEach(function (a) {
    comecar(a, "nota", a.getAttribute("title"));
  });
  arvoreArrasto.querySelectorAll("details[data-pasta] > summary").forEach(function (resumo) {
    resumo.draggable = true;
    comecar(resumo, "pasta", resumo.parentElement.dataset.pasta);
  });
  arvoreArrasto.addEventListener("dragover", function (e) {
    var destino = destinoDe(e);
    if (!tipoDe(e) || !destino || !aceita(destino)) { limparAlvos(); return; }
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    var marca = marcaDe(destino);
    if (marca.classList.contains("alvo-soltar")) { return; }
    limparAlvos();
    marca.classList.add("alvo-soltar");
    clearTimeout(abrirAoParar);
    if (destino.tagName === "DETAILS" && !destino.open) {
      abrirAoParar = setTimeout(function () { destino.open = true; }, 700);
    }
  });
  arvoreArrasto.addEventListener("dragleave", function (e) {
    if (!arvoreArrasto.contains(e.relatedTarget)) { limparAlvos(); clearTimeout(abrirAoParar); }
  });
  arvoreArrasto.addEventListener("drop", function (e) {
    var destino = destinoDe(e);
    var tipo = tipoDe(e);
    if (!tipo || !destino || !aceita(destino)) { return; }
    e.preventDefault();
    limparAlvos();
    clearTimeout(abrirAoParar);
    var de = e.dataTransfer.getData(tipo === "pasta" ? TIPO_PASTA : TIPO_NOTA);
    var pasta = destino === arvoreArrasto ? "" : destino.dataset.pasta;
    var para = (pasta ? pasta + "/" : "") + de.replace(/^.*\//, "");
    if (!de || para === de) { return; }
    var aberta = notaAberta();
    // a nota aberta pode ser a que muda, ou ter links nela reescritos: salva antes
    var guardar = salvarAberta();
    // pasta e desenho têm a sua rota; nota tem a dela, que também reescreve os links
    var rota = tipo === "pasta" ? "/api/notas/mover-pasta"
      : /\.excalidraw$/i.test(de) ? "/api/desenhos/mover" : "/api/notas/mover";
    guardar.then(function () {
      return pedir("POST", rota, { de: de, para: para });
    }).then(function (r) {
      if (!r.ok) { return erroDe(r).then(function (m) { throw new Error(m); }); }
      return r.json().then(function (d) {
        guardarAviso(d);
        var depois = tipo === "pasta" ? d.notas_movidas[aberta] : aberta === de && d.caminho;
        if (depois) { abrir(depois); } else { location.reload(); }
      });
    }).catch(function (e2) {
      var aviso = arvoreArrasto.querySelector(".filtro-vazio");
      aviso.textContent = "não deu para mover: " + e2.message;
      aviso.hidden = false;
    });
  });
}
