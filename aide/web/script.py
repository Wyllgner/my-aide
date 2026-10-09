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
    nome.value = pasta ? pasta + "/" : "";
    nome.focus();
  }

  if (form) {
    document.getElementById("nova-nota").addEventListener("click", function () { pedirNome("nota"); });
    document.getElementById("nova-pasta").addEventListener("click", function () { pedirNome("pasta"); });
    nome.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { form.hidden = true; }
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
        botao.textContent = "apagar?";
        armado = setTimeout(function () {
          armado = null;
          delete botao.dataset.armado;
          botao.textContent = "×";
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

  // o HTML vem do renderizador do servidor, que é quem decide o que é seguro
  function mostrarPrevia(html) {
    if (typeof html === "string") { previa.innerHTML = html; }
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
            mostrarPrevia(d.html);
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

  // ---------- modos: editar, lado a lado, ler ----------
  var MODOS = ["editar", "dividido", "ler"];

  function aplicarModo(modo) {
    if (MODOS.indexOf(modo) < 0) { return; }
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
    // Ctrl+E alterna entre escrever e ler, como no Obsidian
    if ((e.ctrlKey || e.metaKey) && e.key === "e") {
      e.preventDefault();
      aplicarModo(area.dataset.modo === "ler" ? "editar" : "ler");
      if (area.dataset.modo !== "ler") { editor.focus(); }
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

  // ---------- autocompletar [[ ----------
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

  function comoLink(n) {
    var nome = n.replace(/^.*\//, "").replace(/\.md$/i, "");
    // nome repetido em outra pasta: o caminho desfaz a dúvida
    return nomes[nome.toLowerCase()] > 1 ? n.replace(/\.md$/i, "") : nome;
  }

  function fecharSugestoes() { caixa.hidden = true; achados = []; }

  function posicionar() {
    // um espelho do campo, com o mesmo estilo, mede onde está o cursor
    var espelho = document.createElement("div");
    var estilo = getComputedStyle(editor);
    ["fontFamily", "fontSize", "lineHeight", "padding", "border", "letterSpacing",
     "tabSize", "boxSizing", "width"].forEach(function (p) { espelho.style[p] = estilo[p]; });
    espelho.style.position = "absolute";
    espelho.style.visibility = "hidden";
    espelho.style.whiteSpace = "pre-wrap";
    espelho.style.wordWrap = "break-word";
    espelho.textContent = editor.value.slice(0, editor.selectionStart);
    var marca = document.createElement("span");
    marca.textContent = "\u200b";
    espelho.appendChild(marca);
    document.body.appendChild(espelho);
    var caixaCampo = editor.getBoundingClientRect();
    var topo = caixaCampo.top + marca.offsetTop - editor.scrollTop + parseFloat(estilo.lineHeight);
    var esquerda = caixaCampo.left + marca.offsetLeft;
    document.body.removeChild(espelho);
    caixa.style.top = Math.min(topo, window.innerHeight - 40) + window.scrollY + "px";
    caixa.style.left = Math.min(esquerda, window.innerWidth - 300) + window.scrollX + "px";
  }

  function desenhar() {
    caixa.textContent = "";
    achados.forEach(function (n, i) {
      var item = document.createElement("li");
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(i === escolhido));
      var nome = document.createElement("span");
      nome.textContent = n.replace(/^.*\//, "").replace(/\.md$/i, "");
      var onde = document.createElement("span");
      onde.className = "onde";
      onde.textContent = n;
      item.appendChild(nome);
      item.appendChild(onde);
      item.addEventListener("mousedown", function (e) { e.preventDefault(); inserir(n); });
      caixa.appendChild(item);
    });
  }

  function sugerir() {
    var antes = editor.value.slice(0, editor.selectionStart);
    var aberto = antes.match(ABERTO);
    if (!aberto || editor.selectionStart !== editor.selectionEnd) { fecharSugestoes(); return; }
    var busca = aberto[1].toLowerCase();
    achados = notas.filter(function (n) {
      return n !== caminho && n.toLowerCase().indexOf(busca) >= 0;
    }).sort(function (a, b) {
      var na = a.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      var nb = b.replace(/^.*\//, "").toLowerCase().indexOf(busca) === 0 ? 0 : 1;
      return na - nb || a.localeCompare(b);
    }).slice(0, 8);
    if (!achados.length) { fecharSugestoes(); return; }
    escolhido = 0;
    desenhar();
    posicionar();
    caixa.hidden = false;
  }

  function inserir(n) {
    var fim = editor.selectionStart;
    var antes = editor.value.slice(0, fim);
    var aberto = antes.match(ABERTO);
    if (!aberto) { return; }
    var depois = editor.value.slice(fim);
    var fecha = depois.indexOf("]]") === 0 ? "" : "]]";
    var link = comoLink(n);
    editor.value = antes.slice(0, antes.length - aberto[1].length) + link + fecha + depois;
    var cursor = fim - aberto[1].length + link.length + 2;
    editor.setSelectionRange(cursor, cursor);
    fecharSugestoes();
    agendarRealce();
    agendar();
  }

  editor.addEventListener("keydown", function (e) {
    if (caixa.hidden) { return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      escolhido = (escolhido + (e.key === "ArrowDown" ? 1 : achados.length - 1)) % achados.length;
      desenhar();
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      inserir(achados[escolhido]);
    } else if (e.key === "Escape") {
      fecharSugestoes();
    }
  });
  editor.addEventListener("input", sugerir);
  editor.addEventListener("blur", fecharSugestoes);
  editor.addEventListener("scroll", fecharSugestoes);

  window.addEventListener("beforeunload", function (e) {
    if (editor.value !== salvo) { e.preventDefault(); e.returnValue = ""; }
  });

  document.getElementById("usar-disco").addEventListener("click", function () {
    editor.value = salvo = deDisco.texto;
    versao = deDisco.versao;
    mostrarPrevia(deDisco.html);
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
  var apagar = document.getElementById("apagar");
  var armado = null;
  apagar.addEventListener("click", function () {
    if (!armado) {
      apagar.textContent = "clique de novo para apagar";
      apagar.dataset.armado = "1";
      armado = setTimeout(function () {
        armado = null;
        apagar.textContent = "apagar";
        delete apagar.dataset.armado;
      }, 4000);
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
