import { pedir, erroDe, abrir, hrefDoDesenho, guardarAviso, salvarAberta } from "/js/notas/comum.js";

// ---------- criar a nota que um link quebrado pede ----------
document.querySelectorAll(".criar-quebrado").forEach(function (botao) {
  botao.addEventListener("click", function () {
    var caminho = botao.dataset.caminho;
    var desenho = botao.dataset.tipo === "desenho";
    botao.disabled = true;
    pedir("POST", desenho ? "/api/desenhos/arquivo" : "/api/notas/arquivo",
          { caminho: caminho }).then(function (r) {
      if (r.ok || r.status === 409) {
        if (desenho) {
          location.href = hrefDoDesenho(caminho, botao.dataset.de);
        } else {
          abrir(caminho);
        }
        return;
      }
      botao.disabled = false;
      erroDe(r).then(function (m) { botao.textContent = m; });
    });
  });
});

// ---------- ligar um link quebrado a uma nota que existe ----------
// o nome digitado errado: troca o link nas notas que citam e recarrega a
// lista. A nota aberta é salva antes — ela pode ser uma das que mudam
document.querySelectorAll(".ligar-quebrado").forEach(function (botao) {
  botao.addEventListener("click", function () {
    botao.disabled = true;
    var guardar = salvarAberta();
    guardar.then(function () {
      return pedir("POST", "/api/notas/ligar", { alvo: botao.dataset.alvo, para: botao.dataset.para });
    }).then(function (r) {
      if (!r.ok) { return erroDe(r).then(function (m) { throw new Error(m); }); }
      return r.json().then(function (d) {
        guardarAviso(d);
        location.reload();
      });
    }).catch(function (e) {
      botao.disabled = false;
      botao.title = e.message;
      botao.classList.add("erro");
    });
  });
});
