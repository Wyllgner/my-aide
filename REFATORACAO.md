# my-aide — Refatoração em blocos

Aberta em 14/10/2026. Levantamento deste arquivo: 27/10/2026, com o histórico
em `#156` já no `main`.

A regra da etapa: **cada passo é um PR próprio** (branch, PR, merge, sem
esperar) e **cada PR responde às 10 perguntas** abaixo. A ordem dentro de um
bloco é sempre a mesma: **mover primeiro sem mudar nada**, provando que a
resposta HTTP é byte a byte a mesma (`sha256`), e **limpar depois**, em PRs
separados. Commits e PRs em inglês imperativo; comentários de código **sem
acento e sem travessão**; texto que aparece na tela continua com acento.

## As 10 perguntas

Para cada PR, responder, no corpo do PR:

1. Qual é o objetivo e que comportamento tem de ficar idêntico?
2. Dá para fazer com menos código?
3. Há redundância — a mesma coisa dita em dois lugares?
4. Criei abstração sem ganho (camada, função, classe que só repassa)?
5. Os nomes dizem o que a coisa é?
6. Algum comentário só repete o código? (e está sem acento e sem travessão?)
7. O fluxo ficou mais direto, com menos desvios?
8. Existe recurso nativo da linguagem/plataforma que faz isso?
9. Como se testa — qual teste prova que nada mudou?
10. Ficou mesmo **mais simples**, ou só **mais curto**?

A 10 é a que decide: se a resposta for "só mais curto", o PR não vale.

## Os blocos

| # | Bloco | Estado |
|---|---|---|
| 1 | Tirar JS/CSS de dentro de strings Python | mover **concluído**; limpeza em andamento |
| 2 | Telas web (`telas.py`, `notas_tela.py`, `markdown.py`) | não começou |
| 3 | Consultas e gráficos (`consultas.py`, `graficos.py`, `grafo_svg.py`) | não começou |
| 4 | Tools (a camada MCP) | não começou |
| 5 | Canais e testes | não começou |

---

## Bloco 1 — JS/CSS fora do Python

### O que já foi feito

O passo de **mover** acabou em `#151`–`#154`. Os quatro arquivos estáticos
agora são arquivos de verdade, lidos por `aide/web/estaticos.py:ler`:

| Arquivo | Linhas | Quem lê |
|---|---|---|
| `aide/web/static/css/*.css` | 787 (8 partes desde `#158`) | `aide/web/app.py:156` |
| `aide/web/static/js/app.js` | 2255 | `aide/web/app.py:100` |
| `aide/web/static/js/arquivos.js` | 951 | `aide/web/app.py:107` |
| `aide/web/static/js/desenho.js` | 581 | `aide/web/desenho_tela.py:136` |

Os módulos `estilo.py`, `script.py` e `desenho_script.py` morreram; os testes
que dependiam deles passaram a ler pelo `estaticos.ler` (ver
`tests/test_desenho_tela.py`, `tests/test_arquivos_tela.py`,
`tests/test_script.py`, `tests/test_notas_tela.py`).

Depois do mover, as limpezas:

- `#155` — a tela Arquivos usava `.editor-topo`, classe das notas, só pelo
  visual parecido. Ganhou `.arq-secao-topo` própria, e o cabeçalho da nota
  voltou a ser declarado uma vez só.
- `#156` — regras declaradas duas vezes foram juntadas, cores de callout iguais
  à padrão caíram, e nasceram as variáveis `--mono`, `--azul`, `--verde`,
  `--ok`.
- `#157` — comentários do `app.css` sem acento e sem travessão (51 linhas). O
  CSS com os comentários removidos tem o mesmo `sha256` (`af2378283bf5`) antes e
  depois; as duas linhas `content:` guardaram o acento, são texto de tela.
- `#158` — `app.css` virou oito partes em `static/css/`, juntadas por
  `estaticos.folha()` na ordem de `PARTES_CSS` (`base`, `layout`, `notas`,
  `editor`, `vault`, `responsivo`, `desenho`, `arquivos`). O `sha256` do corpo
  de `/app.css` é `41aff33a7522cae8` antes e depois. `test_web.py` ganhou o
  teste que confere que toda parte no disco está na lista.

- `#159` — a folha ganhou um padrão de escrita só: uma declaração por linha,
  dois espaços, linha em branco entre blocos, pelo `prettier@3.3.3` sem
  configuração (787 → 3041 linhas). Prova: normalizador que ignora espaço,
  comentário, aspas, caixa do hex e notação de zero diz que as oito partes têm
  as mesmas regras, na mesma ordem, com os mesmos valores. Quatro testes que
  citavam o CSS no formato antigo foram atualizados para o texto novo.
- `#160` — limpeza do `desenho.js` (581 → 600 linhas): `avisarFalha` (4 cópias
  da mensagem de rede), `jsonOuVazio` (7 leituras do corpo de erro), `rota()`
  com `URLSearchParams` (6 endereços colados à mão) e `corretor` com
  `instanceof Element`. Entrou `test_espaco_no_caminho_sobrevive_a_query`,
  porque `URLSearchParams` manda espaço como `+`.
