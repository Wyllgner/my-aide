# my-aide

Assessor pessoal local: lembra, organiza e cobra. Roda na sua máquina, guarda
tudo em SQLite e usa a API da OpenAI só para interpretar e redigir.

## Instalar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # preencha OPENAI_API_KEY
.venv/bin/myaide init
.venv/bin/myaide doctor     # tudo verde?
```

## Usar

```bash
myaide hoje                          # o que precisa de você
myaide add "Pagar boleto" -d 2026-09-05T09:00
myaide done 3
myaide ls overdue                    # today | overdue | week | inbox | done | all
myaide chat                          # conversa; ele cria e altera tarefas sozinho
myaide checar                        # o que as regras de condição estão vendo
myaide status                        # retrato geral: estado, cobranças e custo
mymyaide custo                       # quanto a API custou e quanto ainda cabe no mês
myaide usage                       # quanto de LLM foi consumido
myaide pessoas                       # com quem você combinou de manter contato
myaide falei Pedro "vai se mudar"    # registra o contato
```

### Gastos

```bash
myaide gasto "10,50 almoço com a KA"      # valor na frente, resto é descrição
myaide gasto "187,90 mercado" -c mercado
myaide gastos                             # lançamentos do mês
myaide quanto mes                         # hoje | ontem | semana | mes | ano | sempre
myaide quanto mes -c mercado
```

Por conversa funciona igual, e é o caminho normal no Telegram — ele deduz a
categoria sozinho:

```
você: 10,50 almoço com a KA
ele:  Anotei R$ 10,50 em alimentação (#12).

você: quanto eu gastei esse mês?
ele:  Você gastou R$ 270,80 este mês, em 5 lançamentos.
```

O valor é guardado em centavos inteiros — somar float acumula erro até o total
não bater. Registrar pelo terminal não chama a OpenAI: o parser é determinístico.

### Notas e memória

```bash
myaide nota "Reunião de orçamento" "cortar 20% da nuvem"
myaide nota "Do stdin" < arquivo.md
myaide notas                         # as mais recentes
myaide buscar "reduzir custo de servidor"   # acha por significado, não só palavra
myaide perfil                        # o que ele sabe sobre você
myaide reindexar                     # reconstrói o índice a partir do vault
```

As notas vivem em `vault/AAAA-MM/*.md` com frontmatter — legíveis sem o projeto.
O SQLite é só índice: `myaide reindexar` reconstrói tudo a partir dos arquivos.

## O daemon

É o que faz dele um assessor e não um chatbot: lembretes, cobrança de atrasos e
briefings acontecem sem você abrir nada.

```bash
myaide serve                         # em primeiro plano
myaide job briefing_manha            # roda um job agora, para testar
```

Para rodar sempre, veja `deploy/my-aide.service`.

## Interface gráfica

```bash
.venv/bin/pip install -e ".[gui]"
myaide-gui
```

App nativo (PySide6): sidebar com contador de pendência, captura rápida em
"Hoje", clique duplo conclui, busca semântica nas notas, e a conversa como uma
aba — não como a tela inteira. Fechar a janela some para a bandeja; o assessor
continua ali.

## Telegram (opcional, mas é o que faz ele te alcançar)

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

O bot sobe junto com `myaide serve`. Só os chats da lista são atendidos — qualquer
outro recebe só o próprio id, nunca os seus dados.

## Agenda (opcional)

Leitura de um calendário assinado — sem OAuth, sem app registrado.

No Google Agenda: **Configurações da agenda > Integrar agenda > Endereço
secreto no formato iCal**. Cole em `config.yaml`:

```yaml
calendar:
  ics_url: "https://calendar.google.com/calendar/ical/.../basic.ics"
```

```bash
myaide agenda --sync        # baixa e mostra
myaide agenda -d 14         # próximas duas semanas, com conflitos de horário
```

O daemon re-sincroniza sozinho a cada 6h. É só leitura: o my-aide não cria nem
altera nada na sua agenda.

## MCP: plugar um executor externo

O assessor expõe suas tools por MCP, então um agente de propósito geral
(Claude Desktop, Cowork e afins) enxerga suas tarefas, notas e a fila de
trabalho — e escreve o resultado de volta aqui.

```bash
myaide mcp-config     # imprime o bloco para colar no cliente
```

Tools marcadas `confirm` (apagar tarefa, nota ou memória) **não** são expostas:
por MCP não há como pedir "tem certeza?" a uma pessoa.

### Fila de trabalho

O daemon não faz trabalho pesado — ele enfileira e deixa pronto para quando
você abrir uma sessão com o executor:

```bash
myaide fila                    # o que está esperando
myaide enfileirar "Organizar as notas fiscais de agosto" -c "estão em ~/Downloads"
myaide job queue_work          # roda agora o que o daemon faria
```

No executor, comece por `work_orders_list`; ao terminar, `work_orders_complete`
grava o resultado aqui — é assim que o trabalho feito lá fora vira memória.

## Quanto custa

```bash
myaide custo          # mês corrente, com barra do orçamento
myaide custo -d 7     # últimos 7 dias
```

Por conversa também: "quanto de API eu já gastei esse mês?".

**Saldo da conta a OpenAI não expõe por API** — os endpoints de billing exigem a
sessão do navegador e recusam chave de API com 403. O jeito de acompanhar é
ancorar: você lê o saldo no painel uma vez, anota, e o assessor desconta o gasto
a partir dali.

```bash
myaide saldo 4.22     # o que o painel mostra
myaide saldo          # quanto deve restar hoje
```

Por conversa funciona igual: "meu saldo da API é 4,22" anota, "quanto ainda
tenho de crédito?" responde. É estimativa, e ele diz que é — reancore quando
passar do painel de novo. Depois de um mês sem reancorar, ele lembra você.

Há também um teto mensal opcional, para quem prefere limitar o ritmo em vez de
acompanhar o saldo:

```yaml
llm:
  orcamento_mensal_usd: 5.0    # 0 desliga
```

O número padrão é estimado dos tokens registrados vezes os preços do
`config.yaml`. Para ver o **custo real** cobrado pela OpenAI, crie uma chave de
admin (platform.openai.com > Settings > Organization > Admin keys) com o escopo
`api.usage.read` e ponha em `.env` como `OPENAI_ADMIN_KEY`. É outro tipo de
credencial: a chave normal da API não serve.

## Configuração

`config.yaml` (versionado) define modelo, horários e canais de notificação.
`config.local.yaml` sobrepõe e é ignorado pelo git — use para o que é só seu.

## Desenvolvimento

```bash
.venv/bin/pytest tests/ -q
.venv/bin/ruff check aide/ tests/
```
