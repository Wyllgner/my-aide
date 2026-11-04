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

// Os gastos fixos: cadastrar, mudar valor e dia, encerrar.
const ROTA_FIXOS = "/api/gastos/recorrentes";

function escrever(metodo, rota, corpo, erro) {
  const pedido = {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Aide": "1" },
    credentials: "same-origin",
  };
  if (corpo) pedido.body = JSON.stringify(corpo);
  const mostrar = (texto) => {
    erro.textContent = texto;
    erro.hidden = false;
  };
  fetch(rota, pedido)
    .then((resposta) => {
      if (resposta.ok) return location.reload();
      return resposta.json().then(
        (d) => mostrar(typeof d.detail === "string" ? d.detail : "erro " + resposta.status),
        () => mostrar("erro " + resposta.status));
    })
    .catch(() => mostrar("o servidor não respondeu"));
}

const erroFixos = document.getElementById("fixos-erro");
const novoFixo = document.getElementById("fixo-novo");

if (novoFixo) {
  novoFixo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    escrever("POST", ROTA_FIXOS, {
      descricao: novoFixo.descricao.value,
      valor: novoFixo.valor.value,
      dia: novoFixo.dia.value,
      categoria: novoFixo.categoria.value,
      forma: novoFixo.forma.value,
    }, erroFixos);
  });
}

document.querySelectorAll(".fixo-linha").forEach((linha) => {
  const rota = ROTA_FIXOS + "/" + linha.dataset.id;
  linha.addEventListener("submit", (evento) => {
    evento.preventDefault();
    escrever("PUT", rota, { valor: linha.valor.value, dia: linha.dia.value }, erroFixos);
  });
  // dois cliques, sem caixa de dialogo: encerrar tira os meses marcados
  const encerrar = linha.querySelector("[data-encerrar]");
  encerrar.addEventListener("click", () => {
    if (encerrar.dataset.certeza) return escrever("DELETE", rota, null, erroFixos);
    encerrar.dataset.certeza = "1";
    encerrar.querySelector(".rotulo").textContent = "clique de novo";
  });
});
