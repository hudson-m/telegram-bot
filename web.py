import os
import json
import base64
import sqlite3
import time
import secrets
import logging
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from memory import get_memories_with_ids, delete_memory
from notes import list_notes, delete_note
from shopping import list_items, remove_item, clear_list
from usage import get_daily_usage, get_totals

WEBAPP_DOMAIN = os.environ.get("WEBAPP_DOMAIN", "localhost")
WEBAPP_ORIGIN = os.environ.get("WEBAPP_ORIGIN", f"http://localhost:8000")
SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
ALLOWED_USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
DB_PATH = os.environ.get("DB_PATH", "history.db")
SETUP_TOKEN = os.environ.get("SETUP_TOKEN", "")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
_pending_challenges: dict[str, bytes] = {}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webauthn_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credential_id BLOB NOT NULL UNIQUE,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _serializer():
    return URLSafeTimedSerializer(SESSION_SECRET)


def get_session_user(request: Request) -> Optional[int]:
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=86400 * 30)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def _decode_b64url(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (4 - len(s) % 4)
    return base64.b64decode(s)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = get_session_user(request)
    if not user_id:
        return RedirectResponse("/login")
    memories = get_memories_with_ids(user_id)
    notes = list_notes(user_id)
    shopping = list_items(user_id)
    totals = get_totals()
    daily = get_daily_usage(30)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "memories": memories,
        "notes": notes,
        "shopping": shopping,
        "totals": totals,
        "daily": daily,
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/")
    with _get_db() as conn:
        has_credential = conn.execute("SELECT 1 FROM webauthn_credentials LIMIT 1").fetchone() is not None
    token = request.query_params.get("token", "")
    setup_mode = bool(SETUP_TOKEN and secrets.compare_digest(token, SETUP_TOKEN))
    return templates.TemplateResponse("login.html", {
        "request": request,
        "has_credential": has_credential,
        "setup_mode": setup_mode,
        "setup_token": token if setup_mode else "",
    })


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("session")
    return response


@app.post("/auth/register/begin")
async def register_begin(request: Request):
    user_id = get_session_user(request)
    with _get_db() as conn:
        has_credential = conn.execute("SELECT 1 FROM webauthn_credentials LIMIT 1").fetchone() is not None
    token = request.query_params.get("token", "")
    token_ok = SETUP_TOKEN and secrets.compare_digest(token, SETUP_TOKEN)
    if has_credential and not user_id and not token_ok:
        raise HTTPException(403, "Já registrado")
    options = webauthn.generate_registration_options(
        rp_id=WEBAPP_DOMAIN,
        rp_name="Assistente do Hudson",
        user_id=b"hudson",
        user_name="hudson",
        user_display_name="Hudson",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        supported_pub_key_algs=[COSEAlgorithmIdentifier.ECDSA_SHA_256],
    )
    _pending_challenges["register"] = options.challenge
    return JSONResponse(content=json.loads(webauthn.options_to_json(options)))


@app.post("/auth/register/complete")
async def register_complete(request: Request):
    body = await request.json()
    challenge = _pending_challenges.pop("register", None)
    if not challenge:
        raise HTTPException(400, "Sem desafio pendente")
    try:
        credential = webauthn.verify_registration_response(
            credential=webauthn.helpers.parse_registration_credential_json(json.dumps(body)),
            expected_challenge=challenge,
            expected_rp_id=WEBAPP_DOMAIN,
            expected_origin=WEBAPP_ORIGIN,
        )
    except Exception as e:
        logging.error(f"WebAuthn error: {e}")
        raise HTTPException(400, str(e))
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO webauthn_credentials (credential_id, public_key, sign_count, created_at) VALUES (?, ?, ?, ?)",
            (credential.credential_id, credential.credential_public_key, credential.sign_count, time.time())
        )
    response = JSONResponse({"success": True})
    response.set_cookie("session", _serializer().dumps({"user_id": ALLOWED_USER_ID}),
                        httponly=True, samesite="lax", max_age=86400 * 30)
    return response


@app.post("/auth/login/begin")
async def login_begin():
    with _get_db() as conn:
        rows = conn.execute("SELECT credential_id FROM webauthn_credentials").fetchall()
    if not rows:
        raise HTTPException(400, "Nenhuma credencial registrada")
    options = webauthn.generate_authentication_options(
        rp_id=WEBAPP_DOMAIN,
        allow_credentials=[PublicKeyCredentialDescriptor(id=bytes(row[0])) for row in rows],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _pending_challenges["login"] = options.challenge
    return JSONResponse(content=json.loads(webauthn.options_to_json(options)))


@app.post("/auth/login/complete")
async def login_complete(request: Request):
    body = await request.json()
    challenge = _pending_challenges.pop("login", None)
    if not challenge:
        raise HTTPException(400, "Sem desafio pendente")
    credential_id = _decode_b64url(body.get("id", ""))
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, credential_id, public_key, sign_count FROM webauthn_credentials WHERE credential_id = ?",
            (credential_id,)
        ).fetchone()
    if not row:
        raise HTTPException(400, "Credencial não encontrada")
    try:
        verification = webauthn.verify_authentication_response(
            credential=webauthn.helpers.parse_authentication_credential_json(json.dumps(body)),
            expected_challenge=challenge,
            expected_rp_id=WEBAPP_DOMAIN,
            expected_origin=WEBAPP_ORIGIN,
            credential_public_key=bytes(row[2]),
            credential_current_sign_count=row[3],
        )
    except Exception as e:
        logging.error(f"WebAuthn error: {e}")
        raise HTTPException(400, str(e))
    with _get_db() as conn:
        conn.execute("UPDATE webauthn_credentials SET sign_count = ? WHERE id = ?",
                     (verification.new_sign_count, row[0]))
    response = JSONResponse({"success": True})
    response.set_cookie("session", _serializer().dumps({"user_id": ALLOWED_USER_ID}),
                        httponly=True, samesite="lax", max_age=86400 * 30)
    return response


@app.delete("/api/memories/{memory_id}")
async def api_delete_memory(memory_id: int, request: Request):
    user_id = get_session_user(request)
    if not user_id:
        raise HTTPException(401)
    delete_memory(user_id, memory_id)
    return {"success": True}


@app.delete("/api/notes/{note_id}")
async def api_delete_note(note_id: int, request: Request):
    user_id = get_session_user(request)
    if not user_id:
        raise HTTPException(401)
    delete_note(user_id, note_id)
    return {"success": True}


@app.delete("/api/shopping/{item_id}")
async def api_delete_shopping(item_id: int, request: Request):
    user_id = get_session_user(request)
    if not user_id:
        raise HTTPException(401)
    remove_item(user_id, item_id)
    return {"success": True}


@app.delete("/api/shopping")
async def api_clear_shopping(request: Request):
    user_id = get_session_user(request)
    if not user_id:
        raise HTTPException(401)
    clear_list(user_id)
    return {"success": True}
