import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
import pytz
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from conversation import get_history, save_history, clear_history
from memory import get_memories, get_memories_with_ids, save_memory, clear_memories, extract_and_save
from reminders import is_reminder_sent, mark_reminder_sent
import anthropic
from groq import Groq
from google.oauth2 import service_account
from googleapiclient.discovery import build

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ALLOWED_USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
TIMEZONE = "America/Sao_Paulo"
REMINDER_MINUTES = int(os.environ.get("REMINDER_MINUTES", "30"))

CALENDARS = {
    "principal": "seu_email@gmail.com",
    "saude": "CALENDAR_ID_SAUDE",
    "trabalho": "CALENDAR_ID_TRABALHO",
    "aulas": "CALENDAR_ID_AULAS",
}

credentials = service_account.Credentials.from_service_account_info(
    json.loads(GOOGLE_SERVICE_ACCOUNT_JSON),
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

TOOLS = [
    {
        "name": "get_current_datetime",
        "description": "Retorna data e hora atual em Curitiba (America/Sao_Paulo)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "create_event",
        "description": "Cria um evento no Google Calendar",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Título do evento"},
                "start_datetime": {"type": "string", "description": "Início no formato ISO 8601, ex: 2026-05-01T14:00:00"},
                "end_datetime": {"type": "string", "description": "Fim no formato ISO 8601"},
                "calendar": {"type": "string", "enum": ["principal", "saude", "trabalho", "aulas"], "description": "Qual calendário usar"},
                "description": {"type": "string"},
                "location": {"type": "string"}
            },
            "required": ["summary", "start_datetime", "end_datetime", "calendar"]
        }
    },
    {
        "name": "list_events",
        "description": "Lista eventos do calendário em um período",
        "input_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "Início da busca ISO 8601"},
                "time_max": {"type": "string", "description": "Fim da busca ISO 8601"},
                "calendar": {"type": "string", "enum": ["principal", "saude", "trabalho", "aulas"], "description": "Calendário para buscar (padrão: principal)"}
            },
            "required": ["time_min", "time_max"]
        }
    },
    {
        "name": "delete_event",
        "description": "Remove um evento do calendário pelo ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar": {"type": "string", "enum": ["principal", "saude", "trabalho", "aulas"]}
            },
            "required": ["event_id", "calendar"]
        }
    }
]

def _iso_with_tz(dt_str: str) -> str:
    if not dt_str:
        return dt_str
    if "+" not in dt_str and "Z" not in dt_str and len(dt_str) >= 16:
        return dt_str + "-03:00"
    return dt_str

