# Telegram Personal Assistant Bot

Assistente pessoal no Telegram com integração ao Google Calendar, memória persistente, suporte a voz e busca na web.

## Funcionalidades

- **Agenda**: cria, lista e remove eventos no Google Calendar via linguagem natural
- **Voz**: transcreve áudios enviados pelo Telegram (Groq Whisper)
- **Lembretes proativos**: envia mensagem automática 30 minutos antes de eventos
- **Memória persistente**: aprende fatos sobre o usuário ao longo das conversas
- **Busca na web**: pesquisa informações atuais via Tavily
- **Lista de compras**: adiciona, lista e remove itens

## Calendários

| Nome | Uso |
|------|-----|
| `principal` | Compromissos gerais |
| `saude` | Consultas, exames, academia |
| `trabalho` | Reuniões e compromissos profissionais |
| `aulas` | Cursos, aulas particulares, workshops |

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Inicia o bot |
| `/myid` | Mostra seu Telegram user ID |
| `/clear` | Limpa o histórico da sessão |
| `/memories` | Lista as memórias salvas |
| `/remember <fato>` | Adiciona uma memória manualmente |
| `/forget <id>` | Remove uma memória pelo ID |
| `/compras` | Exibe a lista de compras |

## Variáveis de ambiente

```env
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
TAVILY_API_KEY=
TELEGRAM_USER_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
DB_PATH=/data/history.db
REMINDER_MINUTES=30
```

## Setup local

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
cp .env.example .env  # preencha as variáveis
venv/Scripts/python main.py
```

## Deploy (Railway)

1. Conecta o repositório no Railway
2. Adiciona todas as variáveis de ambiente
3. Cria um Volume com mount path `/data`
4. O serviço é do tipo **worker** (sem porta exposta)

## Estrutura

```
main.py          # bot, handlers, tools do Claude
conversation.py  # histórico de sessão (SQLite)
memory.py        # memória persistente com extração via LLM
reminders.py     # controle de lembretes enviados
shopping.py      # lista de compras (SQLite)
```
