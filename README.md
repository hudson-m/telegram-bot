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
| `/notas` | Lista as notas salvas |
| `/painel` | Gera link temporário para o painel web |

## Variáveis de ambiente

Todas estão documentadas em [`.env.example`](.env.example). Resumo:

| Variável | Obrigatória | Uso |
|----------|:-----------:|-----|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token do BotFather |
| `TELEGRAM_USER_ID` | ✅ | Único usuário atendido (descubra com `/myid`) |
| `ANTHROPIC_API_KEY` | ✅ | Claude (conversa e ferramentas) |
| `GROQ_API_KEY` | ✅ | Transcrição de voz |
| `TAVILY_API_KEY` | ✅ | Busca na web |
| `GOOGLE_MAPS_API_KEY` | ✅ | Lugares próximos |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ | Acesso ao Google Calendar |
| `CALENDAR_PRINCIPAL` | ✅ | ID do calendário principal |
| `CALENDAR_SAUDE` / `CALENDAR_TRABALHO` / `CALENDAR_AULAS` | | Calendários extras (omitidos se vazios) |
| `ENCRYPTION_KEY` | ✅ | Chave Fernet para as notas |
| `SESSION_SECRET` | recomendada | Assina sessão do painel (sem ela, sessões caem a cada restart) |
| `WEBAPP_DOMAIN` / `WEBAPP_ORIGIN` | em produção | Domínio/origem do painel (passkeys) |
| `DB_PATH` | | Caminho do SQLite (padrão `history.db`) |
| `REMINDER_MINUTES` | | Antecedência dos lembretes (padrão 30) |

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
4. Gera um domínio público para o serviço e configura `WEBAPP_DOMAIN` / `WEBAPP_ORIGIN` com ele (o painel web roda na porta `PORT`)
5. No Telegram, use `/painel` para receber o link de registro da passkey

## Estrutura

```
main.py          # bot, handlers, tools do Claude
conversation.py  # histórico de sessão (SQLite)
memory.py        # memória persistente com extração via LLM
reminders.py     # controle de lembretes enviados
shopping.py      # lista de compras (SQLite)
notes.py         # bloco de notas criptografado (SQLite + Fernet)
usage.py         # custo de tokens por modelo
web.py           # painel web (FastAPI + passkeys/WebAuthn)
```
