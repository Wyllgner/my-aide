"""O JavaScript da tela de desenho, servido em /desenho.js.

Módulo à parte do /app.js porque importa o Excalidraw (`/vendor/excalidraw/`),
e só esta tela precisa dele: as notas não carregam 3 MB que não usam. Arquivo,
e não <script> embutido, pela mesma CSP (`script-src 'self'`).
"""

from __future__ import annotations

JS = r"""
import { createElement, createRoot, Excalidraw } from "/vendor/excalidraw/excalidraw.js";

const raiz = document.getElementById("desenho");
const estado = document.getElementById("desenho-estado");
const caminho = raiz.dataset.caminho;

function avisar(texto, erro) {
  estado.textContent = texto;
  estado.classList.toggle("erro", !!erro);
}

async function abrir() {
  let resposta;
  try {
    resposta = await fetch("/api/desenhos/arquivo?caminho=" + encodeURIComponent(caminho));
  } catch (e) {
    avisar("sem conexão com o my-aide", true);
    return;
  }
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    avisar(dados.detail || "não consegui abrir o desenho", true);
    return;
  }
  const cena = JSON.parse(dados.texto);
  createRoot(raiz).render(createElement(Excalidraw, {
    langCode: "pt-BR",
    initialData: {
      elements: cena.elements || [],
      appState: cena.appState || {},
      files: cena.files || {},
      scrollToContent: true,
    },
    UIOptions: {
      canvasActions: {
        // o Ctrl+S do Excalidraw abriria "salvar como" no disco; quem salva é o my-aide
        saveToActiveFile: false,
        // a página não tem tema escuro, e o tema iria para dentro do arquivo
        toggleTheme: false,
      },
    },
  }));
  avisar("aberto");
}

abrir();
"""