- `#161` — limpeza do `arquivos.js` (951 → 968 linhas): `semExtensao` (6
  cópias, 2 regex diferentes), `selo`/`rotulo`/`medida` (a fila e a lista do
  lote montavam o arquivo igual), `serveAoTipo`, `somaPaginas` (4 cópias),
  `montar()` passou a servir os dois caminhos da rota, `toggleAttribute` e
  `depoisDaMetade`. Três comentários diziam a mesma coisa sobre o corpo do
  pedido; sobrou um. Um teste foi endurecido: a rota de montar tem de aparecer
  uma vez só.
- `#162` — varredura de repetição do `app.js` (2255 → 2270 linhas), sem mexer
  na estrutura: `normal()` e `semAcento()` eram **a mesma função com dois
  nomes**, a 1700 linhas de distância; o espelho do campo estava montado duas
  vezes (18 linhas) e virou `medirCursor`; mais `nomeCurto` (7 cópias),
  `pastaDe` (4), `salvarAberta` (5), `notaAberta` (3), `hrefDoDesenho` (3),
  `mostrarErro` (4) e `mostrarFalha` (4).

### O que falta, na ordem

**1. `app.js`: virar módulo ES.** A limpeza no lugar saiu no `#162`. Falta
trocar o `<script>` por `<script type="module">` e a IIFE `(function () {…})()`
pelo corpo do módulo — um módulo já tem escopo próprio, então a IIFE é
andaime. O `window.aideSalvar` e o `window.aideRealcar` continuam sendo o
contrato com o `desenho.js` e com as telas, e **precisam continuar no
`window`**: módulo não exporta para quem não importa.

**2. `app.js`: dividir em arquivos por assunto** (árvore, abrir rápido, editor,
prévia, blocos ao vivo, atalhos, anexos). Só depois de virar módulo: é o que
permite dividir sem criar global nenhuma.

**Armadilha dos dois:** `tests/test_script.py` roda pedaços do `app.js` no Node,
recortados por marcadores de texto (`function esc(t)`, `var desfazer = []`,
`function interpolar(`). Dividir o arquivo quebra esses recortes — o teste
passa a ler a parte certa, e os marcadores têm de sobreviver ou mudar junto.

### Armadilhas deste bloco

- As telas montam HTML com `f"""` (12 blocos só em `telas.py`). Chave literal
  dentro de `f-string` precisa ser dobrada; ao mover texto de dentro de uma
  `f-string` para um `.css`/`.js`, desdobrar `{{` e `}}`.
- O servidor serve esses arquivos a partir de `aide/web/static/`
  (`estaticos.PASTA`). Arquivo novo que ninguém lê não falha o teste — conferir
  que cada parte entrou na lista.
- Há testes que fazem `assert "algum-trecho" in estaticos.folha()`. Dividir um
  arquivo quebra esses `assert` sem quebrar a tela: atualizar o teste para ler a
  parte certa, não afrouxar o `assert`.

---

## Blocos 2 a 5 — como atacar quando chegar a vez

O método é o mesmo nos quatro: ler o módulo inteiro, responder as 10 perguntas
**antes** de editar, e quebrar o resultado em PRs de um assunto cada.

**Bloco 2 — telas web.** `telas.py` (1312), `notas_tela.py` (748),
`markdown.py` (751). `telas.py` já tem helpers bons (`_cartao`, `_indicador`,
`_lista`, `_selo`, `_linha_tarefa`); o trabalho é ver quais `f"""` de 12 blocos
repetem estrutura que já existe num helper, e separar as telas grandes
(`painel`, `hoje`, `calendario`, `gastos`) em arquivos por tela. Pergunta 4
pesa: não criar um "motor de template" para quatro telas.

**Bloco 3 — consultas e gráficos.** `consultas.py` (483), `graficos.py` (366),
`grafo_svg.py` (215). Procurar o mesmo recorte de período escrito em vários
lugares (`periodo`, `de`, `ate` aparecem em tela e em consulta) e os palpites de
número que o `PENDENCIAS.md` lista — aqui é só não os espalhar mais.

**Bloco 4 — tools.** A camada MCP. Ponto de atenção que vale mais que
simplicidade: **a camada de privacidade.** `ver_privado` nasce falso e todo
canal novo tem de decidir — qualquer extração de helper aqui precisa manter
esse padrão explícito, não herdado por acidente.

**Bloco 5 — canais e testes.** Por último porque é a rede de segurança dos
outros quatro: mexer nela antes é tirar o chão.

---

## Rotina de cada PR

1. Branch a partir do `main`.
2. Um assunto só; se descobrir outro no caminho, anotar e abrir outro PR.
3. `sha256` da resposta HTTP antes e depois, quando o PR é de mover.
4. Rodar os testes (`pytest`).
5. Corpo do PR: as 10 respostas.
6. Merge sem esperar; seguir para o próximo.
