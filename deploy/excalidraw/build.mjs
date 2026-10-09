// Compila o Excalidraw para aide/web/vendor/excalidraw.
//
// Roda só ao trocar de versão (./build.sh); a saída vai para o git e o
// servidor nunca precisa de Node. Duas coisas ficam de fora para o pacote
// não passar de 8 MB para menos de 3:
// - o mermaid (o "colar diagrama mermaid" vira texto comum);
// - os idiomas que não são pt-BR nem inglês.
// E duas trocas no código (TROCAS): a reserva das fontes, que no pacote é o
// esm.sh, passa a ser a nossa pasta, e sai a config do Firebase do
// excalidraw.com.
import { readFile } from "node:fs/promises";
import { build } from "esbuild";

const IDIOMAS = /\/locales\/(pt-BR|en)-[A-Z0-9]+\.js$/;

const PASTA = "/vendor/excalidraw/";

// Trocas no código do pacote. Cada uma tem uma marca que diz se o arquivo é o
// dela; marca presente e padrão ausente quer dizer que a versão nova mudou o
// trecho, e o build para em vez de deixar passar calado.
const TROCAS = [
  {
    // a reserva das fontes; absoluta, porque o pacote monta new URL(fonte, reserva)
    marca: "ASSETS_FALLBACK_URL\",",
    padrao: /`https:\/\/esm\.sh\/.*?\/dist\/prod\/`/,
    por: `new URL(${JSON.stringify(PASTA)}, self.location.origin).href`,
  },
  {
    // a config do Firebase da colaboração do excalidraw.com, embutida no
    // pacote. Pública e de outro projeto, mas é uma chave AIza… no nosso git,
    // e o scanner de segredos do GitHub acusa; a colaboração não existe aqui
    marca: "VITE_APP_FIREBASE_CONFIG:",
    padrao: /VITE_APP_FIREBASE_CONFIG:'\{[^']*\}'/,
    por: "VITE_APP_FIREBASE_CONFIG:'{}'",
  },
];

const trocas = {
  name: "trocas",
  setup(b) {
    b.onLoad({ filter: /@excalidraw\/excalidraw\/dist\/prod\/.*\.js$/ }, async (args) => {
      let texto = await readFile(args.path, "utf8");
      let mudou = false;
      for (const { marca, padrao, por } of TROCAS) {
        if (!texto.includes(marca)) continue;
        if (!padrao.test(texto)) throw new Error(`trecho mudou de forma: ${marca}`);
        texto = texto.replace(padrao, por);
        mudou = true;
      }
      return mudou ? { contents: texto, loader: "js" } : undefined;
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
  plugins: [deFora, trocas],
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
