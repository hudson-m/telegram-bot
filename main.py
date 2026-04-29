import os
import json
import asyncio
import logging
from datetime import datetime
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
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ALLOWED_USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
TIMEZONE = "America/Sao_Paulo"

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
             "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))}
            for e in result.get("items", [])
        ]
        return json.dumps(events)

    elif name == "delete_event":
        cal_id = CALENDARS[inp.get("calendar", "principal")]
        calendar_service.events().delete(calendarId=cal_id, eventId=inp["event_id"]).execute()
        return json.dumps({"success": True})

    return json.dumps({"error": "Ferramenta desconhecida"})

SYSTEM_PROMPT = """Você é o assistente pessoal do Hudson, morando em Curitiba-PR (fuso America/Sao_Paulo).
Sua função principal é gerenciar a agenda dele no Google Calendar.

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
6. Responda sempre em português, de forma informal"""

async def process_message(user_id: int, text: str) -> str:
    messages = get_history(user_id)
    messages.append({"role": "user", "content": text})
    while True:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )
        if response.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            save_history(user_id, messages)
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
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            return "Algo deu errado, tente novamente."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_chat_action("typing")
    reply = await process_message(update.effective_user.id, update.message.text)
    await update.message.reply_text(reply)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Oi! Me diz o que quer agendar.")

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Seu ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text("Histórico limpo.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
