<div align="center">

# my-aide

**Um assessor pessoal que roda na sua máquina.**
Ele lembra, organiza e cobra. Seus dados nunca saem do seu disco.

<p>
<img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
<img alt="SQLite" src="https://img.shields.io/badge/dados-SQLite%20local-003B57?logo=sqlite&logoColor=white">
<img alt="Testes" src="https://img.shields.io/badge/testes-551-2EA043">
<img alt="Licença" src="https://img.shields.io/badge/uso-pessoal-6E7681">
</p>

</div>

---

## A ideia

Um cron dispara por horário. O my-aide dispara por **condição sobre os seus dados**:

| Gatilho por tempo | Gatilho por condição |
|---|---|
| "toda segunda às 9h, me manda um resumo" | "esta tarefa você já adiou 3 vezes, ainda importa?" |
| basta um cron | precisa de um banco com o seu histórico |

Um cron não sabe que você adiou três vezes. Só sabe quem guardou. É isso que o
my-aide guarda, e é por isso que ele mora na sua máquina: o estado e o critério
são seus, a mão de obra é que é emprestada da API.

```
você:  10,50 almoço com a KA
ele:   Anotei R$ 10,50 em alimentação (#12).

você:  me lembra de enviar o artigo quinta às 20h
ele:   Lembrete criado para quinta às 20h (#5).

(dois dias depois, sem você pedir nada, no Telegram)
ele:   #15 Enviar versão final do artigo venceu ontem.
       Uma decisão registrada: seguir, adiar com data, ou encerrar.
```

## Começar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,web]"
cp .env.example .env          # preencha OPENAI_API_KEY
.venv/bin/myaide init         # cria o banco e aplica as migrations
.venv/bin/myaide doctor       # confere o ambiente, tudo verde?
```

Para chamar só `myaide`, ponha um symlink em `~/.local/bin`:

```bash
ln -s "$PWD/.venv/bin/myaide" ~/.local/bin/myaide
```

## O dia a dia

```bash
myaide hoje                             # o que precisa de você
myaide add "Pagar boleto" -d 2026-09-25T09:00
myaide done 3
myaide ls overdue                       # today, overdue, week, inbox, done, all
myaide add "pagar o aluguel" -d "10/10 09:00" -r "todo mês"
myaide lembrete "tirar o bolo" -q 20h   # "amanhã 9h", "quinta 20h", "25/09 14h"
myaide lembretes                        # o que ainda vai disparar
myaide chat                             # conversa; ele cria e altera tarefas sozinho
myaide checar                           # o que as regras de condição estão vendo
myaide status                           # retrato geral: estado, cobranças e custo
```

Tarefa com repetição volta sozinha: concluir a do aluguel cria a próxima
ocorrência na hora, contada a partir do prazo e não de hoje, e o terminal diz
quando ela volta. As repetições são cinco: todo dia, dias úteis, toda semana,
todo mês, todo ano.

O `--help` é agrupado por assunto, então dá para achar um comando sem conhecer
a lista inteira. O horário do lembrete é lido por um parser determinístico, o
que significa que criar um lembrete não custa chamada de API e funciona offline.

### Dinheiro

```bash
myaide gasto "10,50 almoço com a KA"    # valor na frente, o resto é descrição
myaide gasto "187,90 mercado" -c mercado
myaide gastos                           # lançamentos do mês
myaide quanto mes                       # hoje, ontem, semana, mes, ano, sempre
myaide quanto mes -c mercado
```

### Teto por categoria

Declare um teto e o assessor passa a cobrar sozinho, em vez de só responder
quando perguntado:

```yaml
gastos:
  tetos:
    alimentação: 800     # reais por mês
    transporte: 300
  avisar_em: 0.8         # a partir de quanto do teto ele avisa
