// ---------- atalhos de escrita: no editor e no bloco do ao vivo ----------
// Ctrl+B negrito, Ctrl+I itálico, Ctrl+K link; Enter continua a lista (ou
// a citação) e, num item vazio, encerra; Tab e Shift+Tab mexem no recuo do
// item. Fora de lista, Tab segue o padrão (vai para o próximo controle)
var ITEM = /^(\s*)([-*+]|(\d+)([.)]))(\s+)(\[[ xX]\]\s+)?/;
var CITACAO = /^\s*>\s?/;

// execCommand mantém o Ctrl+Z e já dispara o input; onde não houver, troca direto
function trocar(campo, ini, fim, texto, cursorIni, cursorFim) {
  campo.setSelectionRange(ini, fim);
  if (!document.execCommand || !document.execCommand("insertText", false, texto)) {
    campo.setRangeText(texto, ini, fim, "end");
    campo.dispatchEvent(new Event("input"));
  }
  campo.setSelectionRange(cursorIni, cursorFim === undefined ? cursorIni : cursorFim);
}

// envolve a seleção com a marca; se ela já está envolta, tira
function envolver(campo, marca) {
  var a = campo.selectionStart;
  var b = campo.selectionEnd;
  var v = campo.value;
  var n = marca.length;
  var envolta = v.slice(a - n, a) === marca && v.slice(b, b + n) === marca &&
    // itálico dentro de negrito (**x**) não é itálico
    !(marca === "*" && v.charAt(a - 2) === "*" && v.charAt(b + 1) === "*");
  if (envolta) {
    trocar(campo, a - n, b + n, v.slice(a, b), a - n, b - n);
  } else {
    trocar(campo, a, b, marca + v.slice(a, b) + marca, a + n, b + n);
  }
}

// [seleção]() com o cursor nos parênteses; sem seleção, nos colchetes
function link(campo) {
  var a = campo.selectionStart;
  var b = campo.selectionEnd;
  var texto = campo.value.slice(a, b);
  var cursor = texto ? a + texto.length + 3 : a + 1;
  trocar(campo, a, b, "[" + texto + "]()", cursor);
}

function linhaDo(campo) {
  var v = campo.value;
  var ini = v.lastIndexOf("\n", campo.selectionStart - 1) + 1;
  var fim = v.indexOf("\n", campo.selectionStart);
  return { ini: ini, fim: fim < 0 ? v.length : fim, texto: v.slice(ini, fim < 0 ? v.length : fim) };
}

function continuarLista(campo) {
  var a = campo.selectionStart;
  if (a !== campo.selectionEnd) { return false; }
  var linha = linhaDo(campo);
  var m = linha.texto.match(ITEM);
  var marca;
  if (m) {
    // o próximo número; tarefa continua como tarefa, desmarcada
    marca = m[1] + (m[3] ? parseInt(m[3], 10) + 1 + m[4] : m[2]) + m[5] + (m[6] ? "[ ] " : "");
  } else {
    m = linha.texto.match(CITACAO);
    if (!m) { return false; }
    marca = m[0];
  }
  // o cursor antes do fim da marca: Enter normal
  if (a - linha.ini < m[0].length) { return false; }
  if (!linha.texto.slice(m[0].length).trim()) {
    // item vazio: o Enter encerra a lista, tirando a marca
    trocar(campo, linha.ini, linha.fim, "", linha.ini);
  } else {
    trocar(campo, a, a, "\n" + marca, a + 1 + marca.length);
  }
  return true;
}

function recuar(campo, voltar) {
  var linha = linhaDo(campo);
  if (!ITEM.test(linha.texto)) { return false; }
  var a = campo.selectionStart;
  var b = campo.selectionEnd;
  if (!voltar) {
    trocar(campo, linha.ini, linha.ini, "  ", a + 2, b + 2);
  } else {
    var tira = linha.texto.match(/^ {0,2}/)[0].length;
    if (tira) {
      trocar(campo, linha.ini, linha.ini + tira, "", Math.max(linha.ini, a - tira), Math.max(linha.ini, b - tira));
    }
  }
  return true;
}

function ligarAtalhos(campo) {
  campo.addEventListener("keydown", function (e) {
    var mod = (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey;
    var tecla = (e.key || "").toLowerCase();
    var feito = false;
    if (mod && tecla === "b") {
      envolver(campo, "**");
      feito = true;
    } else if (mod && tecla === "i") {
      envolver(campo, "*");
      feito = true;
    } else if (mod && tecla === "k") {
      link(campo);
      feito = true;
    } else if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
      feito = continuarLista(campo);
    } else if (e.key === "Tab" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      feito = recuar(campo, e.shiftKey);
    }
    if (feito) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  });
}

export { ligarAtalhos, trocar };
