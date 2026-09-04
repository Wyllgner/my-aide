# my-aide

Assessor pessoal local: lembra, organiza e cobra. Roda na sua máquina, guarda
tudo em SQLite e usa a API da OpenAI só para interpretar e redigir.

## Instalar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # preencha OPENAI_API_KEY
.venv/bin/aide init
.venv/bin/aide doctor     # tudo verde?
```

## Usar

```bash
aide hoje                          # o que precisa de você
aide add "Pagar boleto" -d 2026-09-05T09:00
aide done 3
aide ls overdue                    # today | overdue | week | inbox | done | all
aide chat                          # conversa; ele cria e altera tarefas sozinho
aide checar                        # o que as regras de condição estão vendo
aide usage                         # quanto de LLM foi consumido
```

### Notas e memória

```bash
aide nota "Reunião de orçamento" "cortar 20% da nuvem"
aide nota "Do stdin" < arquivo.md
aide notas                         # as mais recentes
aide buscar "reduzir custo de servidor"   # acha por significado, não só palavra
aide perfil                        # o que ele sabe sobre você
aide reindexar                     # reconstrói o índice a partir do vault
```

As notas vivem em `vault/AAAA-MM/*.md` com frontmatter — legíveis sem o projeto.
O SQLite é só índice: `aide reindexar` reconstrói tudo a partir dos arquivos.

## O daemon

É o que faz dele um assessor e não um chatbot: lembretes, cobrança de atrasos e
briefings acontecem sem você abrir nada.

```bash
aide serve                         # em primeiro plano
aide job briefing_manha            # roda um job agora, para testar
```

Para rodar sempre, veja `deploy/my-aide.service`.

## Telegram (opcional, mas é o que faz ele te alcançar)

1. Fale com o [@BotFather](https://t.me/BotFather), mande `/newbot` e copie o token.
2. Ponha em `.env`: `TELEGRAM_BOT_TOKEN=...`
3. Rode `aide telegram-id` e mande qualquer mensagem para o seu bot.
4. Ponha o id que aparecer em `config.yaml`:

```yaml
telegram:
  enabled: true
  allowed_chat_ids: [123456789]
```

5. Adicione `telegram` em `notify.channels` para receber os briefings por lá.

O bot sobe junto com `aide serve`. Só os chats da lista são atendidos — qualquer
outro recebe só o próprio id, nunca os seus dados.

## MCP: plugar um executor externo

O assessor expõe suas tools por MCP, então um agente de propósito geral
(Claude Desktop, Cowork e afins) enxerga suas tarefas, notas e a fila de
trabalho — e escreve o resultado de volta aqui.

```bash
aide mcp-config     # imprime o bloco para colar no cliente
```

Tools marcadas `confirm` (apagar tarefa, nota ou memória) **não** são expostas:
por MCP não há como pedir "tem certeza?" a uma pessoa.

### Fila de trabalho

O daemon não faz trabalho pesado — ele enfileira e deixa pronto para quando
você abrir uma sessão com o executor:

```bash
aide fila                    # o que está esperando
aide enfileirar "Organizar as notas fiscais de agosto" -c "estão em ~/Downloads"
aide job queue_work          # roda agora o que o daemon faria
```

No executor, comece por `work_orders_list`; ao terminar, `work_orders_complete`
grava o resultado aqui — é assim que o trabalho feito lá fora vira memória.

## Configuração

`config.yaml` (versionado) define modelo, horários e canais de notificação.
`config.local.yaml` sobrepõe e é ignorado pelo git — use para o que é só seu.

## Desenvolvimento

```bash
.venv/bin/pytest tests/ -q
.venv/bin/ruff check aide/ tests/
```
