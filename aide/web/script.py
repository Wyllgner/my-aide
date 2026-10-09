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
    salvar();
  });

  editor.addEventListener("input", function () {
    privada.checked = marcadaNoTexto();
    corretor();
    agendar();
  });

  // ---------- modos: editar, lado a lado, ler ----------
  var MODOS = ["editar", "dividido", "ler"];

  function aplicarModo(modo) {
    if (MODOS.indexOf(modo) < 0) { return; }
    area.dataset.modo = modo;
    document.querySelectorAll(".modo").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.modo === modo));
    });
    try { localStorage.setItem("aide.notas.modo", modo); } catch (e) { /* sem armazenamento: vale só agora */ }
  }

  try { aplicarModo(localStorage.getItem("aide.notas.modo")); } catch (e) { /* idem */ }
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
    salvar().then(function () {
      return pedir("POST", "/api/notas/arquivo", { caminho: novo });
    }).then(function (r) {
      if (r.ok || r.status === 409) { abrir(novo); } else { erroDe(r).then(function (m) { mostrar(m, "erro"); }); }
    });
  }
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
