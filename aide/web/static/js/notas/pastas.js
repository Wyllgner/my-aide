import {
  pedir, erroDe, abrir, pastaDe, guardarAviso, salvarAberta, notaAberta,
} from "/js/notas/comum.js";

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
    // só o nome; com "/" no meio, vale como caminho desde a raiz do vault
    var mae = pastaDe(de) ? pastaDe(de) + "/" : "";
    campo.value = de.slice(mae.length);
    campo.setAttribute("aria-label", "nome da pasta");
    campo.spellcheck = false;
    var erro = document.createElement("span");
    erro.className = "erro";
    form.appendChild(campo);
    form.appendChild(erro);
    resumo.hidden = true;
    resumo.parentNode.insertBefore(form, resumo.nextSibling);
    campo.focus();
    campo.select();
    function fechar() { form.remove(); resumo.hidden = false; }
    campo.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { fechar(); } });
    campo.addEventListener("click", function (ev) { ev.stopPropagation(); });
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var para = campo.value.trim().replace(/^\/+|\/+$/g, "");
      if (para && para.indexOf("/") < 0) { para = mae + para; }
      if (!para || para === de) { fechar(); return; }
      var antes = notaAberta();
      var guardar = salvarAberta();
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
    var aberta = notaAberta();
    var guardar = salvarAberta();
    guardar.then(function () {
      return pedir("DELETE", "/api/notas/pasta?caminho=" + encodeURIComponent(pasta));
    }).then(function (r) {
      if (!r.ok) { return erroDe(r).then(function (m) { botao.textContent = m; }); }
      // a nota aberta ia junto: volta para a lista
      location.href = aberta.indexOf(pasta + "/") === 0 ? "/notas" : location.href;
    }).catch(function (e2) { botao.textContent = e2.message; });
  });
});
