import sqlite3
import json
import time
import os
import anthropic

DB_PATH = os.environ.get("DB_PATH", "history.db")

EXTRACT_PROMPT = """Analise essa conversa e extraia fatos importantes sobre o usuário que valem ser lembrados no futuro.

Vale lembrar:
- Compromissos agendados ou cancelados
- Preferências mencionadas
- Informações pessoais relevantes
- Pendências ou intenções ("quer marcar X em breve")
- Qualquer contexto útil para futuras conversas

Retorne SOMENTE um JSON válido, sem texto antes ou depois:
{"memories": ["fato 1", "fato 2"]}

Se não houver nada relevante: {"memories": []}

Conversa:
{conversation}"""


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_memories(user_id: int) -> list[str]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT content FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
            (user_id,)
        ).fetchall()
    return [row[0] for row in rows]


def save_memory(user_id: int, content: str):
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content.strip(), time.time())
        )


def delete_memory(user_id: int, memory_id: int):
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            (memory_id, user_id)
        )


def get_memories_with_ids(user_id: int) -> list[tuple]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
            (user_id,)
        ).fetchall()
    return rows


def clear_memories(user_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))


def extract_and_save(user_id: int, messages: list):
    """Extrai memórias da conversa recente e salva. Chamado em background."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    conversation_text = ""
    for msg in messages[-10:]:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            conversation_text += f"{role}: {content}\n"
        elif isinstance(content, list):
            for block in content:
                text = None
                if hasattr(block, "text"):
                    text = block.text
                elif isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"]
                if text:
                    conversation_text += f"{role}: {text}\n"

    if not conversation_text.strip():
        return

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": EXTRACT_PROMPT.format(conversation=conversation_text)
            }]
        )
        text = response.content[0].text
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end])
        for memory in data.get("memories", []):
            if memory.strip():
                save_memory(user_id, memory)
    except Exception:
        pass
