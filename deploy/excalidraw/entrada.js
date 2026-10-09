// O que a tela de desenho usa, num só módulo: React junto, para a página
// não depender de import map (que seria script embutido, barrado pela CSP).
export { createElement } from "react";
export { createRoot } from "react-dom/client";
export {
  Excalidraw,
  exportToBlob,
  restore,
  serializeAsJSON,
} from "@excalidraw/excalidraw";
