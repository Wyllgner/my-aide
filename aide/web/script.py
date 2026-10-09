"""O único JavaScript da página, servido em /app.js.

Arquivo, e não <script> embutido, porque a CSP só deixa rodar script vindo
daqui (`script-src 'self'`): um <script> que um dia escapasse do escape de
uma tela não roda. Sem framework e sem build, como o resto.

Faz só o que o servidor não consegue: salvar enquanto você digita, avisar do
conflito com quem escreveu por fora, e os botões de criar e apagar.
"""

from __future__ import annotations

JS = r"""
"use strict";
(function () {
  // a marca que seguranca.py exige em toda escrita
  function pedir(metodo, url, corpo) {
    return fetch(url, {
      method: metodo,
      headers: { "Content-Type": "application/json", "X-Aide": "1" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
      credentials: "same-origin",
    });
  }

  function abrir(caminho) {
    location.href = "/notas?arquivo=" + encodeURIComponent(caminho).replace(/%2F/g, "/");
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
    if (pulou.length) {
      partes.push("não consegui atualizar o link em " + pulou.join(", ") + " (arquivo fora de UTF-8 ou sem permissão)");
    }
    try {
      sessionStorage.setItem("aide.notas.aviso", partes.join(" · "));
    } catch (e) { /* sem armazenamento: só não mostra o aviso */ }
  }

  // ---------- criar nota e pasta ----------
  var form = document.getElementById("criar");
  var nome = document.getElementById("criar-nome");
  var erro = document.getElementById("criar-erro");
  var criando = null;

  function pedirNome(tipo) {
    criando = tipo;
    form.hidden = false;
    erro.textContent = "";
    var pasta = form.dataset.pasta;
    nome.placeholder = tipo === "nota" ? "nome da nota" : "nome da pasta";
    nome.setAttribute("aria-label", nome.placeholder);
    nome.value = pasta ? pasta + "/" : "";
    nome.focus();
  }

  if (form) {
    document.getElementById("nova-nota").addEventListener("click", function () { pedirNome("nota"); });
    document.getElementById("nova-pasta").addEventListener("click", function () { pedirNome("pasta"); });
    nome.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { form.hidden = true; erro.textContent = ""; }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var caminho = nome.value.trim().replace(/\/+$/, "");
      if (!caminho) { return; }
      if (criando === "nota" && !/\.md$/i.test(caminho)) { caminho += ".md"; }
      var url = criando === "nota" ? "/api/notas/arquivo" : "/api/notas/pasta";
      pedir("POST", url, { caminho: caminho }).then(function (r) {
        if (r.ok) {
          if (criando === "nota") { abrir(caminho); } else { location.reload(); }
        } else {
          erroDe(r).then(function (m) { erro.textContent = m; });
        }
      });
    });
  }

  // ---------- criar a nota que um link quebrado pede ----------
  document.querySelectorAll(".criar-quebrado").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var caminho = botao.dataset.caminho;
      botao.disabled = true;
      pedir("POST", "/api/notas/arquivo", { caminho: caminho }).then(function (r) {
        if (r.ok || r.status === 409) { abrir(caminho); return; }
        botao.disabled = false;
        erroDe(r).then(function (m) { botao.textContent = m; });
      });
    });
  });

  // ---------- renomear e mover pasta ----------
  document.querySelectorAll(".renomear-pasta").forEach(function (botao) {
    botao.addEventListener("click", function (e) {
      // o botão mora no <summary>: sem isto o clique abre e fecha a pasta
      e.preventDefault();
      e.stopPropagation();
      var de = botao.dataset.pasta;
      var resumo = botao.closest("summary");
      if (resumo.querySelector("form")) { return; }
      var form = document.createElement("form");
      form.className = "renomear-pasta-form";
      var campo = document.createElement("input");
      campo.value = de;
      campo.setAttribute("aria-label", "caminho da pasta");
      campo.spellcheck = false;
      var erro = document.createElement("span");
      erro.className = "erro";
      form.appendChild(campo);
      form.appendChild(erro);
      resumo.hidden = true;
      resumo.parentNode.insertBefore(form, resumo.nextSibling);
      campo.focus();
      campo.setSelectionRange(de.lastIndexOf("/") + 1, de.length);
      function fechar() { form.remove(); resumo.hidden = false; }
      campo.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { fechar(); } });
      campo.addEventListener("click", function (ev) { ev.stopPropagation(); });
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var para = campo.value.trim().replace(/^\/+|\/+$/g, "");
        if (!para || para === de) { fechar(); return; }
        var editorAberto = document.getElementById("editor");
        var antes = editorAberto ? editorAberto.dataset.caminho : null;
        var guardar = window.aideSalvar ? window.aideSalvar() : Promise.resolve();
        guardar.then(function () {
          return pedir("POST", "/api/notas/mover-pasta", { de: de, para: para });
        }).then(function (r) {
          if (!r.ok) { return erroDe(r).then(function (m) { erro.textContent = m; }); }
          return r.json().then(function (d) {
            guardarAviso(d);
            var depois = antes && d.notas_movidas[antes];
            if (depois) { abrir(depois); } else { location.reload(); }
          });
        }).catch(function (e3) { erro.textContent = e3.message; });
      });
    });
  });

  // ---------- grafo: arrastar, zoom e vizinhas ----------
  document.querySelectorAll("svg.grafo").forEach(function (svg) {
    var vb = svg.viewBox.baseVal;
    var original = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
    var arrasto = null;
    var moveu = false;

    function paraSvg(evento) {
      var caixa = svg.getBoundingClientRect();
      return { x: vb.x + (evento.clientX - caixa.left) / caixa.width * vb.width,
               y: vb.y + (evento.clientY - caixa.top) / caixa.height * vb.height };
    }

    // o grafo local fica no meio da página: a roda sozinha rola a página,
    // e o zoom pede Ctrl — senão quem rola passando por cima fica preso nele
    var local = svg.classList.contains("local");
    svg.addEventListener("wheel", function (e) {
      if (local && !e.ctrlKey && !e.metaKey) { return; }
      e.preventDefault();
      var ponto = paraSvg(e);
      var fator = e.deltaY < 0 ? 0.85 : 1 / 0.85;
      var largura = Math.min(Math.max(vb.width * fator, original.w / 8), original.w * 3);
      var escala = largura / vb.width;
      vb.x = ponto.x - (ponto.x - vb.x) * escala;
      vb.y = ponto.y - (ponto.y - vb.y) * escala;
      vb.width = largura;
      vb.height = vb.height * escala;
    }, { passive: false });

    svg.addEventListener("pointerdown", function (e) {
      arrasto = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y };
      moveu = false;
    });
    window.addEventListener("pointermove", function (e) {
      if (!arrasto) { return; }
      var caixa = svg.getBoundingClientRect();
      var dx = (e.clientX - arrasto.x) / caixa.width * vb.width;
      var dy = (e.clientY - arrasto.y) / caixa.height * vb.height;
      if (Math.abs(e.clientX - arrasto.x) + Math.abs(e.clientY - arrasto.y) > 4) { moveu = true; }
      vb.x = arrasto.vx - dx;
      vb.y = arrasto.vy - dy;
    });
    window.addEventListener("pointerup", function () { arrasto = null; });
    // arrastar por cima de uma nota não pode abri-la ao soltar
    svg.addEventListener("click", function (e) {
      if (moveu) { e.preventDefault(); moveu = false; }
    }, true);
    svg.addEventListener("dblclick", function () {
      vb.x = original.x; vb.y = original.y; vb.width = original.w; vb.height = original.h;
    });

    svg.querySelectorAll("a.no").forEach(function (no) {
      function destacar() {
        var perto = (no.dataset.vizinhos || "").split(" ");
        perto.push(no.dataset.id);
        svg.classList.add("focado");
        svg.querySelectorAll("a.no").forEach(function (outro) {
          outro.classList.toggle("perto", perto.indexOf(outro.dataset.id) >= 0);
        });
        svg.querySelectorAll("line").forEach(function (l) {
          l.classList.toggle("perto", l.dataset.a === no.dataset.id || l.dataset.b === no.dataset.id);
        });
      }
      function apagar() { svg.classList.remove("focado"); }
      // mouse e teclado: quem navega com Tab vê as mesmas vizinhas
      no.addEventListener("mouseenter", destacar);
      no.addEventListener("focus", destacar);
      no.addEventListener("mouseleave", apagar);
      no.addEventListener("blur", apagar);
    });
  });

  // ---------- apagar pasta: dois cliques, como a nota ----------
  document.querySelectorAll(".apagar-pasta").forEach(function (botao) {
    var armado = null;
    botao.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (!armado) {
        botao.dataset.armado = "1";
        botao.querySelector(".rotulo").textContent = "apagar?";
        armado = setTimeout(function () {
          armado = null;
          delete botao.dataset.armado;
          botao.querySelector(".rotulo").textContent = "";
        }, 4000);
        return;
      }
      var pasta = botao.dataset.pasta;
      var editorAberto = document.getElementById("editor");
      var aberta = editorAberto ? editorAberto.dataset.caminho : "";
      var guardar = window.aideSalvar ? window.aideSalvar() : Promise.resolve();
      guardar.then(function () {
        return pedir("DELETE", "/api/notas/pasta?caminho=" + encodeURIComponent(pasta));
      }).then(function (r) {
        if (!r.ok) { return erroDe(r).then(function (m) { botao.textContent = m; }); }
        // a nota aberta ia junto: volta para a lista
        location.href = aberta.indexOf(pasta + "/") === 0 ? "/notas" : location.href;
      }).catch(function (e2) { botao.textContent = e2.message; });
    });
  });

  // ---------- editor ----------
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
        return erroDe(r).then(function (m) { mostrar(m, "erro"); });
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

  // ---------- cores no editor ----------
  // a cópia colorida por trás do campo transparente; acima disto, pesa
  var realce = document.getElementById("realce");
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
    var campo = document.createElement("textarea");
    campo.className = "bloco-vivo";
    campo.value = fonte;
    campo.spellcheck = editor.spellcheck;
    campo.setAttribute("aria-label", "markdown do bloco");
    b.campo = campo;
    bloco = b;
    if (el) {
      el.replaceWith(campo);
    } else {
      previa.insertBefore(campo, depoisDele);
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
      // o bloco do fim, apagado de volta: a nota fica como estava
      editor.value = !b.el && !campo.value ? b.original : b.cabeca + campo.value + b.cauda;
      ajustarAltura(campo);
      privada.checked = marcadaNoTexto();
      corretor();
      campo.spellcheck = editor.spellcheck;
      agendarRealce();
      agendar();
    });
    campo.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { ev.preventDefault(); campo.blur(); return; }
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
      if (b.el) { b.campo.replaceWith(b.el); } else { b.campo.remove(); }
    } else {
      // até a prévia nova chegar, o texto cru do bloco fica no lugar dele
      var pendente = document.createElement("div");
      pendente.className = "bloco-pendente";
      pendente.textContent = b.campo.value;
      b.campo.replaceWith(pendente);
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
    }
    if (guardada && guardada.texto === editor.value) {
      mostrarPrevia(guardada.html, guardada.texto);
      revelarAnexos();
    } else if (editor.value !== b.original) {
      salvar();
    }
  }

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
    // seleciona só o nome, como o Obsidian: o caso comum é renomear
    var barra = campoCaminho.value.lastIndexOf("/");
    campoCaminho.setSelectionRange(barra + 1, campoCaminho.value.length);
  }

  function fecharRenomear() {
    renomear.hidden = true;
    titulo.hidden = false;
    campoCaminho.value = caminho.replace(/\.md$/i, "");
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
    var pasta = caminho.lastIndexOf("/") >= 0 ? caminho.slice(0, caminho.lastIndexOf("/")) : "";
    var novo = (alvo.indexOf("/") >= 0 || !pasta ? alvo : pasta + "/" + alvo);
    if (!/\.md$/i.test(novo)) { novo += ".md"; }
    garantirSalvo().then(function () {
      return pedir("POST", "/api/notas/arquivo", { caminho: novo });
    }).then(function (r) {
      if (r.ok || r.status === 409) { abrir(novo); } else { erroDe(r).then(function (m) { mostrar(m, "erro"); }); }
    }).catch(function (e) { mostrar(e.message, "erro"); });
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
    editor.value = linhas.join("\n");
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
      mostrar(e.message, "erro");
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
  function alturaAte(posicao) {
    // o mesmo espelho do autocompletar: a linha pode quebrar em várias
    var espelho = document.createElement("div");
    var estilo = getComputedStyle(editor);
    ["fontFamily", "fontSize", "lineHeight", "padding", "border", "letterSpacing",
     "tabSize", "boxSizing", "width"].forEach(function (p) { espelho.style[p] = estilo[p]; });
    espelho.style.position = "absolute";
    espelho.style.visibility = "hidden";
    espelho.style.whiteSpace = "pre-wrap";
    espelho.style.wordWrap = "break-word";
    espelho.textContent = editor.value.slice(0, posicao);
    var marca = document.createElement("span");
    marca.textContent = "\u200b";
    espelho.appendChild(marca);
    document.body.appendChild(espelho);
    var topo = marca.offsetTop;
    document.body.removeChild(espelho);
    return topo;
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
    editor.scrollTop = Math.max(0, alturaAte(inicio + de) - editor.clientHeight / 2);
    if (realce) { realce.scrollTop = editor.scrollTop; }
    if (!marca || area.dataset.modo === "editar") {
      editor.scrollIntoView({ block: "nearest" });
    }
  })();

  // ---------- autocompletar [[ e comandos com / ----------
  var notas = [];
  try { notas = JSON.parse(editor.dataset.notas || "[]"); } catch (e) { notas = []; }
  var nomes = {};
  notas.forEach(function (n) {
    var nome = n.replace(/^.*\//, "").replace(/\.md$/i, "");
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
    var nome = n.replace(/^.*\//, "").replace(/\.md$/i, "");
    // nome repetido em outra pasta: o caminho desfaz a dúvida
    return nomes[nome.toLowerCase()] > 1 ? n.replace(/\.md$/i, "") : nome;
  }

  function fecharSugestoes() { caixa.hidden = true; achados = []; }

  function posicionar() {
    // um espelho do campo, com o mesmo estilo, mede onde está o cursor
    var espelho = document.createElement("div");
    var estilo = getComputedStyle(campoSugestao);
    ["fontFamily", "fontSize", "lineHeight", "padding", "border", "letterSpacing",
     "tabSize", "boxSizing", "width"].forEach(function (p) { espelho.style[p] = estilo[p]; });
    espelho.style.position = "absolute";
    espelho.style.visibility = "hidden";
    espelho.style.whiteSpace = "pre-wrap";
    espelho.style.wordWrap = "break-word";
    espelho.textContent = campoSugestao.value.slice(0, campoSugestao.selectionStart);
    var marca = document.createElement("span");
    marca.textContent = "\u200b";
    espelho.appendChild(marca);
    document.body.appendChild(espelho);
    var caixaCampo = campoSugestao.getBoundingClientRect();
    var topo = caixaCampo.top + marca.offsetTop - campoSugestao.scrollTop + parseFloat(estilo.lineHeight);
    var esquerda = caixaCampo.left + marca.offsetLeft;
    document.body.removeChild(espelho);
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
    return notas.filter(function (n) {
      return n !== caminho && n.toLowerCase().indexOf(busca) >= 0;
    }).sort(function (a, b) {
      var na = a.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      var nb = b.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      return na - nb || a.localeCompare(b);
    }).slice(0, 8).map(function (n) {
      return { nome: n.replace(/^.*\//, "").replace(/\.md$/i, ""), onde: n,
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

  function semAcento(t) {
    return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

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
        erroDe(r).then(function (m) { mostrar(m, "erro"); });
      }
    });
  });
})();
"""
