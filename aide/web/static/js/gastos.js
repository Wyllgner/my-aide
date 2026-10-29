// O teto do mes pela tela de gastos. Arquivo, e nao <script> embutido, pela
// CSP (script-src 'self').
//
// O mes vem do formulario (data-mes), que e o mes que a tela mostra: mudar o
// teto aqui vale dele em diante, e os meses de antes ficam como estao.
const formulario = document.getElementById("teto-form");

if (formulario) {
  const erro = formulario.querySelector(".teto-erro");

  function mostrarErro(texto) {
    erro.textContent = texto;
    erro.hidden = false;
  }

  // a marca que seguranca.py exige em toda escrita
  function enviar(remover) {
    const corpo = { categoria: formulario.categoria.value, mes: formulario.dataset.mes, remover };
    if (!remover) corpo.valor = formulario.valor.value;
    fetch("/api/gastos/teto", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Aide": "1" },
      body: JSON.stringify(corpo),
      credentials: "same-origin",
    })
      .then((resposta) => {
        if (resposta.ok) return location.reload();
        return resposta.json().then(
          (d) => mostrarErro(d.detail || "erro " + resposta.status),
          () => mostrarErro("erro " + resposta.status));
      })
      .catch(() => mostrarErro("o servidor não respondeu"));
  }

  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    enviar(false);
  });

  formulario.querySelector("[data-remover]").addEventListener("click", () => {
    if (formulario.categoria.reportValidity()) enviar(true);
  });
}
