// Compila o Excalidraw para aide/web/vendor/excalidraw.
//
// Roda só ao trocar de versão (./build.sh); a saída vai para o git e o
// servidor nunca precisa de Node. Duas coisas ficam de fora para o pacote
// não passar de 8 MB para menos de 3:
// - o mermaid (o "colar diagrama mermaid" vira texto comum);
// - os idiomas que não são pt-BR nem inglês.
// E a reserva das fontes, que no pacote é o esm.sh, passa a ser a nossa
// pasta: a página nunca tenta buscar nada fora, nem barrada pela CSP.
import { readFile } from "node:fs/promises";
import { build } from "esbuild";

const IDIOMAS = /\/locales\/(pt-BR|en)-[A-Z0-9]+\.js$/;

const RESERVA = /`https:\/\/esm\.sh\/.*?\/dist\/prod\/`/;
const PASTA = "/vendor/excalidraw/";

const fontesDaqui = {
  name: "fontes-daqui",
  setup(b) {
    b.onLoad({ filter: /@excalidraw\/excalidraw\/dist\/prod\/.*\.js$/ }, async (args) => {
      const texto = await readFile(args.path, "utf8");
      if (!texto.includes("ASSETS_FALLBACK_URL\",")) return undefined;
      if (!RESERVA.test(texto)) throw new Error("a reserva das fontes mudou de forma");
      // absoluta: o pacote monta new URL(fonte, reserva)
      const daqui = `new URL(${JSON.stringify(PASTA)}, self.location.origin).href`;
      return { contents: texto.replace(RESERVA, daqui), loader: "js" };
    });
  },
};

const deFora = {
  name: "de-fora",
  setup(b) {
    b.onResolve({ filter: /^@excalidraw\/mermaid-to-excalidraw$/ }, () => ({
      path: "mermaid", namespace: "de-fora",
    }));
    b.onResolve({ filter: /^\.\/locales\// }, (args) => {
      const caminho = args.resolveDir + "/" + args.path.slice(2);
      return IDIOMAS.test(caminho) ? undefined : { path: "vazio", namespace: "idioma" };
    });
    b.onLoad({ filter: /.*/, namespace: "de-fora" }, () => ({
      contents: "export async function parseMermaidToExcalidraw() {"
        + " throw new Error('mermaid fora do pacote'); }",
    }));
    // idioma ausente cai no inglês, que o Excalidraw já usa de reserva
    b.onLoad({ filter: /.*/, namespace: "idioma" }, () => ({ contents: "export default {};" }));
  },
};

const resultado = await build({
  entryPoints: ["entrada.js"],
  bundle: true,
  format: "esm",
  splitting: true,
  minify: true,
  legalComments: "none",
  define: { "process.env.NODE_ENV": '"production"' },
  entryNames: "excalidraw",
  chunkNames: "partes/[name]-[hash]",
  outdir: process.argv[2],
  plugins: [deFora, fontesDaqui],
  logLevel: "warning",
  metafile: true,
});

// os pacotes que de fato entraram, para o build.sh juntar as licenças
const pacotes = new Set();
for (const entrada of Object.keys(resultado.metafile.inputs)) {
  const achado = entrada.match(/node_modules\/((?:@[^/]+\/)?[^/]+)/);
  if (achado) pacotes.add(achado[1]);
}
console.log([...pacotes].sort().join("\n"));
