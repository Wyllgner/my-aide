import {
  pedir, erroDe, abrir, nomeCurto, salvarAberta, semAcento, notasDoVault,
} from "/js/notas/comum.js";
import { pastaPadrao } from "/js/notas/criar.js";

// ---------- abrir nota rápido (Ctrl+O, como no Obsidian) ----------
// uma caixa no meio da tela: digite parte do nome ou do caminho e Enter
// abre. Vazia, mostra as últimas que você abriu. Sem nota com o nome
// digitado, a última opção cria uma, na pasta da nota aberta
var RECENTES = "aide.notas.recentes";
var seletor = null;

// só deste navegador: lembrar as últimas abertas é comodidade, não dado
function recentes() {
  try { return JSON.parse(localStorage.getItem(RECENTES) || "[]"); } catch (e) { return []; }
}
(function lembrarAberta() {
  var aberta = new URLSearchParams(location.search).get("arquivo");
  if (!aberta || notasDoVault.indexOf(aberta) < 0) { return; }
  var lista = [aberta].concat(recentes().filter(function (c) { return c !== aberta; })).slice(0, 12);
  try { localStorage.setItem(RECENTES, JSON.stringify(lista)); } catch (e) { /* sem armazenamento */ }
})();

// sem acento e em minuscula: toda busca por nome passa por aqui
// menor é melhor; -1 é fora. Nome que começa com a busca, depois nome que
// a contém, depois caminho; por último as letras do nome na ordem ("tlhd"
// → Telhado). Só no nome: no caminho inteiro, quase tudo casaria
function pontuar(nota, busca) {
  var tudo = semAcento(nota);
  var nome = nomeCurto(tudo);
  if (nome.indexOf(busca) === 0) { return 0; }
  if (nome.indexOf(busca) >= 0) { return 1; }
  if (tudo.indexOf(busca) >= 0) { return 2; }
  var i = 0;
  for (var k = 0; k < nome.length && i < busca.length; k++) { if (nome[k] === busca[i]) { i++; } }
  return i === busca.length ? 3 : -1;
}

function filtrarSeletor() {
  var s = seletor;
  var digitado = s.campo.value.trim();
  var busca = semAcento(digitado);
  var ordemRecente = recentes();
  var achadas;
  if (!busca) {
    achadas = ordemRecente.filter(function (c) { return notasDoVault.indexOf(c) >= 0; });
    achadas = achadas.concat(notasDoVault.filter(function (c) { return achadas.indexOf(c) < 0; }));
  } else {
    achadas = notasDoVault.map(function (c) { return [pontuar(c, busca), c]; })
      .filter(function (p) { return p[0] >= 0; })
      .sort(function (a, b) {
        var ra = ordemRecente.indexOf(a[1]);
        var rb = ordemRecente.indexOf(b[1]);
        return a[0] - b[0] || (ra < 0 ? 99 : ra) - (rb < 0 ? 99 : rb) || a[1].localeCompare(b[1]);
      })
      .map(function (p) { return p[1]; });
  }
  s.itens = achadas.slice(0, 40).map(function (c) { return { caminho: c }; });
  var exata = achadas.some(function (c) {
    return semAcento(nomeCurto(c)) === busca || semAcento(c) === busca;
  });
  if (digitado && !exata) {
    var pasta = pastaPadrao();
    var novo = digitado.indexOf("/") >= 0 || !pasta ? digitado : pasta + "/" + digitado;
    if (!/\.md$/i.test(novo)) { novo += ".md"; }
    s.itens.push({ caminho: novo, criar: true });
  }
  s.escolhido = 0;
  desenharSeletor();
}

function desenharSeletor() {
  var s = seletor;
  s.lista.textContent = "";
  s.itens.forEach(function (item, i) {
    var li = document.createElement("li");
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(i === s.escolhido));
    var nome = document.createElement("span");
    nome.textContent = item.criar ? "+ criar nota “" + nomeCurto(item.caminho) + "”"
      : nomeCurto(item.caminho);
    var onde = document.createElement("span");
    onde.className = "onde";
    onde.textContent = item.caminho;
    li.appendChild(nome);
    li.appendChild(onde);
    li.addEventListener("mousedown", function (e) { e.preventDefault(); irDoSeletor(item); });
    s.lista.appendChild(li);
    if (i === s.escolhido && li.scrollIntoView) { li.scrollIntoView({ block: "nearest" }); }
  });
  if (!s.itens.length) {
    var vazio = document.createElement("li");
    vazio.className = "vazio";
    vazio.textContent = "nenhuma nota";
    s.lista.appendChild(vazio);
  }
}

// quem sai da nota salva antes; se não deu para salvar, fica e avisa
function irDoSeletor(item) {
  var guardar = salvarAberta();
  guardar.then(function () {
    if (!item.criar) { abrir(item.caminho); return; }
    return pedir("POST", "/api/notas/arquivo", { caminho: item.caminho }).then(function (r) {
      if (r.ok || r.status === 409) { abrir(item.caminho); return; }
      return erroDe(r).then(function (m) { throw new Error(m); });
    });
  }).catch(function (e) { seletor.dica.textContent = e.message; });
}

function fecharSeletor() {
  if (!seletor) { return; }
  seletor.fundo.remove();
  if (seletor.antes && seletor.antes.focus) { seletor.antes.focus({ preventScroll: true }); }
  seletor = null;
}

function abrirSeletor() {
  if (seletor) { seletor.campo.focus(); return; }
  var fundo = document.createElement("div");
  fundo.className = "seletor-fundo";
  var caixaS = document.createElement("div");
  caixaS.className = "seletor";
  caixaS.setAttribute("role", "dialog");
  caixaS.setAttribute("aria-label", "abrir nota");
  var campo = document.createElement("input");
  campo.placeholder = "abrir nota… digite parte do nome";
  campo.setAttribute("aria-label", "nome da nota");
  campo.autocomplete = "off";
  campo.spellcheck = false;
  var lista = document.createElement("ul");
  lista.className = "seletor-lista";
  lista.setAttribute("role", "listbox");
  var dica = document.createElement("p");
  dica.className = "dica";
  dica.textContent = "↑ ↓ escolhe · Enter abre · Esc fecha";
  caixaS.appendChild(campo);
  caixaS.appendChild(lista);
  caixaS.appendChild(dica);
  fundo.appendChild(caixaS);
  document.body.appendChild(fundo);
  seletor = { fundo: fundo, campo: campo, lista: lista, dica: dica, itens: [], escolhido: 0,
    antes: document.activeElement };
  campo.addEventListener("input", filtrarSeletor);
  campo.addEventListener("keydown", function (e) {
    var s = seletor;
    if (e.key === "Escape") {
      e.preventDefault();
      fecharSeletor();
    } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && s.itens.length) {
      e.preventDefault();
      s.escolhido = (s.escolhido + (e.key === "ArrowDown" ? 1 : s.itens.length - 1)) % s.itens.length;
      desenharSeletor();
    } else if (e.key === "Enter" && s.itens.length) {
      e.preventDefault();
      irDoSeletor(s.itens[s.escolhido]);
    }
  });
  fundo.addEventListener("mousedown", function (e) { if (e.target === fundo) { fecharSeletor(); } });
  filtrarSeletor();
  campo.focus();
}

document.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key || "").toLowerCase() === "o") {
    e.preventDefault();
    abrirSeletor();
  }
});
var botaoAbrir = document.getElementById("abrir-rapido");
if (botaoAbrir) { botaoAbrir.addEventListener("click", abrirSeletor); }