def execute_tool(name: str, inp: dict) -> str:
    tz = pytz.timezone(TIMEZONE)

    if name == "get_current_datetime":
        now = datetime.now(tz)
        return json.dumps({
            "iso": now.isoformat(),
            "weekday": now.strftime("%A"),
            "formatted": now.strftime("%d/%m/%Y %H:%M")
        })

    elif name == "create_event":
        cal_id = CALENDARS[inp.get("calendar", "principal")]
        body = {
            "summary": inp["summary"],
            "start": {"dateTime": _iso_with_tz(inp["start_datetime"]), "timeZone": TIMEZONE},
            "end": {"dateTime": _iso_with_tz(inp["end_datetime"]), "timeZone": TIMEZONE},
        }
        if inp.get("description"):
            body["description"] = inp["description"]
        if inp.get("location"):
            body["location"] = inp["location"]
        result = calendar_service.events().insert(calendarId=cal_id, body=body).execute()
        return json.dumps({"success": True, "event_id": result["id"], "summary": result["summary"]})

    elif name == "list_events":
        cal_id = CALENDARS[inp.get("calendar", "principal")]
        result = calendar_service.events().list(
            calendarId=cal_id,
            timeMin=_iso_with_tz(inp["time_min"]),
            timeMax=_iso_with_tz(inp["time_max"]),
            maxResults=15,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = [
            {"id": e["id"], "summary": e.get("summary", "Sem título"),
             "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
             }
            for e in result.get("items", [])
        ]
        return json.dumps(events)

    elif name == "delete_event":
        cal_id = CALENDARS[inp.get("calendar", "principal")]
        calendar_service.events().delete(calendarId=cal_id, eventId=inp["event_id"]).execute()
        return json.dumps({"success": True})

    return json.dumps({"error": "Ferramenta desconhecida"})

BASE_SYSTEM_PROMPT = """Você é o assistente pessoal do Hudson, morando em Curitiba-PR (fuso America/Sao_Paulo).
Sua função principal é gerenciar a agenda dele no Google Calendar e ser um assistente de confiança.

Calendários:
- principal: compromissos gerais
- saude: consultas médicas, exames, academia
- trabalho: reuniões e compromissos profissionais
- aulas: cursos, aulas particulares, workshops

Regras:
1. Sempre chame get_current_datetime antes de criar ou listar eventos
2. Interprete linguagem natural: "sexta", "amanhã", "semana que vem às 14h"
3. Se não souber o horário de fim, assuma 1 hora de duração
4. Escolha o calendário certo conforme o tipo do evento
5. Confirme o agendamento de forma curta e direta
6. Responda sempre em português, de forma informal
7. Use as memórias abaixo para personalizar respostas e manter continuidade entre conversas

{memories_section}"""

def build_system_prompt(user_id: int) -> str:
    memories = get_memories(user_id)
    if memories:
        memories_text = "Memórias sobre o Hudson:\n" + "\n".join(f"- {m}" for m in memories)
    else:
        memories_text = "Nenhuma memória registrada ainda."
    return BASE_SYSTEM_PROMPT.format(memories_section=memories_text)

def _serialize_content(content):
    if not isinstance(content, list):
        return content
    return [block.model_dump() if hasattr(block, "model_dump") else block for block in content]

async def process_message(user_id: int, text: str) -> str:
    messages = get_history(user_id)
    messages.append({"role": "user", "content": text})
    system_prompt = build_system_prompt(user_id)

    while True:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages
        )
        if response.stop_reason == "end_turn":
            serialized = _serialize_content(response.content)
            messages.append({"role": "assistant", "content": serialized})
            save_history(user_id, messages)
            asyncio.get_event_loop().run_in_executor(None, extract_and_save, user_id, messages)
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Feito!"
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            messages.append({"role": "user", "content": tool_results})
        else:
            return "Algo deu errado, tente novamente."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_chat_action("typing")
    reply = await process_message(update.effective_user.id, update.message.text)
    await update.message.reply_text(reply)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_chat_action("typing")
    voice_file = await update.message.voice.get_file()
    audio_bytes = await voice_file.download_as_bytearray()
    transcription = groq_client.audio.transcriptions.create(
        file=("voice.ogg", bytes(audio_bytes)),
        model="whisper-large-v3-turbo",
        language="pt"
    )
    text = transcription.text
    reply = await process_message(update.effective_user.id, text)
    await update.message.reply_text(f"_{text}_\n\n{reply}", parse_mode="Markdown")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Oi! Me diz o que quer agendar ou o que precisa.")

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Seu ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text("Histórico da sessão limpo.")

async def cmd_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_memories_with_ids(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Nenhuma memória registrada ainda.")
        return
    lines = []
    for mem_id, content, created_at in rows:
        from datetime import datetime
        import pytz
        dt = datetime.fromtimestamp(created_at, tz=pytz.timezone(TIMEZONE))
        lines.append(f"[{mem_id}] {dt.strftime('%d/%m')} — {content}")
    await update.message.reply_text("\n".join(lines))

async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove uma memória específica pelo ID: /forget 42"""
    from memory import delete_memory
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Use: /forget <id> — veja os IDs com /memories")
        return
    delete_memory(update.effective_user.id, int(args[0]))
    await update.message.reply_text(f"Memória {args[0]} removida.")

async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona uma memória manualmente: /remember prefiro reuniões de manhã"""
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Use: /remember <fato>")
        return
    save_memory(update.effective_user.id, text)
    await update.message.reply_text("Memorizado!")

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    if not ALLOWED_USER_ID:
        return
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    window_end = now + timedelta(minutes=REMINDER_MINUTES + 5)
    for cal_name in CALENDARS:
        try:
            events = json.loads(execute_tool("list_events", {
                "time_min": now.isoformat(),
                "time_max": window_end.isoformat(),
                "calendar": cal_name
            }))
        except Exception:
            continue
        for event in events:
            event_id = event["id"]
            start_str = event["start"]
            if "T" not in start_str:
                continue
            try:
                start_dt = datetime.fromisoformat(start_str)
                minutes_until = (start_dt - now).total_seconds() / 60
            except Exception:
                continue
            if minutes_until <= REMINDER_MINUTES and not is_reminder_sent(ALLOWED_USER_ID, event_id):
                mark_reminder_sent(ALLOWED_USER_ID, event_id)
                await context.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=f"⏰ Daqui {int(minutes_until)} min: *{event['summary']}*",
                    parse_mode="Markdown"
                )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("memories", cmd_memories))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.job_queue.run_repeating(check_reminders, interval=300, first=30)
    app.run_polling()

if __name__ == "__main__":
    main()
