import {
  pedir, erroDe, abrir, nomeCurto, pastaDe, hrefDoDesenho, guardarAviso, semAcento,
  notasDoVault, desenhosDoVault,
} from "/js/notas/comum.js";
import { LIMITE_REALCE, realcar } from "/js/notas/realce.js";
import { ligarAtalhos, trocar } from "/js/notas/atalhos.js";

// ---------- editor ----------
// O editor so existe na tela de uma nota. Ele fica numa funcao porque o
// "sem editor aqui, nada a ligar" e a primeira linha dele, e num modulo um
// return no topo e erro de sintaxe.
(function ligarEditor() {
  var editor = document.getElementById("editor");
  if (!editor) { return; }
  var caminho = editor.dataset.caminho;
  var versao = editor.dataset.versao;
  var estado = document.getElementById("estado");
  var privada = document.getElementById("privada");
  var conflito = document.getElementById("conflito");
  var salvo = editor.value;
  var espera = null;
  var salvando = false;
  var deDisco = null;
  var previa = document.getElementById("previa");
  var area = document.querySelector(".area");

  function mostrar(texto, tipo) {
    estado.textContent = texto;
    estado.dataset.estado = tipo;
  }

  // o motivo que o servidor deu, na barra de estado da nota
  function mostrarErro(r) {
    return erroDe(r).then(function (m) { mostrar(m, "erro"); });
  }

  // a promessa que estourou no caminho (sem conexao, ou o erro ja traduzido)
  function mostrarFalha(e) { mostrar(e.message, "erro"); }

  // ao vivo (mais abaixo): o bloco aberto, a prévia que chegou enquanto ele
  // estava aberto, e de que texto a prévia na tela veio. `mudancas` são os
  // blocos já fechados que mudaram de tamanho depois dela: com eles, as
  // linhas dos outros blocos continuam certas até a prévia nova chegar
  var bloco = null;
  var guardada = null;
  var previaVale = editor.value;
  var mudancas = [];

  // o HTML vem do renderizador do servidor, que é quem decide o que é seguro
  function mostrarPrevia(html, texto) {
    if (typeof html !== "string") { return; }
    // trocar a prévia agora apagaria o bloco onde você está escrevendo
    if (bloco) { guardada = { html: html, texto: texto }; return; }
    guardada = null;
    previa.innerHTML = html;
    previaVale = texto;
    mudancas = [];
    mostrarLinha();
  }

  function salvar() {
    clearTimeout(espera);
    if (salvando || editor.value === salvo || !conflito.hidden) { return Promise.resolve(); }
    salvando = true;
    var texto = editor.value;
    mostrar("salvando…", "salvando");
    return pedir("PUT", "/api/notas/arquivo", { caminho: caminho, texto: texto, versao: versao })
      .then(function (r) {
        if (r.ok) {
          return r.json().then(function (d) {
            versao = d.versao;
            salvo = texto;
            mostrarPrevia(d.html, texto);
            revelarAnexos();
            mostrar(editor.value === salvo ? "salvo" : "não salvo", editor.value === salvo ? "salvo" : "pendente");
          });
        }
        if (r.status === 409) {
          return r.json().then(function (d) {
            deDisco = d;
            conflito.hidden = false;
            mostrar("conflito", "erro");
          });
        }
        return mostrarErro(r);
      })
      .catch(function () { mostrar("sem conexão; não salvo", "erro"); })
      .then(function () {
        salvando = false;
        if (editor.value !== salvo && conflito.hidden) { agendar(); }
      });
  }

  // a pasta da nota aberta pode mudar de lugar: quem move salva antes
  // Salva e só segue se ficou mesmo salvo. Com conflito, sem conexão ou erro,
  // rejeita: renomear ou abrir outra nota por cima descartaria o que você
  // escreveu e ainda não está no disco
  function garantirSalvo() {
    return salvar().then(function () {
      if (editor.value !== salvo || !conflito.hidden) {
        throw new Error("salve a nota antes (há texto que não foi para o disco)");
      }
    });
  }
  window.aideSalvar = garantirSalvo;

  // ---------- exportar ----------
  // .md: o texto do campo, que é o da nota (no ao vivo também), sem passar
  // pelo servidor. PDF: a impressão do navegador, que o CSS de print deixa
  // só com o nome e a prévia — e a prévia precisa estar em dia com o texto
  var exportar = document.getElementById("exportar");
  var nomeDaNota = caminho.split("/").pop();

  document.getElementById("exportar-md").addEventListener("click", function () {
    exportar.open = false;
    fecharBloco();
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([editor.value], { type: "text/markdown;charset=utf-8" }));
    a.download = nomeDaNota;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });

  // salvo e com a prévia que veio desse texto: sem bloco do ao vivo ainda
  // esperando a prévia nova
  function previaEmDia() {
    return new Promise(function (pronto, falhou) {
      var tentativas = 0;
      (function ver() {
        if (!conflito.hidden) { falhou(new Error("resolva o conflito antes de exportar")); return; }
        if (!salvando && editor.value === salvo && !previa.querySelector(".bloco-pendente")) {
          pronto();
          return;
        }
        if (++tentativas > 100) { falhou(new Error("a prévia não ficou pronta; tente de novo")); return; }
        if (!salvando && editor.value !== salvo) { salvar(); }
        setTimeout(ver, 100);
      })();
    });
  }

  // a imagem de fora da tela (loading=lazy) ainda não carregou: sem esperar,
  // ela sai em branco no PDF
  function imagensCarregadas() {
    return Promise.all(Array.prototype.map.call(previa.querySelectorAll("img"), function (img) {
      img.loading = "eager";
      if (img.complete) { return null; }
      return new Promise(function (pronto) {
        img.addEventListener("load", pronto, { once: true });
        img.addEventListener("error", pronto, { once: true });
      });
    }));
  }

  document.getElementById("exportar-pdf").addEventListener("click", function () {
    exportar.open = false;
    fecharBloco();
    previaEmDia().then(imagensCarregadas).then(function () {
      // o título da página vira o nome sugerido do PDF
      var titulo = document.title;
      document.title = nomeDaNota.replace(/\.md$/i, "");
      window.addEventListener("afterprint", function () { document.title = titulo; }, { once: true });
      window.print();
    }).catch(mostrarFalha);
  });

  document.addEventListener("click", function (e) {
    if (exportar.open && !exportar.contains(e.target)) { exportar.open = false; }
  });

  function agendar() {
    clearTimeout(espera);
    mostrar("não salvo", "pendente");
    espera = setTimeout(salvar, 1000);
  }

  // o frontmatter é a verdade: a caixa só escreve ou tira a linha nele
  // igual a vault.separar: abre com uma linha "---" e fecha na próxima linha
  // que seja só "---"; pode vir vazio
  var FRONT = /^---\n(?:([\s\S]*?)\n)?---(?:\n|$)/;
  var LINHA = /^private:\s*(true|yes|sim|1)\s*$/im;

  function marcadaNoTexto() {
    var m = editor.value.match(FRONT);
    return !!(m && LINHA.test(m[1] || ""));
  }

  // o corretor avançado do Chrome manda o texto para o Google
  function corretor() { editor.spellcheck = !privada.checked; }

  privada.addEventListener("change", function () {
    var texto = editor.value;
    var m = texto.match(FRONT);
    var resto = m ? (m[1] || "").split("\n").filter(function (l) { return !/^private:/i.test(l); }) : [];
    var depois = m ? texto.slice(m[0].length) : "\n" + texto;
    if (privada.checked) { resto.push("private: true"); }
    editor.value = resto.join("").trim()
      ? "---\n" + resto.join("\n") + "\n---\n" + depois
      : depois.replace(/^\n/, "");
    corretor();
    agendarRealce();
    salvar();
  });

  editor.addEventListener("input", function () {
    privada.checked = marcadaNoTexto();
    corretor();
    agendar();
  });

  var realce = document.getElementById("realce");
  var pedidoRealce = null;
  function atualizarRealce() {
    if (!realce) { return; }
    if (editor.value.length > LIMITE_REALCE) {
      editor.classList.remove("colorido");
      realce.textContent = "";
      return;
    }
    editor.classList.add("colorido");
    realce.innerHTML = realcar(editor.value);
    realce.scrollTop = editor.scrollTop;
  }
  function agendarRealce() {
    if (pedidoRealce) { return; }
    pedidoRealce = requestAnimationFrame(function () { pedidoRealce = null; atualizarRealce(); });
  }
  if (realce) {
    atualizarRealce();
    editor.addEventListener("input", agendarRealce);
    editor.addEventListener("scroll", function () { realce.scrollTop = editor.scrollTop; });
    // o campo pode ser redimensionado pela alça; a cópia acompanha
    if (window.ResizeObserver) { new ResizeObserver(agendarRealce).observe(editor); }
  }
  window.aideRealcar = agendarRealce;

  // ---------- modos: editar, lado a lado, ao vivo, ler ----------
  var MODOS = ["editar", "dividido", "vivo", "ler"];

  // o Ctrl+E volta do ler para o modo de escrever que você usava
  var escrita = area.dataset.modo === "ler" ? "editar" : area.dataset.modo;

  function aplicarModo(modo) {
    if (MODOS.indexOf(modo) < 0) { return; }
    fecharBloco();
    if (modo !== "ler") { escrita = modo; }
    area.dataset.modo = modo;
    document.querySelectorAll(".modo").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.modo === modo));
    });
    // cookie, e não localStorage: o servidor lê e a página já nasce no modo
    document.cookie = "notas_modo=" + modo + "; path=/notas; max-age=31536000; SameSite=Strict";
  }

  document.querySelectorAll(".modo").forEach(function (b) {
    b.addEventListener("click", function () { aplicarModo(b.dataset.modo); });
  });

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      salvar();
    }
    // F2 renomeia, como no Obsidian
    if (e.key === "F2" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      document.getElementById("botao-renomear").click();
    }
    // Ctrl+E alterna entre escrever e ler, como no Obsidian
    if ((e.ctrlKey || e.metaKey) && e.key === "e") {
      e.preventDefault();
      aplicarModo(area.dataset.modo === "ler" ? escrita : "ler");
      if (campoVisivel()) { editor.focus(); }
    }
  });

  // ---------- lado a lado: as duas colunas rolam juntas ----------
  // linha a linha: o bloco que está no topo de uma coluna fica no topo da
  // outra. Cada bloco da prévia diz a linha do arquivo de onde veio
  // (data-fonte, data-bloco); a altura da mesma linha no campo vem de um
  // espelho dele. Entre dois blocos, a rolagem anda em reta. Quem começou a
  // rolar manda; a rolagem que ele provoca na outra coluna não volta para ele
  var rolando = null;
  var soltarRolagem = null;
  var mapaRolagem = null;

  // [x, y] crescentes nos dois: o y de um x, na reta entre os pares vizinhos
  function interpolar(pares, x) {
    if (!pares.length) { return 0; }
    if (x <= pares[0][0]) { return pares[0][1]; }
    for (var i = 1; i < pares.length; i++) {
      var a = pares[i - 1];
      var b = pares[i];
      if (x <= b[0]) {
        return b[0] === a[0] ? b[1] : a[1] + (x - a[0]) / (b[0] - a[0]) * (b[1] - a[1]);
      }
    }
    return pares[pares.length - 1][1];
  }

  // o topo de cada linha do campo, com as quebras que a largura dele faz
  function toposDasLinhas() {
    var espelho = document.createElement("div");
    var estilo = getComputedStyle(editor);
    ["fontFamily", "fontSize", "lineHeight", "padding", "letterSpacing", "tabSize"]
      .forEach(function (p) { espelho.style[p] = estilo[p]; });
    espelho.style.cssText += ";position:absolute;visibility:hidden;white-space:pre-wrap;" +
      "overflow-wrap:break-word;box-sizing:border-box;border:0;width:" + editor.clientWidth + "px";
    editor.value.split("\n").forEach(function (linha) {
      var d = document.createElement("div");
      d.textContent = linha || "\u200b";
      espelho.appendChild(d);
    });
    document.body.appendChild(espelho);
    var topos = Array.prototype.map.call(espelho.children, function (d) { return d.offsetTop; });
    document.body.removeChild(espelho);
    return topos;
  }

  // pares [topo no campo, topo na prévia], um por bloco; refeito quando o
  // texto, a prévia ou a altura de uma das colunas muda
  function paresDeRolagem() {
    var chave = [editor.value.length, editor.scrollHeight, editor.clientWidth,
      previa.scrollHeight, previa.clientWidth].join(",");
    if (mapaRolagem && mapaRolagem.chave === chave && mapaRolagem.texto === editor.value &&
        mapaRolagem.primeiro === previa.firstChild) {
      return mapaRolagem.pares;
    }
    var topos = editor.value.length > LIMITE_REALCE ? [] : toposDasLinhas();
    var base = previa.getBoundingClientRect().top - previa.scrollTop;
    var pares = [[0, 0]];
    if (topos.length) {
      previa.querySelectorAll("[data-fonte], [data-bloco]").forEach(function (el) {
        var linha = parseInt(el.dataset.fonte || el.dataset.bloco, 10);
        if (isNaN(linha) || linha >= topos.length || !el.offsetHeight) { return; }
        var par = [topos[linha], el.getBoundingClientRect().top - base];
        var ultimo = pares[pares.length - 1];
        if (par[0] > ultimo[0] && par[1] > ultimo[1]) { pares.push(par); }
      });
    }
    var fim = [editor.scrollHeight - editor.clientHeight, previa.scrollHeight - previa.clientHeight];
    // as pontas sempre se encontram: no fim de uma, a outra também está no fim
    while (pares.length > 1 && (pares[pares.length - 1][0] >= fim[0] ||
                                 pares[pares.length - 1][1] >= fim[1])) { pares.pop(); }
    pares.push(fim);
    mapaRolagem = { chave: chave, texto: editor.value, primeiro: previa.firstChild, pares: pares };
    return pares;
  }

  function acompanhar(de, para) {
    if (area.dataset.modo !== "dividido" || rolando === para) { return; }
    rolando = de;
    var pares = paresDeRolagem();
    if (de === previa) { pares = pares.map(function (p) { return [p[1], p[0]]; }); }
    para.scrollTop = interpolar(pares, de.scrollTop);
    clearTimeout(soltarRolagem);
    soltarRolagem = setTimeout(function () { rolando = null; }, 120);
  }
  editor.addEventListener("scroll", function () { acompanhar(editor, previa); });
  previa.addEventListener("scroll", function () { acompanhar(previa, editor); });

  // ---------- ao vivo: escrever na própria prévia ----------
  // a nota aparece formatada; clicar num bloco troca só ele pelo markdown das
  // linhas que o servidor marcou em data-bloco="início-fim". O campo da nota
  // (escondido) continua sendo o texto de verdade: cada tecla no bloco
  // remonta ele, e salvar, conflito e anexos seguem iguais. Ao sair do bloco,
  // a prévia nova vem do servidor.
  function campoVisivel() {
    return area.dataset.modo === "editar" || area.dataset.modo === "dividido";
  }

  // as linhas do bloco no texto de agora, contando os blocos que mudaram de
  // tamanho depois da prévia; null se ele mesmo já mudou. Um bloco pendente
  // (fechado, esperando a prévia nova) traz as linhas já contando as mudanças
  // até a dele: `data-desde` diz de qual em diante ainda falta contar
  function faixaDe(el) {
    var partes = el.dataset.bloco.split("-");
    var ini = parseInt(partes[0], 10);
    var fim = parseInt(partes[1], 10);
    if (isNaN(ini) || isNaN(fim)) { return null; }
    for (var i = parseInt(el.dataset.desde || "0", 10); i < mudancas.length; i++) {
      var m = mudancas[i];
      if (ini >= m.fim) { ini += m.delta; fim += m.delta; } else if (fim > m.ini) { return null; }
    }
    return [ini, fim];
  }

  // o texto que aparece antes do clique, dentro do bloco: o cursor vai para
  // o mesmo trecho no markdown (aproximado, mas cai no lugar quase sempre)
  function textoAteOClique(el, e) {
    var no = null;
    var desloc = 0;
    if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (p) { no = p.offsetNode; desloc = p.offset; }
    } else if (document.caretRangeFromPoint) {
      var r = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (r) { no = r.startContainer; desloc = r.startOffset; }
    }
    if (!no || !el.contains(no)) { return null; }
    var faixa = document.createRange();
    faixa.setStart(el, 0);
    faixa.setEnd(no, desloc);
    return faixa.toString();
  }

  function ajustarAltura(campo) {
    campo.style.height = "auto";
    campo.style.height = campo.scrollHeight + "px";
  }

  // el: o bloco clicado; sem ele, um bloco novo — no fim da nota, ou antes
  // da linha `novo.apos` e já com `novo.texto` (o Shift+Enter). `onde`
  // ("inicio" ou "fim") põe o cursor numa ponta, para quem chega pelas setas
  function abrirBloco(el, e, onde, novo) {
    if (bloco) { return; }
    var faixa = el ? faixaDe(el) : null;
    if (editor.value !== previaVale || (el && !faixa)) {
      // a prévia está atrás do texto: as linhas dela não valem mais
      mostrar("atualizando a prévia…", "salvando");
      salvar();
      return;
    }
    var linhas = editor.value.split("\n");
    var b = { el: el, original: editor.value };
    var fonte;
    if (faixa) {
      b.ini = faixa[0];
      b.fim = faixa[1];
      b.cabeca = b.ini > 0 ? linhas.slice(0, b.ini).join("\n") + "\n" : "";
      b.cauda = b.fim < linhas.length ? "\n" + linhas.slice(b.fim).join("\n") : "";
      fonte = linhas.slice(b.ini, b.fim).join("\n");
    } else {
      // separado dos vizinhos por uma linha vazia: sem ela, o texto novo
      // grudaria no parágrafo de cima (ou o de baixo grudaria nele)
      var apos = novo ? Math.min(novo.apos, linhas.length) : linhas.length;
      var acima = linhas.slice(0, apos).join("\n").replace(/\n*$/, "");
      var abaixo = linhas.slice(apos).join("\n").replace(/^\n+/, "");
      b.ini = b.fim = apos;
      b.cabeca = acima ? acima + "\n\n" : "";
      b.cauda = abaixo ? "\n\n" + abaixo : "\n";
      b.noFim = !abaixo;
      fonte = (novo && novo.texto) || "";
      // o lugar na página: antes do primeiro bloco que vem depois dele
      var depoisDele = null;
      previa.querySelectorAll("[data-bloco]").forEach(function (outro) {
        var f = faixaDe(outro);
        if (!depoisDele && f && f[0] >= apos) { depoisDele = outro; }
      });
    }
    // a linha onde o texto do bloco começa no texto de agora
    b.inicioReal = b.cabeca ? b.cabeca.split("\n").length - 1 : 0;
    b.fonte = fonte;
    // o bloco que o Shift+Enter abriu é o mesmo passo do de cima no desfazer
    b.juntar = !!novo;
    var campo = document.createElement("textarea");
    campo.className = "bloco-vivo";
    campo.value = fonte;
    campo.spellcheck = editor.spellcheck;
    campo.setAttribute("aria-label", "markdown do bloco");
    // as cores, como no modo editar: o campo transparente por cima de uma
    // cópia colorida do texto dele
    var caixa = document.createElement("div");
    caixa.className = "bloco-caixa";
    var copia = document.createElement("pre");
    copia.className = "realce";
    copia.setAttribute("aria-hidden", "true");
    caixa.appendChild(copia);
    caixa.appendChild(campo);
    b.campo = campo;
    b.caixa = caixa;
    b.colorir = function () {
      var cabe = campo.value.length <= LIMITE_REALCE;
      campo.classList.toggle("colorido", cabe);
      copia.innerHTML = cabe ? realcar(campo.value) : "";
    };
    b.colorir();
    bloco = b;
    if (el) {
      el.replaceWith(caixa);
    } else {
      previa.insertBefore(caixa, depoisDele);
      // veio com texto (o que estava depois do cursor): ele já sai do bloco
      // de cima e entra aqui
      if (fonte) {
        editor.value = b.cabeca + fonte + b.cauda;
        agendar();
      }
    }
    ajustarAltura(campo);

    var cursor = onde === "inicio" ? 0 : fonte.length;
    var antes = el && e ? textoAteOClique(el, e) : null;
    if (antes !== null && antes !== undefined) {
      var trecho = antes.slice(-16);
      var achado = trecho ? fonte.indexOf(trecho) : -1;
      cursor = !trecho ? 0 : achado >= 0 ? achado + trecho.length : cursor;
    }
    campo.focus({ preventScroll: true });
    campo.setSelectionRange(cursor, cursor);

    ligarSugestoes(campo);
    ligarAtalhos(campo);
    campo.addEventListener("input", function () {
      // escrever de novo depois de desfazer: o que foi desfeito não volta mais
      if (campo.value !== b.fonte) { refazer = []; }
      // o bloco do fim, apagado de volta: a nota fica como estava
      editor.value = !b.el && !campo.value ? b.original : b.cabeca + campo.value + b.cauda;
      ajustarAltura(campo);
      b.colorir();
      privada.checked = marcadaNoTexto();
      corretor();
      campo.spellcheck = editor.spellcheck;
      agendarRealce();
      agendar();
    });
    campo.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { ev.preventDefault(); campo.blur(); return; }
      // o Ctrl+Z do navegador só conhece este bloco: no bloco que ainda está
      // como abriu, ele é o da nota inteira
      var passo = passoPedido(ev);
      if (passo && campo.value === b.fonte && (passo === "desfazer" || refazer.length)) {
        ev.preventDefault();
        fecharBloco();
        andarNoHistorico(passo);
        return;
      }
      // Shift+Enter: um bloco novo embaixo, e não mais uma linha neste
      if (ev.key === "Enter" && ev.shiftKey && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
        ev.preventDefault();
        dividirBloco();
        return;
      }
      // seta para cima na primeira linha, ou para baixo na última: segue para
      // o bloco vizinho, como se a nota fosse um texto só
      var semMod = !ev.shiftKey && !ev.ctrlKey && !ev.metaKey && !ev.altKey &&
        campo.selectionStart === campo.selectionEnd;
      var antes = campo.value.slice(0, campo.selectionStart);
      if (semMod && ev.key === "ArrowUp" && antes.indexOf("\n") < 0) {
        ev.preventDefault();
        irAoVizinho(-1);
      } else if (semMod && ev.key === "ArrowDown" && campo.value.indexOf("\n", campo.selectionStart) < 0) {
        ev.preventDefault();
        irAoVizinho(1);
      }
    });
    campo.addEventListener("blur", function () {
      // trocou de janela: o bloco continua aberto e o foco volta para ele
      // e o blur de um bloco que já saiu (o Chrome dispara ao remover) não
      // fecha o que as setas acabaram de abrir
      if (!document.hasFocus() || bloco !== b) { return; }
      fecharBloco();
    });
  }

  // fecha o bloco aberto e abre o de cima (-1) ou o de baixo (1). O vizinho
  // é achado pelas linhas depois de fechar: se a prévia nova entrar nesse
  // meio-tempo, os elementos de antes já não estão na página. Embaixo do
  // último bloco, a seta para baixo começa um bloco novo no fim
  function irAoVizinho(direcao) {
    var b = bloco;
    // o bloco novo já é o fim da nota: para baixo não há nada
    if (direcao > 0 && b.noFim) { return; }
    var ini = b.ini;
    var fim = b.inicioReal + b.campo.value.split("\n").length;
    fecharBloco();
    var escolhido = null;
    previa.querySelectorAll("[data-bloco]").forEach(function (el) {
      var f = faixaDe(el);
      if (!f) { return; }
      if (direcao < 0 && f[1] <= ini) { escolhido = el; }
      if (direcao > 0 && !escolhido && f[0] >= fim) { escolhido = el; }
    });
    if (escolhido) {
      abrirBloco(escolhido, null, direcao < 0 ? "fim" : "inicio");
    } else if (direcao > 0) {
      abrirBloco(null);
    }
  }

  // o que vem depois do cursor vai para um bloco novo logo abaixo, aberto e
  // com o cursor no começo; com o cursor no fim, o bloco novo nasce vazio
  function dividirBloco() {
    var b = bloco;
    var campo = b.campo;
    // o espaço em volta do corte fica para trás ("frase. Outra" → "Outra")
    var antes = campo.value.slice(0, campo.selectionStart).replace(/[ \t]*\n*$/, "");
    var depois = campo.value.slice(campo.selectionEnd).replace(/^[ \t]*\n+/, "");
    if (!/\n$/.test(campo.value.slice(0, campo.selectionStart))) { depois = depois.replace(/^[ \t]+/, ""); }
    if (antes !== campo.value) {
      campo.value = antes;
      campo.dispatchEvent(new Event("input"));
    }
    // a linha logo depois do bloco de cima, já encurtado
    var apos = b.inicioReal + (antes ? antes.split("\n").length : 0);
    fecharBloco();
    abrirBloco(null, null, "inicio", { apos: apos, texto: depois });
  }

  function fecharBloco() {
    if (!bloco) { return; }
    var b = bloco;
    bloco = null;
    if (editor.value === b.original) {
      // nada mudou: o bloco de antes volta como estava
      if (b.el) { b.caixa.replaceWith(b.el); } else { b.caixa.remove(); }
    } else {
      // até a prévia nova chegar, o texto cru do bloco fica no lugar dele
      var pendente = document.createElement("div");
      pendente.className = "bloco-pendente";
      pendente.textContent = b.campo.value;
      b.caixa.replaceWith(pendente);
      // o quanto a nota cresceu ou encolheu: tudo o que vem depois do bloco anda junto
      mudancas.push({ ini: b.ini, fim: b.fim,
        delta: editor.value.split("\n").length - b.original.split("\n").length });
      // o pendente também se abre e é alcançado pelas setas, com as linhas
      // dele no texto de agora
      if (b.campo.value && editor.value !== b.original) {
        pendente.dataset.bloco = b.inicioReal + "-" + (b.inicioReal + b.campo.value.split("\n").length);
        pendente.dataset.desde = String(mudancas.length);
      }
      previaVale = editor.value;
      registrar(b.original, editor.value, b.inicioReal, b.juntar);
    }
    if (guardada && guardada.texto === editor.value) {
      mostrarPrevia(guardada.html, guardada.texto);
      revelarAnexos();
    } else if (editor.value !== b.original) {
      salvar();
    }
  }

  // ---------- desfazer no ao vivo ----------
  // cada bloco é um campo novo, e o Ctrl+Z do navegador só conhece o que se
  // digitou nele: ao fechar o bloco, esse histórico ia embora junto. Aqui a
  // nota guarda o texto de antes e de depois de cada bloco fechado (e de
  // cada caixa de tarefa), e o Ctrl+Z fora de um bloco — ou num bloco que
  // ainda não mudou — volta a nota inteira um passo. Só vale enquanto o
  // texto é o que o histórico deixou: mexido por outro caminho (o modo
  // editar, o conflito), ele recomeça em vez de apagar o que mudou.
  var desfazer = [];
  var refazer = [];
  var PASSOS = 200;
  // a linha que o último desfazer mexeu: a prévia nova rola até ela
  var linhaMexida = null;

  function registrar(antes, depois, linha, juntar) {
    if (antes === depois) { return; }
    var topo = desfazer[desfazer.length - 1];
    if (juntar && topo && topo.depois === antes) {
      topo.depois = depois;
    } else {
      desfazer.push({ antes: antes, depois: depois, linha: linha });
      if (desfazer.length > PASSOS) { desfazer.shift(); }
    }
    refazer = [];
  }

  function passoPedido(e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) { return null; }
    var tecla = (e.key || "").toLowerCase();
    if (tecla === "z") { return e.shiftKey ? "refazer" : "desfazer"; }
    if (tecla === "y" && !e.shiftKey) { return "refazer"; }
    return null;
  }

  function andarNoHistorico(pedido) {
    var de = pedido === "desfazer" ? desfazer : refazer;
    var para = pedido === "desfazer" ? refazer : desfazer;
    var passo = de.pop();
    if (!passo) {
      mostrar(pedido === "desfazer" ? "nada para desfazer" : "nada para refazer", "pendente");
      return;
    }
    var esperado = pedido === "desfazer" ? passo.depois : passo.antes;
    if (editor.value !== esperado || !conflito.hidden) {
      desfazer = [];
      refazer = [];
      mostrar("a nota mudou por outro caminho; não há o que desfazer", "pendente");
      return;
    }
    editor.value = pedido === "desfazer" ? passo.antes : passo.depois;
    para.push(passo);
    linhaMexida = passo.linha;
    privada.checked = marcadaNoTexto();
    corretor();
    agendarRealce();
    // a prévia na tela é do texto de antes; a nova vem com o salvamento. Se
    // o texto voltou a ser o que está no disco, salvar não iria ao servidor
    if (editor.value === salvo) { salvo = null; }
    salvar();
  }

  function mostrarLinha() {
    if (linhaMexida == null || previaVale !== editor.value) { return; }
    var linha = linhaMexida;
    linhaMexida = null;
    var achado = null;
    previa.querySelectorAll("[data-bloco]").forEach(function (el) {
      var f = el.dataset.bloco.split("-");
      if (!achado && parseInt(f[1], 10) > linha) { achado = el; }
    });
    if (achado) { achado.scrollIntoView({ block: "nearest" }); }
  }

  document.addEventListener("keydown", function (e) {
    if (area.dataset.modo !== "vivo" || bloco) { return; }
    // nos campos de verdade (busca, renomear) o Ctrl+Z é o deles
    if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable]")) { return; }
    var passo = passoPedido(e);
    if (!passo) { return; }
    e.preventDefault();
    andarNoHistorico(passo);
  });

  previa.addEventListener("click", function (e) {
    if (area.dataset.modo !== "vivo" || bloco) { return; }
    var alvo = e.target;
    // link, caixa de tarefa, player e o título do callout que dobra fazem o
    // que já faziam
    if (alvo.closest("a, input, button, audio, video, textarea, summary")) { return; }
    // selecionando um trecho para copiar
    if (String(window.getSelection() || "")) { return; }
    var el = alvo.closest("[data-bloco]");
    if (el && previa.contains(el)) { abrirBloco(el, e); return; }
    // no espaço vazio embaixo do último bloco: escrever no fim da nota
    var ultimo = previa.lastElementChild;
    if (alvo === previa && (!ultimo || e.clientY > ultimo.getBoundingClientRect().bottom)) {
      abrirBloco(null, e);
    }
  });

  // ---------- renomear e mover ----------
  var titulo = document.getElementById("titulo");
  var renomear = document.getElementById("renomear");
  var campoCaminho = document.getElementById("renomear-caminho");
  var erroRenomear = document.getElementById("renomear-erro");

  function abrirRenomear() {
    titulo.hidden = true;
    renomear.hidden = false;
    erroRenomear.textContent = "";
    campoCaminho.focus();
    campoCaminho.select();
  }

  function fecharRenomear() {
    renomear.hidden = true;
    titulo.hidden = false;
    campoCaminho.value = nomeCurto(caminho);
  }

  titulo.addEventListener("click", abrirRenomear);
  document.getElementById("botao-renomear").addEventListener("click", abrirRenomear);
  campoCaminho.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { fecharRenomear(); }
  });
  renomear.addEventListener("submit", function (e) {
    e.preventDefault();
    var novo = campoCaminho.value.trim().replace(/^\/+|\/+$/g, "");
    if (!novo) { return; }
    // o campo é só o nome; com uma "/" no meio, vale como caminho desde a
    // raiz do vault (mudar de pasta, no dia a dia, é arrastar na árvore)
    var pastaAtual = pastaDe(caminho) ? pastaDe(caminho) + "/" : "";
    if (novo.indexOf("/") < 0) { novo = pastaAtual + novo; }
    if (!/\.md$/i.test(novo)) { novo += ".md"; }
    if (novo === caminho) { fecharRenomear(); return; }
    // o que ainda não foi salvo vai antes: o arquivo muda de lugar
    garantirSalvo().then(function () {
      return pedir("POST", "/api/notas/mover", { de: caminho, para: novo });
    }).then(function (r) {
      if (r.ok) {
        return r.json().then(function (d) {
          guardarAviso(d);
          salvo = editor.value;
          abrir(d.caminho);
        });
      }
      return erroDe(r).then(function (m) { erroRenomear.textContent = m; });
    }).catch(function (e) { erroRenomear.textContent = e.message; });
  });

  // o aviso deixado por um renomear, na página da nota já com o nome novo
  try {
    var aviso = sessionStorage.getItem("aide.notas.aviso");
    if (aviso) { mostrar(aviso, "salvo"); }
    sessionStorage.removeItem("aide.notas.aviso");
  } catch (e) { /* idem */ }

  // ---------- link quebrado: um clique cria a nota ----------
  function criarDoLink(e) {
    var link = e.target.closest("a.quebrado");
    if (!link) { return; }
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") { return; }
    e.preventDefault();
    var alvo = link.dataset.alvo.trim();
    if (!alvo) { return; }
    var pasta = pastaDe(caminho);
    var novo = (alvo.indexOf("/") >= 0 || !pasta ? alvo : pasta + "/" + alvo);
    if (/\.excalidraw$/i.test(novo)) {
      // [[Planta.excalidraw]] pede um desenho, não uma nota Planta.excalidraw.md
      garantirSalvo().then(function () {
        return pedir("POST", "/api/desenhos/arquivo", { caminho: novo });
      }).then(function (r) {
        if (r.ok || r.status === 409) {
          location.href = hrefDoDesenho(novo, caminho);
        } else {
          mostrarErro(r);
        }
      }).catch(mostrarFalha);
      return;
    }
    if (!/\.md$/i.test(novo)) { novo += ".md"; }
    garantirSalvo().then(function () {
      return pedir("POST", "/api/notas/arquivo", { caminho: novo });
    }).then(function (r) {
      if (r.ok || r.status === 409) { abrir(novo); } else { mostrarErro(r); }
    }).catch(mostrarFalha);
  }
  // ---------- tarefa marcada na prévia ----------
  // a caixa diz a linha; o script troca [ ] por [x] no texto e salva. Se o
  // texto mudou desde a última prévia, a linha pode não ser mais a tarefa:
  // aí não mexe em nada e espera a prévia nova
  var TAREFA = /^(\s*(?:[-*+]|\d+[.)])\s+\[)([ xX])(\])/;
  previa.addEventListener("change", function (e) {
    var caixa = e.target;
    if (!caixa.matches || !caixa.matches("input[data-linha]")) { return; }
    var linhas = editor.value.split("\n");
    var n = parseInt(caixa.dataset.linha, 10);
    var casado = TAREFA.exec(linhas[n] || "");
    var estavaFeita = !caixa.checked;
    if (!casado || (casado[2] !== " ") !== estavaFeita || editor.value !== salvo || !conflito.hidden) {
      caixa.checked = estavaFeita;
      mostrar("a prévia está atrás do texto; tente de novo", "pendente");
      salvar();
      return;
    }
    linhas[n] = linhas[n].replace(TAREFA, "$1" + (caixa.checked ? "x" : " ") + "$3");
    var antes = editor.value;
    editor.value = linhas.join("\n");
    if (area.dataset.modo === "vivo") { registrar(antes, editor.value, n); }
    agendarRealce();
    salvar();
  });

  previa.addEventListener("click", criarDoLink);
  previa.addEventListener("keydown", criarDoLink);

  // ---------- anexos: colar, arrastar ou escolher ----------
  // o arquivo vai para o vault (POST /api/notas/anexo) e o ![[...]] entra
  // onde o cursor está, como no Obsidian
  function inserirNoCursor(texto) {
    // ao vivo, com um bloco aberto: entra no cursor do bloco
    var alvo = bloco ? bloco.campo : editor;
    if (!bloco && !campoVisivel()) {
      // o campo está escondido e o cursor dele pode estar no começo, antes
      // do frontmatter: no modo ler (e ao vivo sem bloco aberto) o anexo vai
      // para o fim da nota
      editor.setSelectionRange(editor.value.length, editor.value.length);
      texto = (/\n$/.test(editor.value) || !editor.value ? "" : "\n") + texto + "\n";
    }
    alvo.focus({ preventScroll: true });
    // execCommand mantém o Ctrl+Z; onde não houver, troca direto
    if (!document.execCommand || !document.execCommand("insertText", false, texto)) {
      alvo.setRangeText(texto, alvo.selectionStart, alvo.selectionEnd, "end");
      alvo.dispatchEvent(new Event("input"));
    }
  }

  function enviarAnexo(arquivo, nome) {
    var url = "/api/notas/anexo?nota=" + encodeURIComponent(caminho) +
      "&nome=" + encodeURIComponent(nome);
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": arquivo.type || "application/octet-stream", "X-Aide": "1" },
      body: arquivo,
      credentials: "same-origin",
    }).then(function (r) {
      if (!r.ok) {
        return erroDe(r).then(function (m) { throw new Error(arquivo.name + ": " + m); });
      }
      return r.json();
    });
  }

  // a captura de tela chega da área de transferência como "image.png":
  // sem nome de verdade, o servidor dá "Captura <data hora>"
  var CAPTURA = /^image\.(png|jpe?g|gif|webp|bmp)$/i;

  // os anexos recém-postos: na próxima prévia, ela rola até eles e pisca —
  // no modo ler o link vai para o fim da nota, e sem isso nada apareceria
  var aRevelar = [];
  function revelarAnexos() {
    // com um bloco aberto a prévia nova ainda não entrou: espera ela
    if (!aRevelar.length || bloco) { return; }
    var achado = null;
    previa.querySelectorAll("[src], a.anexo[href]").forEach(function (el) {
      var url = el.getAttribute("src") || el.getAttribute("href") || "";
      var m = url.match(/[?&]caminho=([^&]*)/);
      var caminhoAnexo = m ? decodeURIComponent(m[1]) : "";
      if (aRevelar.indexOf(caminhoAnexo) >= 0) {
        el.classList.add("destaque");
        achado = achado || el;
      }
    });
    aRevelar = [];
    if (achado && area.dataset.modo !== "editar") { achado.scrollIntoView({ block: "center" }); }
  }

  function anexar(arquivos, colado) {
    if (!arquivos.length) { return; }
    var links = [];
    mostrar(arquivos.length > 1 ? "enviando " + arquivos.length + " anexos…" : "enviando anexo…", "salvando");
    // um de cada vez, na ordem: os links saem na ordem em que foram escolhidos
    return arquivos.reduce(function (antes, arquivo) {
      return antes.then(function () {
        return enviarAnexo(arquivo, colado && CAPTURA.test(arquivo.name) ? "" : arquivo.name)
          .then(function (d) { links.push(d.link); aRevelar.push(d.caminho); });
      });
    }, Promise.resolve()).then(function () {
      inserirNoCursor(links.join("\n"));
    }).catch(function (e) {
      if (links.length) { inserirNoCursor(links.join("\n")); }
      mostrarFalha(e);
    });
  }

  // na página inteira, e não só no campo: no modo ler o campo está escondido
  // e o foco fica na prévia ou em lugar nenhum. Outro campo (busca, renomear,
  // nome da nota nova) cola o que for nele, normal
  function arquivosColados(e) {
    var dados = e.clipboardData;
    if (!dados) { return []; }
    var arquivos = Array.prototype.slice.call(dados.files || []);
    if (!arquivos.length && dados.items) {
      Array.prototype.forEach.call(dados.items, function (item) {
        var arquivo = item.kind === "file" && item.getAsFile();
        if (arquivo) { arquivos.push(arquivo); }
      });
    }
    return arquivos;
  }
  document.addEventListener("paste", function (e) {
    var alvo = e.target;
    if (alvo !== editor && !(bloco && alvo === bloco.campo) && alvo && alvo.matches &&
        alvo.matches("input, textarea, [contenteditable]")) {
      return;
    }
    var arquivos = arquivosColados(e);
    if (!arquivos.length) { return; }  // texto: cola normal
    e.preventDefault();
    anexar(arquivos, true);
  });

  var soltando = 0;
  function temArquivo(e) {
    return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0;
  }
  area.addEventListener("dragenter", function (e) {
    if (!temArquivo(e)) { return; }
    soltando++;
    area.classList.add("soltando");
  });
  area.addEventListener("dragover", function (e) {
    if (!temArquivo(e)) { return; }
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  area.addEventListener("dragleave", function (e) {
    if (!temArquivo(e)) { return; }
    soltando = Math.max(0, soltando - 1);
    if (!soltando) { area.classList.remove("soltando"); }
  });
  area.addEventListener("drop", function (e) {
    if (!temArquivo(e)) { return; }
    e.preventDefault();
    soltando = 0;
    area.classList.remove("soltando");
    // solto no texto: o link entra onde o arquivo caiu
    var solto = bloco && e.target === bloco.campo ? bloco.campo : e.target === editor ? editor : null;
    if (solto && document.caretPositionFromPoint) {
      var ponto = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (ponto && ponto.offsetNode === solto) { solto.setSelectionRange(ponto.offset, ponto.offset); }
    }
    anexar(Array.prototype.slice.call(e.dataTransfer.files), false);
  });

  var escolher = document.getElementById("escolher-anexo");
  document.getElementById("botao-anexar").addEventListener("click", function () { escolher.click(); });
  escolher.addEventListener("change", function () {
    anexar(Array.prototype.slice.call(escolher.files), false);
    escolher.value = "";
  });

  // ---------- chegar no link citado ----------
  // a lista de links quebrados abre a nota com ?linha=&alvo=: a prévia rola
  // até o link e pisca, e o campo seleciona o link no texto
  // onde o caractere `posicao` do campo cai, num espelho escondido com o
  // mesmo estilo dele: a linha pode quebrar em varias, e so o navegador sabe
  // onde. Serve para rolar ate o cursor e para por a lista de sugestoes nele
  function medirCursor(campo, posicao) {
    var espelho = document.createElement("div");
    var estilo = getComputedStyle(campo);
    ["fontFamily", "fontSize", "lineHeight", "padding", "border", "letterSpacing",
     "tabSize", "boxSizing", "width"].forEach(function (p) { espelho.style[p] = estilo[p]; });
    espelho.style.position = "absolute";
    espelho.style.visibility = "hidden";
    espelho.style.whiteSpace = "pre-wrap";
    espelho.style.wordWrap = "break-word";
    espelho.textContent = campo.value.slice(0, posicao);
    var marca = document.createElement("span");
    marca.textContent = "\u200b";
    espelho.appendChild(marca);
    document.body.appendChild(espelho);
    var onde = { topo: marca.offsetTop, esquerda: marca.offsetLeft,
      altura: parseFloat(estilo.lineHeight) };
    document.body.removeChild(espelho);
    return onde;
  }

  (function irAoLink() {
    var busca = new URLSearchParams(location.search);
    var linha = parseInt(busca.get("linha"), 10);
    if (isNaN(linha) || linha < 0) { return; }
    var alvo = (busca.get("alvo") || "").trim();
    // sai da URL: recarregar a página não deve pular de novo
    // tirado do texto da URL, e não remontado: URLSearchParams trocaria "/"
    // por %2F e espaço por +, e o endereço ficaria ilegível
    var limpa = location.search.replace(/[?&](linha|alvo)=[^&]*/g, "").replace(/^&/, "?");
    history.replaceState(null, "", location.pathname + limpa + location.hash);

    // prévia: o último bloco que começa nessa linha ou antes; dentro dele, o
    // link quebrado com esse alvo, se houver
    var bloco = null;
    previa.querySelectorAll("[data-fonte]").forEach(function (b) {
      if (parseInt(b.dataset.fonte, 10) <= linha) { bloco = b; }
    });
    var marca = bloco;
    if (bloco && alvo) {
      bloco.querySelectorAll("a.quebrado").forEach(function (a) {
        if (marca === bloco && (a.dataset.alvo || "").toLowerCase() === alvo.toLowerCase()) { marca = a; }
      });
    }
    if (marca && area.dataset.modo !== "editar") {
      marca.scrollIntoView({ block: "center" });
      marca.classList.add("destaque");
    }

    // campo: seleciona o link na linha (ou a linha inteira) e rola até ele
    var linhas = editor.value.split("\n");
    if (!campoVisivel() || linha >= linhas.length) { return; }
    var inicio = 0;
    for (var i = 0; i < linha; i++) { inicio += linhas[i].length + 1; }
    var texto = linhas[linha];
    var achado = alvo ? texto.toLowerCase().indexOf(alvo.toLowerCase()) : -1;
    var de = achado >= 0 ? achado : 0;
    var ate = achado >= 0 ? achado + alvo.length : texto.length;
    editor.focus({ preventScroll: true });
    editor.setSelectionRange(inicio + de, inicio + ate);
    editor.scrollTop = Math.max(0, medirCursor(editor, inicio + de).topo - editor.clientHeight / 2);
    if (realce) { realce.scrollTop = editor.scrollTop; }
    if (!marca || area.dataset.modo === "editar") {
      editor.scrollIntoView({ block: "nearest" });
    }
  })();

  // ---------- chegar pela busca ----------
  // aberta por um resultado (?busca=), a nota marca as palavras buscadas e
  // rola até a primeira. As mesmas palavras que a busca usa: de 3 letras para cima
  (function marcarBusca() {
    var busca = new URLSearchParams(location.search).get("busca") || "";
    var termos = (busca.toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []).filter(function (t) {
      return t.length > 2;
    });
    if (!termos.length) { return; }
    var padrao = new RegExp(termos.map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|"), "gi");
    var nos = [];
    var andar = document.createTreeWalker(previa, NodeFilter.SHOW_TEXT);
    while (andar.nextNode()) { nos.push(andar.currentNode); }
    var primeira = null;
    nos.forEach(function (no) {
      var texto = no.nodeValue;
      padrao.lastIndex = 0;
      if (!padrao.test(texto)) { return; }
      padrao.lastIndex = 0;
      var pedacos = document.createDocumentFragment();
      var fim = 0;
      var m;
      while ((m = padrao.exec(texto))) {
        pedacos.appendChild(document.createTextNode(texto.slice(fim, m.index)));
        var marca = document.createElement("mark");
        marca.className = "achado-busca";
        marca.textContent = m[0];
        pedacos.appendChild(marca);
        primeira = primeira || marca;
        fim = m.index + m[0].length;
      }
      pedacos.appendChild(document.createTextNode(texto.slice(fim)));
      no.parentNode.replaceChild(pedacos, no);
    });
    if (primeira && area.dataset.modo !== "editar") { primeira.scrollIntoView({ block: "center" }); }
  })();

  // ---------- autocompletar [[ e comandos com / ----------
  var notas = notasDoVault;
  // os desenhos entram no [[ também; o nome deles leva a extensão
  // ([[Planta.excalidraw]]), então não disputam nome com nota
  var DESENHO = /\.excalidraw$/i;
  var nomes = {};
  notas.concat(desenhosDoVault).forEach(function (n) {
    var nome = nomeCurto(n);
    nomes[nome.toLowerCase()] = (nomes[nome.toLowerCase()] || 0) + 1;
  });
  var caixa = document.createElement("ul");
  caixa.className = "sugestoes";
  caixa.hidden = true;
  caixa.setAttribute("role", "listbox");
  document.body.appendChild(caixa);
  var achados = [];
  var escolhido = 0;
  var ABERTO = /\[\[([^\[\]\n|#]*)$/;
  // o campo onde se está digitando: o editor, ou o bloco aberto no ao vivo
  var campoSugestao = editor;

  function comoLink(n) {
    var nome = nomeCurto(n);
    // nome repetido em outra pasta: o caminho desfaz a dúvida (desenho
    // mantém o .excalidraw, que é o que diz que o link é de desenho)
    return nomes[nome.toLowerCase()] > 1 ? n.replace(/\.md$/i, "") : nome;
  }

  function fecharSugestoes() { caixa.hidden = true; achados = []; }

  // a lista abre embaixo do cursor, uma linha abaixo dele
  function posicionar() {
    var onde = medirCursor(campoSugestao, campoSugestao.selectionStart);
    var caixaCampo = campoSugestao.getBoundingClientRect();
    var topo = caixaCampo.top + onde.topo - campoSugestao.scrollTop + onde.altura;
    var esquerda = caixaCampo.left + onde.esquerda;
    caixa.style.top = Math.min(topo, window.innerHeight - 40) + window.scrollY + "px";
    caixa.style.left = Math.min(esquerda, window.innerWidth - 300) + window.scrollX + "px";
  }

  // cada sugestão é { nome, onde, escolher }: uma nota para o [[, ou um
  // comando do /
  function desenhar() {
    caixa.textContent = "";
    achados.forEach(function (sugestao, i) {
      var item = document.createElement("li");
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(i === escolhido));
      var nome = document.createElement("span");
      nome.textContent = sugestao.nome;
      var onde = document.createElement("span");
      onde.className = "onde";
      onde.textContent = sugestao.onde;
      item.appendChild(nome);
      item.appendChild(onde);
      item.addEventListener("mousedown", function (e) { e.preventDefault(); sugestao.escolher(); });
      caixa.appendChild(item);
      // a lista rola: o escolhido pelas setas continua à vista
      if (i === escolhido && item.scrollIntoView) { item.scrollIntoView({ block: "nearest" }); }
    });
  }

  function notasPara(busca) {
    return notas.concat(desenhosDoVault).filter(function (n) {
      return n !== caminho && n.toLowerCase().indexOf(busca) >= 0;
    }).sort(function (a, b) {
      var na = a.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      var nb = b.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      return na - nb || a.localeCompare(b);
    }).slice(0, 8).map(function (n) {
      return { nome: nomeCurto(n).replace(DESENHO, ""),
        onde: DESENHO.test(n) ? "desenho · " + n : n,
        escolher: function () { inserir(n); } };
    });
  }

  function sugerir() {
    if (campoSugestao.selectionStart !== campoSugestao.selectionEnd) { fecharSugestoes(); return; }
    var antes = campoSugestao.value.slice(0, campoSugestao.selectionStart);
    var aberto = antes.match(ABERTO);
    var barra = !aberto && antes.match(BARRA);
    if (aberto) {
      achados = notasPara(aberto[1].toLowerCase());
    } else if (barra) {
      achados = comandosPara(barra[2]);
    } else {
      fecharSugestoes();
      return;
    }
    if (!achados.length) { fecharSugestoes(); return; }
    escolhido = 0;
    desenhar();
    posicionar();
    caixa.hidden = false;
  }

  function inserir(n) {
    var fim = campoSugestao.selectionStart;
    var antes = campoSugestao.value.slice(0, fim);
    var aberto = antes.match(ABERTO);
    if (!aberto) { return; }
    var depois = campoSugestao.value.slice(fim);
    var fecha = depois.indexOf("]]") === 0 ? "" : "]]";
    var link = comoLink(n);
    campoSugestao.value = antes.slice(0, antes.length - aberto[1].length) + link + fecha + depois;
    var cursor = fim - aberto[1].length + link.length + 2;
    campoSugestao.setSelectionRange(cursor, cursor);
    fecharSugestoes();
    // o input faz o resto: cores, salvar e, no bloco, remontar a nota
    campoSugestao.dispatchEvent(new Event("input"));
  }

  // ---------- comandos com / ----------
  // "/" no começo da linha ou depois de um espaço abre a lista; o que vem
  // depois filtra ("/tab" → Tabela). § marca onde o cursor fica. `bloco`:
  // precisa começar numa linha só sua; `separar`: e com uma linha vazia antes
  // (sem ela, "---" embaixo de um parágrafo vira título, e a tabela não vale)
  var BARRA = /(^|\s)\/([^\s\/]{0,24})$/;
  var CALLOUT_TIPOS = [
    ["note", "Nota", ""], ["abstract", "Resumo", "summary tldr"], ["info", "Info", ""],
    ["todo", "A fazer", ""], ["tip", "Dica", "hint important"], ["success", "Feito", "check done"],
    ["question", "Pergunta", "help faq"], ["warning", "Atenção", "caution aviso"],
    ["failure", "Falhou", "fail missing"], ["danger", "Perigo", "error erro"],
    ["bug", "Bug", ""], ["example", "Exemplo", ""], ["quote", "Citação", "cite"],
  ];
  var COMANDOS = [
    { nome: "Título 1", onde: "#", texto: "# §", bloco: true, chaves: "heading h1" },
    { nome: "Título 2", onde: "##", texto: "## §", bloco: true, chaves: "heading h2" },
    { nome: "Título 3", onde: "###", texto: "### §", bloco: true, chaves: "heading h3" },
    { nome: "Lista", onde: "-", texto: "- §", bloco: true, chaves: "bullet marcadores" },
    { nome: "Lista numerada", onde: "1.", texto: "1. §", bloco: true, chaves: "ordenada numbered" },
    { nome: "Tarefa", onde: "- [ ]", texto: "- [ ] §", bloco: true, chaves: "todo checkbox caixa" },
    { nome: "Citação", onde: ">", texto: "> §", bloco: true, chaves: "quote" },
    { nome: "Bloco de código", onde: "```", texto: "```\n§\n```", bloco: true, chaves: "code" },
    { nome: "Tabela", onde: "| a | b |", texto: "| Coluna | Coluna |\n| --- | --- |\n| § |  |",
      bloco: true, separar: true, chaves: "table" },
    { nome: "Divisória", onde: "---", texto: "---\n§", bloco: true, separar: true, chaves: "linha hr divider" },
    { nome: "Link para nota", onde: "[[ ]]", texto: "[[§]]", chaves: "wikilink nota" },
    { nome: "Link", onde: "[texto](url)", texto: "[§]()", chaves: "url endereco Ctrl+K" },
    { nome: "Imagem ou anexo", onde: "escolher arquivo", anexo: true, chaves: "arquivo foto pdf audio video" },
    { nome: "Negrito", onde: "**texto** · Ctrl+B", texto: "**§**", chaves: "bold forte" },
    { nome: "Itálico", onde: "*texto* · Ctrl+I", texto: "*§*", chaves: "italic" },
    { nome: "Riscado", onde: "~~texto~~", texto: "~~§~~", chaves: "strike tachado" },
    { nome: "Código no texto", onde: "`texto`", texto: "`§`", chaves: "code inline" },
    { nome: "Data de hoje", onde: "dd/mm/aaaa", data: "dia", chaves: "hoje date dia" },
    { nome: "Data e hora", onde: "dd/mm/aaaa hh:mm", data: "tudo", chaves: "agora now" },
    { nome: "Hora", onde: "hh:mm", data: "hora", chaves: "agora now time" },
  ];
  CALLOUT_TIPOS.forEach(function (t) {
    COMANDOS.push({ nome: "Callout " + t[1], onde: "> [!" + t[0] + "]", texto: "> [!" + t[0] + "] §",
      bloco: true, chaves: "caixa aviso " + t[0] + " " + t[2] });
  });
  COMANDOS.push({ nome: "Callout recolhível", onde: "> [!faq]-", texto: "> [!faq]- §",
    bloco: true, chaves: "caixa dobra fold details question" });

  function comandosPara(busca) {
    var b = semAcento(busca);
    var achou = COMANDOS.filter(function (c) {
      return semAcento(c.nome + " " + c.onde + " " + (c.chaves || "")).indexOf(b) >= 0;
    });
    // quem começa com o que foi digitado vem primeiro; o resto, na ordem da lista
    return achou.filter(function (c) { return semAcento(c.nome).indexOf(b) === 0; }).concat(
      achou.filter(function (c) { return semAcento(c.nome).indexOf(b) !== 0; })
    ).map(function (c) {
      return { nome: c.nome, onde: c.onde, escolher: function () { aplicarComando(c); } };
    });
  }

  function dois(n) { return (n < 10 ? "0" : "") + n; }

  function aplicarComando(c) {
    var campo = campoSugestao;
    var cursor = campo.selectionStart;
    var casado = campo.value.slice(0, cursor).match(BARRA);
    fecharSugestoes();
    if (!casado) { return; }
    var ini = cursor - casado[2].length - 1;
    if (c.anexo) {
      // tira o "/..." e abre o seletor; o link entra onde estava a barra
      trocar(campo, ini, cursor, "", ini);
      escolher.click();
      return;
    }
    var texto = c.texto;
    if (c.data) {
      var d = new Date();
      var dia = dois(d.getDate()) + "/" + dois(d.getMonth() + 1) + "/" + d.getFullYear();
      var hora = dois(d.getHours()) + ":" + dois(d.getMinutes());
      texto = (c.data === "dia" ? dia : c.data === "hora" ? hora : dia + " " + hora) + "§";
    }
    var v = campo.value;
    var linhaAntes = v.slice(v.lastIndexOf("\n", ini - 1) + 1, ini);
    var prefixo = "";
    if (c.bloco && linhaAntes.trim()) {
      prefixo = "\n\n";
    } else if (c.separar && ini > 0) {
      var anterior = v.slice(0, ini - linhaAntes.length).replace(/\n$/, "");
      if (anterior.slice(anterior.lastIndexOf("\n") + 1).trim()) { prefixo = "\n"; }
    }
    texto = prefixo + texto;
    var marca = texto.indexOf("§");
    texto = texto.replace("§", "");
    trocar(campo, ini, cursor, texto, ini + (marca < 0 ? texto.length : marca));
    // de novo, com o cursor já no lugar: o "Link para nota" abre a lista de notas
    sugerir();
  }

  function ligarSugestoes(campo) {
    campo.addEventListener("keydown", function (e) {
      if (caixa.hidden || campoSugestao !== campo) { return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        escolhido = (escolhido + (e.key === "ArrowDown" ? 1 : achados.length - 1)) % achados.length;
        desenhar();
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        achados[escolhido].escolher();
      } else if (e.key === "Escape") {
        fecharSugestoes();
      } else {
        return;
      }
      // a tecla era das sugestões: o bloco não fecha nem troca de bloco
      e.stopImmediatePropagation();
    });
    campo.addEventListener("input", function () { campoSugestao = campo; sugerir(); });
    campo.addEventListener("blur", fecharSugestoes);
    campo.addEventListener("scroll", fecharSugestoes);
  }
  ligarSugestoes(editor);

  ligarAtalhos(editor);

  window.addEventListener("beforeunload", function (e) {
    if (editor.value !== salvo) { e.preventDefault(); e.returnValue = ""; }
  });

  document.getElementById("usar-disco").addEventListener("click", function () {
    editor.value = salvo = deDisco.texto;
    versao = deDisco.versao;
    mostrarPrevia(deDisco.html, deDisco.texto);
    agendarRealce();
    conflito.hidden = true;
    privada.checked = marcadaNoTexto();
    mostrar("salvo", "salvo");
  });

  document.getElementById("usar-meu").addEventListener("click", function () {
    versao = deDisco.versao;
    conflito.hidden = true;
    salvar();
  });

  // apagar pede um segundo clique em vez de uma caixa de diálogo
  // só o rótulo muda, o ícone fica; Esc ou 4 s sem clicar desarmam
  var apagar = document.getElementById("apagar");
  var rotuloApagar = apagar.querySelector(".rotulo");
  var armado = null;
  function desarmar() {
    clearTimeout(armado);
    armado = null;
    rotuloApagar.textContent = "apagar";
    delete apagar.dataset.armado;
  }
  apagar.addEventListener("keydown", function (e) { if (e.key === "Escape") { desarmar(); } });
  apagar.addEventListener("click", function () {
    if (!armado) {
      rotuloApagar.textContent = "confirmar";
      apagar.dataset.armado = "1";
      armado = setTimeout(desarmar, 4000);
      return;
    }
    pedir("DELETE", "/api/notas/arquivo?caminho=" + encodeURIComponent(caminho)).then(function (r) {
      if (r.ok) {
        salvo = editor.value;
        location.href = "/notas";
      } else {
        mostrarErro(r);
      }
    });
  });
})();