```

Chegando em 80% ele avisa; passando do teto, a cobrança sobe para urgente e
chega junto com o resto do que precisa de você. Sem teto declarado ele não diz
nada, porque não teria como ter opinião sobre quanto é muito.

Há também o gasto atípico, que não precisa de configuração: um lançamento muito
acima do seu normal é apontado, comparado com a **mediana** dos últimos 90 dias
(a média seria puxada pela própria compra grande) e só depois de existir
histórico suficiente. Gasto marcado como privado entra na soma do teto e nunca
no texto do aviso: somar mantém o total verdadeiro, nomear entregaria pelo aviso
o que a listagem esconde.

Por conversa funciona igual, e é o caminho normal no Telegram: ele deduz a
categoria sozinho. Dois detalhes que valem saber:

* O valor é guardado em **centavos inteiros**. Somar float acumula erro até o
  total do mês não bater, e esse é o tipo de bug que só aparece quando já não dá
  para saber qual lançamento está errado.
* Registrar pelo terminal **não gasta API**. O parser é determinístico, então
  funciona offline e sai de graça.

### Notas e memória

```bash
myaide nota "Reunião de orçamento" "cortar 20% da nuvem"
myaide nota "Do stdin" < arquivo.md
myaide notas
myaide buscar "reduzir custo de servidor"    # por significado, não só palavra
myaide perfil                                # o que ele sabe sobre você
myaide reindexar                             # reconstrói o índice a partir do vault
```

As notas vivem em `vault/AAAA-MM/*.md` com frontmatter, legíveis sem o projeto.
O SQLite é só índice, e o vault manda nos dois sentidos:

* Um `.md` que você escreveu no editor e salvou em `vault/` é **adotado** na
  próxima reindexação, com o título lido do frontmatter.
* Apagar uma nota move o arquivo para `vault/.trash/`, então o vault contém só
  nota viva. O texto continua legível ali, e voltar é um `mv`.
* Linha sem arquivo é acusada por nome, em vez de falhar calada na busca.

### Pessoas e agenda

```bash
myaide pessoa Pedro -r amigo -c 14      # passa a acompanhar, cobrando a cada 14 dias
myaide pessoas                          # com quem você combinou de manter contato
myaide falei Pedro "vai se mudar"       # registra o contato de hoje
myaide pessoa Pedro --esquecer          # para de acompanhar
myaide agenda -d 14                     # próximas duas semanas, com conflitos
```

## O daemon

É o que separa um assessor de um chatbot: lembretes, cobrança de atraso e
briefings acontecem sem você abrir nada.

```bash
myaide serve                  # em primeiro plano
myaide job briefing_manha     # roda um job agora, para testar
```

Oito jobs cuidam do ciclo:

| Job | O que faz |
|---|---|
| `tick_reminders` | dispara o que venceu, inclusive o que passou com a máquina desligada |
| `eval_conditions` | avalia as regras e cobra o que merece atenção |
| `briefing_manha` | o que vence hoje e o que ficou atrás |
| `briefing_noite` | o que foi concluído e o que sobrou |
| `revisao_semanal` | o retrato de domingo |
| `queue_work` | enfileira trabalho para um executor externo |
| `reindex_vault` | reindexa a nota que mudou e adota a que você escreveu no editor |
| `sync_calendar` | baixa de novo o calendário assinado |

Os horários ficam em `config.yaml`: briefing às 07:30 e às 21:30, revisão no
domingo às 19:00, regras de condição a cada 12h. Para rodar sempre, inclusive
depois do reboot, use `deploy/my-aide.service`.

## Interface web

Sobe junto com o daemon em **http://127.0.0.1:8787**, com doze telas de leitura:
painel com gráficos, hoje, calendário do mês, conversas, notas, gastos, custo e
saldo, memória, pessoas, fila, ferramentas e auditoria.

> **Só leitura, e só nesta máquina.** A página mostra tudo, inclusive o que está
> marcado como privado, e não pede senha. O que a torna segura é escutar em
> 127.0.0.1, e por isso o endereço é constante no código, não configuração.
> Concluir tarefa, lançar gasto e conversar continuam sendo CLI, Telegram ou MCP.

## Telegram

Opcional, mas é o que faz ele te alcançar sem você abrir nada.

1. Fale com o [@BotFather](https://t.me/BotFather), mande `/newbot` e copie o token.
2. Ponha em `.env`: `TELEGRAM_BOT_TOKEN=...`
3. Rode `myaide telegram-id` e mande qualquer mensagem para o seu bot.
4. Ponha o id que aparecer em `config.yaml`:

```yaml
telegram:
  enabled: true
  allowed_chat_ids: [123456789]
```

5. Adicione `telegram` em `notify.channels` para receber os briefings por lá.

O bot sobe junto com `myaide serve`. Só os chats da lista são atendidos, e
qualquer outro recebe apenas o próprio id, nunca os seus dados.

## Agenda

Leitura de um calendário assinado, sem OAuth e sem app registrado. No Google
Agenda: **Configurações da agenda > Integrar agenda > Endereço secreto no
formato iCal**. Cole em `config.local.yaml`, que é ignorado pelo git, porque o
link dá acesso de leitura à agenda inteira:

```yaml
calendar:
  ics_url: "https://calendar.google.com/calendar/ical/.../basic.ics"
```

```bash
myaide agenda --sync      # baixa e mostra
```

O daemon re-sincroniza a cada 6h. É só leitura: o my-aide não cria nem altera
nada na sua agenda.

## MCP: um executor externo com acesso ao seu estado

O assessor expõe as tools por MCP, então um agente de propósito geral (Claude
Desktop, Cowork e afins) enxerga suas tarefas, notas e a fila de trabalho, e
escreve o resultado de volta aqui.

```bash
myaide mcp-config     # imprime o bloco para colar no cliente
```

São 38 tools, das quais 32 aparecem por MCP. As 6 marcadas `confirm` (apagar
tarefa, nota, gasto ou memória) ficam de fora de propósito: por MCP não existe
como perguntar "tem certeza?" a uma pessoa.

### Fila de trabalho

O daemon não faz trabalho pesado. Ele enfileira e deixa pronto para quando você
abrir uma sessão com o executor:

```bash
myaide fila
myaide enfileirar "Organizar as notas fiscais de agosto" -c "estão em ~/Downloads"
myaide job queue_work
```

No executor, comece por `work_orders_list`. Ao terminar, `work_orders_complete`
grava o resultado aqui, e é assim que o trabalho feito lá fora vira memória.

## Quanto custa

```bash
myaide custo          # mês corrente, com barra do orçamento
myaide custo -d 7     # últimos 7 dias
myaide usage          # consumo por modelo e finalidade, com o custo ao lado
```

Por conversa também: "quanto de API eu já gastei esse mês?".

**O saldo da conta a OpenAI não expõe por API.** Os endpoints de billing exigem
a sessão do navegador e recusam chave de API com 403. O jeito de acompanhar é
ancorar: você lê o saldo no painel uma vez, anota, e o assessor desconta o gasto
a partir dali.

```bash
myaide saldo 4,22     # o que o painel mostra
myaide saldo          # quanto deve restar hoje
```

Ele diz que é estimativa, e lembra você de reancorar depois de um mês. Se você
prefere limitar o ritmo em vez de acompanhar o saldo, há um teto mensal:

```yaml
llm:
  orcamento_mensal_usd: 5.0    # 0 desliga
```

Para ver o **custo real** cobrado pela OpenAI, crie uma chave de admin
(platform.openai.com > Settings > Organization > Admin keys) com o escopo
`api.usage.read` e ponha em `.env` como `OPENAI_ADMIN_KEY`. É outro tipo de
credencial: a chave normal da API não serve.

## Privacidade, por dentro

Não é promessa, é estrutura. Três decisões sustentam ela:

* **`ver_privado` nasce falso.** Quem quiser ler o que está marcado como privado
  tem de pedir, e só o terminal do dono pede. Modelo, MCP, Telegram e web ficam
  no padrão, então marcar como privado basta para o conteúdo não sair da máquina.
* **O guard é estrutural, não por tool.** Ele mora no caminho por onde todas as
  leituras passam, porque revisão manual esquece uma: foi assim que
  `tasks.complete` vazava a linha inteira até uma varredura automática pegá-lo.
* **Segredo com permissão apertada.** O `.env` e o banco são 600, apertados pelo
  próprio código ao abrir, e o backup usa `umask 077`. O conteúdo da conversa
  desceu para DEBUG, então o journal do systemd não guarda uma segunda cópia
  fora do banco fechado.

O que segue em aberto e não tem conserto bom: **injeção de prompt**. Nota,
mensagem ou resultado de tool podem conter texto que o modelo leia como
instrução. O que limita o estrago é o que já existe: tool destrutiva pede
confirmação e é recusada fora do CLI, e o MCP não expõe nenhuma delas.

## Como está organizado

```
aide/
  comandos/     a CLI, um módulo por assunto
  core/         orquestrador e contexto
  tools/        as 38 tools, a única forma de escrever no estado
  scheduler/    jobs, regras de condição e briefings
  channels/     terminal, Telegram, notificação de desktop
  storage/      SQLite, migrations, vault e busca
  llm/          provider, embeddings e cálculo de custo
  web/          a página em 127.0.0.1:8787
  mcp/          o servidor que o executor externo pluga
vault/          suas notas em markdown, a fonte da verdade
deploy/         unidade do systemd e script de backup
```

Duas regras que valem em todo o projeto: **escrita só por tool**, para tudo
passar pela trilha de auditoria, e **markdown é a fonte da verdade**, para o
banco poder ser reconstruído.

`ARQUITETURA.md` tem o desenho completo e o porquê de cada escolha.
`PENDENCIAS.md` tem o que falta, verificado no código.

## Configuração

`config.yaml` é versionado e define modelo, horários e canais de notificação.
`config.local.yaml` sobrepõe e é ignorado pelo git, então é onde vai o que é só
seu (o endereço do iCal, por exemplo).

## Desenvolvimento

```bash
.venv/bin/pytest -q                  # 551 testes
.venv/bin/pytest -q -m "not slow"    # sem os que sobem processo de verdade
.venv/bin/ruff check aide tests
```

Os testes de CLI rodam com `AIDE_ROOT` numa raiz temporária. Sem isso eles
abririam o banco real e, pior, o `.env` com as credenciais de verdade.
