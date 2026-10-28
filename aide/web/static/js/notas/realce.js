// A copia colorida que fica por tras do campo transparente: o markdown do
// texto, marcado com <span> por classe. Sem pagina nenhuma no meio: serve
// ao campo da nota e ao bloco do ao vivo.
//
// Acima deste tamanho, colorir pesa mais do que ajuda: o campo fica sem cor.
var LIMITE_REALCE = 200000;

function esc(t) {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function span(classe, t) { return '<span class="' + classe + '">' + t + "</span>"; }

// dentro de uma linha já escapada: código primeiro, para nada dentro dele colorir
function realcarLinha(linha) {
  var pedacos = linha.split(/(`[^`]*`)/);
  return pedacos.map(function (p, i) {
    if (i % 2 === 1) { return span("r-codigo", p); }
    return p
      .replace(/(!?\[\[)([^\]\n]+?)(\]\])/g, function (m, a, meio, f) {
        return span("r-marca", a) + span("r-link", meio) + span("r-marca", f);
      })
      .replace(/(\[)([^\]]+)(\]\()([^)\s]+)(\))/g, function (m, a, t, b, url, f) {
        return span("r-marca", a) + span("r-link", t) + span("r-marca", b) + span("r-url", url) + span("r-marca", f);
      })
      .replace(/(\*\*|__)(?=\S)(.+?)(\1)/g, function (m, a, t, f) {
        return span("r-marca", a) + span("r-forte", t) + span("r-marca", f);
      })
      .replace(/(^|[^*\w])(\*|_)(?=\S)([^*_]+?)(\2)(?![*\w])/g, function (m, antes, a, t, f) {
        return antes + span("r-marca", a) + span("r-italico", t) + span("r-marca", f);
      })
      .replace(/(^|[\s(])(#[\w/-]*[^\W\d_][\w/-]*)/g, function (m, antes, tag) {
        return antes + span("r-tag", tag);
      });
  }).join("");
}

function realcar(texto) {
  var linhas = texto.split("\n");
  var saida = [];
  var cercado = false;
  var noFront = linhas[0] === "---";
  for (var i = 0; i < linhas.length; i++) {
    var l = esc(linhas[i]);
    if (noFront) {
      saida.push(span("r-front", l));
      if (i > 0 && linhas[i] === "---") { noFront = false; }
      continue;
    }
    if (/^\s*(```|~~~)/.test(linhas[i])) {
      cercado = !cercado;
      saida.push(span("r-codigo", l));
      continue;
    }
    if (cercado) { saida.push(span("r-codigo", l)); continue; }
    var titulo = /^(#{1,6} )(.*)$/.exec(l);
    if (titulo) { saida.push(span("r-marca", titulo[1]) + span("r-titulo", titulo[2])); continue; }
    if (/^\s*&gt;/.test(l)) { saida.push(span("r-citacao", l)); continue; }
    var tarefa = /^(\s*(?:[-*+]|\d+[.)])\s+)(\[[ xX]\])(.*)$/.exec(l);
    if (tarefa) {
      saida.push(span("r-marca", tarefa[1]) + span("r-link", tarefa[2]) + realcarLinha(tarefa[3]));
      continue;
    }
    var lista = /^(\s*(?:[-*+]|\d+[.)])\s+)(.*)$/.exec(l);
    if (lista) { saida.push(span("r-marca", lista[1]) + realcarLinha(lista[2])); continue; }
    saida.push(realcarLinha(l));
  }
  // a linha final vazia precisa de altura, senão o cursor no fim desalinha
  return saida.join("\n") + "\n ";
}

export { LIMITE_REALCE, realcar };
