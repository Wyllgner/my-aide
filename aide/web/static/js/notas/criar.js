import { pedir, erroDe, abrir, hrefDoDesenho } from "/js/notas/comum.js";

// ---------- criar nota e pasta ----------
var form = document.getElementById("criar");
var nome = document.getElementById("criar-nome");
var erro = document.getElementById("criar-erro");
var criando = null;

// `naPasta`: o "+" de uma pasta da árvore; sem ele, a pasta da nota aberta
function pedirNome(tipo, naPasta) {
  criando = tipo;
  form.hidden = false;
  erro.textContent = "";
  var pasta = naPasta !== undefined ? naPasta : form.dataset.pasta;
  nome.placeholder = { nota: "nome da nota", desenho: "nome do desenho" }[tipo] || "nome da pasta";
  nome.setAttribute("aria-label", nome.placeholder);
  nome.value = pasta ? pasta + "/" : "";
  nome.focus();
}

if (form) {
  document.getElementById("nova-nota").addEventListener("click", function () { pedirNome("nota"); });
  document.getElementById("nova-pasta").addEventListener("click", function () { pedirNome("pasta"); });
  document.getElementById("novo-desenho").addEventListener("click", function () { pedirNome("desenho"); });
  [[".nova-na-pasta", "nota"], [".novo-desenho-na-pasta", "desenho"]].forEach(function (par) {
    document.querySelectorAll(par[0]).forEach(function (botao) {
      botao.addEventListener("click", function (e) {
        // o clique é do botão, não da pasta: ela não abre nem fecha
        e.preventDefault();
        e.stopPropagation();
        pedirNome(par[1], botao.dataset.pasta);
        form.scrollIntoView({ block: "nearest" });
      });
    });
  });
  nome.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { form.hidden = true; erro.textContent = ""; }
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var caminho = nome.value.trim().replace(/\/+$/, "");
    if (!caminho) { return; }
    if (criando === "nota" && !/\.md$/i.test(caminho)) { caminho += ".md"; }
    if (criando === "desenho" && !/\.excalidraw$/i.test(caminho)) { caminho += ".excalidraw"; }
    var url = { nota: "/api/notas/arquivo", desenho: "/api/desenhos/arquivo" }[criando]
      || "/api/notas/pasta";
    pedir("POST", url, { caminho: caminho }).then(function (r) {
      if (r.ok) {
        if (criando === "nota") {
          abrir(caminho);
        } else if (criando === "desenho") {
          location.href = hrefDoDesenho(caminho,
            new URLSearchParams(location.search).get("arquivo"));
        } else {
          location.reload();
        }
      } else {
        erroDe(r).then(function (m) { erro.textContent = m; });
      }
    });
  });
}

// a pasta onde a nota nova nasce, para quem precisa dela de fora (o abrir
// rapido oferece criar na pasta da nota aberta)
export function pastaPadrao() {
  return form ? form.dataset.pasta : "";
}
