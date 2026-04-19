# area_manager.py
from fastapi.responses import Response
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from datetime import datetime, date
from enum import Enum
from typing import Optional
import sqlite3
from pathlib import Path
import re

from config import AREA_MANAGER_DB_PATH, AREA_MANAGER_PIN, UPLOAD_ROOT
from storage import get_file_storage

app = FastAPI(title="Area Manager - Control Room")

# ====== CONFIG ======
PIN_UNICO = AREA_MANAGER_PIN
DB_PATH = AREA_MANAGER_DB_PATH


def _upload_storage_rel(site_code: str, kind: str, file_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_name)
    return "/".join(["uploads", "area_manager", "sites", site_code, kind, safe_name])


def _file_response(storage_ref: str, fallback_media_type: str = "application/pdf") -> Response:
    payload, media_type = get_file_storage().read_bytes(storage_ref)
    file_name = Path(storage_ref).name
    headers = {"Content-Disposition": f'inline; filename="{file_name}"'}
    return Response(content=payload, media_type=media_type or fallback_media_type, headers=headers)

@app.get("/files/{file_id}")
def get_file(
    file_id: int,
    username: str = Query(...),
    site_code: str = Query(...),
    kind: str = Query("breakdown")  # breakdown | document
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()

    if kind == "breakdown":
        cur.execute("""
            SELECT pdf_path AS path
            FROM am_breakdowns
            WHERE id=? AND site_code=?
        """, (file_id, sc))
    else:
        cur.execute("""
            SELECT file_path AS path
            FROM am_documents
            WHERE id=? AND site_code=?
        """, (file_id, sc))

    row = cur.fetchone()
    conn.close()

    if not row or not row["path"]:
        raise HTTPException(status_code=404, detail="File non trovato")

    storage_ref = row["path"]
    if not get_file_storage().exists(storage_ref):
        raise HTTPException(status_code=404, detail="File mancante su disco")

    return _file_response(storage_ref)



# =========================
# ENUM / MODELLI
# =========================
class Role(str, Enum):
    DIRECTION = "DIRECTION"
    AREA_MANAGER = "AREA_MANAGER"
    HR_SITE = "HR_SITE"
    OPS_MANAGER = "OPS_MANAGER"


class PresenceType(str, Enum):
    OPERATIVA = "OPERATIVA"
    AUDIT = "AUDIT"
    RIUNIONE = "RIUNIONE"
    EMERGENZA = "EMERGENZA"
    ALTRO = "ALTRO"


class BreakdownStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class DocumentCategory(str, Enum):
    CONTRATTO = "CONTRATTO"
    SLA = "SLA"
    CAPITOLATO = "CAPITOLATO"
    VERBALE = "VERBALE"
    ALTRO = "ALTRO"


class AuthIn(BaseModel):
    pin: str
    username: str


class SiteIn(BaseModel):
    site_code: str
    site_name: str = ""
    client: str = ""
    status: str = "ACTIVE"


class UserSiteIn(BaseModel):
    username: str
    site_code: str


class PresenceIn(BaseModel):
    username: str
    site_code: str
    presence_date: date
    presence_type: PresenceType = PresenceType.OPERATIVA
    notes: str = ""


class ForkliftIn(BaseModel):
    site_code: str
    forklift_code: str
    type: str = ""
    brand: str = ""
    model: str = ""
    status: str = "ACTIVE"


class BreakdownIn(BaseModel):
    site_code: str
    forklift_code: str
    description: str
    opened_by: str


class BreakdownCloseIn(BaseModel):
    closed_by: str
    close_note: str = ""


class ChatMessageIn(BaseModel):
    site_code: str
    sender: str
    text: str
    context_type: str = "SITE"   # SITE / BREAKDOWN / DOCUMENT (per ora usiamo SITE)
    context_id: str = ""         # per ora stringa libera (es: "BD-12")


# =========================
# DB
# =========================
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _safe_site_code(site_code: str) -> str:
    sc = (site_code or "").strip().upper()
    sc = re.sub(r"[^A-Z0-9_-]+", "_", sc)
    return sc


def _require_site_access(username: str, site_code: str):
    """
    Se l'utente è assegnato al sito in am_user_sites -> ok, altrimenti 403.
    """
    site_code = _safe_site_code(site_code)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM am_user_sites
        WHERE username=? AND site_code=?
        LIMIT 1
    """, (username, site_code))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=403,
            detail=f"Accesso negato: {username} non è assegnato al sito {site_code}"
        )


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_sites (
        site_code TEXT PRIMARY KEY,
        site_name TEXT,
        client TEXT,
        status TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_user_sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        site_code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(username, site_code)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_presence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        site_code TEXT NOT NULL,
        presence_date TEXT NOT NULL,
        presence_type TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # ✅ CARRELLI con archived
    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_forklifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_code TEXT NOT NULL,
        forklift_code TEXT NOT NULL,
        type TEXT,
        brand TEXT,
        model TEXT,
        status TEXT,
        archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(site_code, forklift_code)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_breakdowns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_code TEXT NOT NULL,
        forklift_code TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL,
        opened_at TEXT NOT NULL,
        opened_by TEXT NOT NULL,
        closed_at TEXT,
        closed_by TEXT,
        close_note TEXT,
        pdf_path TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_code TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        uploaded_by TEXT NOT NULL,
        uploaded_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS am_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_code TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        sender TEXT NOT NULL,
        text TEXT NOT NULL,
        context_type TEXT NOT NULL,
        context_id TEXT,
        attachment_path TEXT
    )
    """)

    # =========================
    # MIGRAZIONI (per DB vecchi)
    # =========================
    # Se avevi già am_forklifts senza archived, lo aggiungiamo senza rompere.
    try:
        cur.execute("ALTER TABLE am_forklifts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass

    conn.commit()
    conn.close()

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


init_db()


# =========================
# API
# =========================
@app.get("/")
def root():
    return {"status": "Area Manager attivo"}


# --- auth ponte (come Alert Hub) ---
@app.post("/auth/pin")
def auth_pin(payload: AuthIn):
    if payload.pin != PIN_UNICO:
        raise HTTPException(status_code=401, detail="PIN errato")
    return {"status": "ok", "username": payload.username}


# --- siti ---
@app.post("/sites")
def create_site(site: SiteIn):
    sc = _safe_site_code(site.site_code)
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO am_sites(site_code, site_name, client, status, created_at)
        VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM am_sites WHERE site_code=?), ?))
    """, (sc, site.site_name, site.client, site.status, sc, now_iso()))

    conn.commit()
    conn.close()
    return {"status": "ok", "site_code": sc}


@app.get("/sites")
def list_sites(username: str = Query(...)):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.site_code, s.site_name, s.client, s.status
        FROM am_sites s
        INNER JOIN am_user_sites us ON us.site_code = s.site_code
        WHERE us.username=?
        ORDER BY s.site_code ASC
    """, (username,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/sites/assign")
def assign_site(payload: UserSiteIn):
    sc = _safe_site_code(payload.site_code)
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO am_user_sites(username, site_code, created_at)
            VALUES (?, ?, ?)
        """, (payload.username, sc, now_iso()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

    return {"status": "ok", "username": payload.username, "site_code": sc}


# --- presenze AM ---
@app.post("/presences")
def add_presence(p: PresenceIn):
    sc = _safe_site_code(p.site_code)
    _require_site_access(p.username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO am_presence(username, site_code, presence_date, presence_type, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (p.username, sc, p.presence_date.isoformat(), p.presence_type.value, p.notes, now_iso()))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "presence_id": pid}


@app.get("/presences")
def list_presences(
    username: str = Query(...),
    site_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    if site_code:
        sc = _safe_site_code(site_code)
        _require_site_access(username, sc)

    q = "SELECT * FROM am_presence WHERE username=?"
    params = [username]

    if site_code:
        q += " AND site_code=?"
        params.append(_safe_site_code(site_code))
    if date_from:
        q += " AND presence_date>=?"
        params.append(date_from)
    if date_to:
        q += " AND presence_date<=?"
        params.append(date_to)

    q += " ORDER BY presence_date DESC, id DESC LIMIT 500"

    conn = db()
    cur = conn.cursor()
    cur.execute(q, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# =========================
# CARRELLI (con ARCHIVIO)
# =========================
@app.post("/forklifts")
def add_forklift(f: ForkliftIn):
    sc = _safe_site_code(f.site_code)
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO am_forklifts(
            site_code, forklift_code, type, brand, model, status, archived, created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            COALESCE((SELECT archived FROM am_forklifts WHERE site_code=? AND forklift_code=?), 0),
            COALESCE((SELECT created_at FROM am_forklifts WHERE site_code=? AND forklift_code=?), ?)
        )
    """, (
        sc, f.forklift_code, f.type, f.brand, f.model, f.status,
        sc, f.forklift_code,
        sc, f.forklift_code, now_iso()
    ))

    conn.commit()
    conn.close()
    return {"status": "ok", "site_code": sc, "forklift_code": f.forklift_code}


@app.get("/forklifts")
def list_forklifts(
    username: str = Query(...),
    site_code: str = Query(...),
    archived: int = Query(0, ge=0, le=1)
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM am_forklifts
        WHERE site_code=? AND archived=?
        ORDER BY forklift_code ASC
        LIMIT 5000
    """, (sc, archived))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/forklifts/{forklift_id}/archive")
def archive_forklift(
    forklift_id: int,
    username: str = Query(...),
    site_code: str = Query(...)
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE am_forklifts
        SET archived=1
        WHERE id=? AND site_code=?
    """, (forklift_id, sc))

    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Carrello non trovato (o non appartiene al sito)")

    conn.commit()
    conn.close()
    return {"status": "ok", "forklift_id": forklift_id, "archived": 1}


# --- guasti ---
@app.post("/breakdowns")
def open_breakdown(b: BreakdownIn):
    sc = _safe_site_code(b.site_code)
    _require_site_access(b.opened_by, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO am_breakdowns(site_code, forklift_code, description, status, opened_at, opened_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (sc, b.forklift_code, b.description, BreakdownStatus.OPEN.value, now_iso(), b.opened_by))
    bid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "breakdown_id": bid}


@app.get("/breakdowns")
def list_breakdowns(username: str = Query(...), site_code: str = Query(...), include_closed: bool = False):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    q = "SELECT * FROM am_breakdowns WHERE site_code=?"
    params = [sc]
    if not include_closed:
        q += " AND status<>?"
        params.append(BreakdownStatus.CLOSED.value)
    q += " ORDER BY id DESC LIMIT 500"

    conn = db()
    cur = conn.cursor()
    cur.execute(q, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/breakdowns/{breakdown_id}/close")
def close_breakdown(breakdown_id: int, payload: BreakdownCloseIn, site_code: str = Query(...)):
    sc = _safe_site_code(site_code)
    _require_site_access(payload.closed_by, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE am_breakdowns
        SET status=?, closed_at=?, closed_by=?, close_note=?
        WHERE id=? AND site_code=?
    """, (BreakdownStatus.CLOSED.value, now_iso(), payload.closed_by, payload.close_note, breakdown_id, sc))
    conn.commit()
    conn.close()
    return {"status": "ok", "breakdown_id": breakdown_id}


@app.post("/breakdowns/{breakdown_id}/upload-pdf")
def upload_breakdown_pdf(
    breakdown_id: int,
    username: str = Query(...),
    site_code: str = Query(...),
    file: UploadFile = File(...),
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Carica un file PDF")

    target_path = _upload_storage_rel(sc, "breakdowns", f"BD_{breakdown_id}_{file.filename}")
    stored_ref = get_file_storage().save_upload(target_path, file, content_type="application/pdf")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE am_breakdowns
        SET pdf_path=?
        WHERE id=? AND site_code=?
    """, (stored_ref, breakdown_id, sc))
    conn.commit()
    conn.close()

    return {"status": "ok", "breakdown_id": breakdown_id, "pdf_path": stored_ref}


# --- documenti impianto ---
@app.post("/documents/upload")
def upload_site_document(
    username: str = Query(...),
    site_code: str = Query(...),
    category: DocumentCategory = Query(DocumentCategory.ALTRO),
    title: str = Query("Documento"),
    file: UploadFile = File(...),
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Carica un file PDF")

    target_path = _upload_storage_rel(sc, "documents", f"{category.value}_{file.filename}")
    stored_ref = get_file_storage().save_upload(target_path, file, content_type="application/pdf")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO am_documents(site_code, category, title, file_path, uploaded_by, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (sc, category.value, title, stored_ref, username, now_iso()))
    did = cur.lastrowid
    conn.commit()
    conn.close()

    return {"status": "ok", "document_id": did, "file_path": stored_ref}


@app.get("/documents")
def list_documents(username: str = Query(...), site_code: str = Query(...)):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM am_documents
        WHERE site_code=?
        ORDER BY id DESC LIMIT 500
    """, (sc,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# --- chat (semplice) ---
@app.post("/chat/messages")
def chat_send(msg: ChatMessageIn):
    sc = _safe_site_code(msg.site_code)
    _require_site_access(msg.sender, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO am_chat_messages(site_code, sent_at, sender, text, context_type, context_id, attachment_path)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
    """, (sc, now_iso(), msg.sender, msg.text, msg.context_type, msg.context_id))
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "message_id": mid}


@app.get("/chat/messages")
def chat_list(
    username: str = Query(...),
    site_code: str = Query(...),
    limit: int = Query(200, ge=1, le=1000),
    context_type: str = Query("SITE"),
    context_id: str = Query(""),
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    q = """
        SELECT * FROM am_chat_messages
        WHERE site_code=? AND context_type=? AND IFNULL(context_id,'')=?
        ORDER BY id DESC
        LIMIT ?
    """
    conn = db()
    cur = conn.cursor()
    cur.execute(q, (sc, context_type, context_id, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return list(reversed(rows))
@app.get("/files/breakdown/{breakdown_id}")
def get_breakdown_pdf(
    breakdown_id: int,
    username: str = Query(...),
    site_code: str = Query(...)
):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT pdf_path
        FROM am_breakdowns
        WHERE id=? AND site_code=?
    """, (breakdown_id, sc))
    row = cur.fetchone()
    conn.close()

    if not row or not row["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF non trovato")

    storage_ref = row["pdf_path"]

    if not get_file_storage().exists(storage_ref):
        raise HTTPException(status_code=404, detail="File non presente su disco")

    return _file_response(storage_ref)
# =========================
# MIGRAZIONI SICURE (archived)
# =========================
def _ensure_archived_columns():
    conn = db()
    cur = conn.cursor()

    def add_col(table: str):
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # colonna già presente

    add_col("am_presence")
    add_col("am_documents")
    add_col("am_breakdowns")
    add_col("am_forklifts")

    conn.commit()
    conn.close()

_ensure_archived_columns()


# =========================
# PRESENCES - ARCHIVIA / ELIMINA
# =========================
@app.post("/presences/{presence_id}/archive")
def archive_presence(presence_id: int, username: str = Query(...), site_code: str = Query(...)):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE am_presence
        SET archived=1
        WHERE id=? AND username=? AND site_code=?
    """, (presence_id, username, sc))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata (o non appartiene a questo sito/utente)")
    return {"status": "ok", "presence_id": presence_id, "archived": 1}


@app.delete("/presences/{presence_id}")
def delete_presence(presence_id: int, username: str = Query(...), site_code: str = Query(...)):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM am_presence
        WHERE id=? AND username=? AND site_code=?
    """, (presence_id, username, sc))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata (o non appartiene a questo sito/utente)")
    return {"status": "ok", "presence_id": presence_id, "deleted": True}


# Modifica list_presences: per default NON mostra archived
# (aggiungi questi parametri e filtri nella tua list_presences)
# include_archived: bool = False

# =========================
# DOCUMENTS - ARCHIVIA / ELIMINA (con cancellazione file)
# =========================
@app.post("/documents/{document_id}/archive")
def archive_document(document_id: int, username: str = Query(...), site_code: str = Query(...)):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE am_documents
        SET archived=1
        WHERE id=? AND site_code=?
    """, (document_id, sc))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return {"status": "ok", "document_id": document_id, "archived": 1}


@app.delete("/documents/{document_id}")
def delete_document(document_id: int, username: str = Query(...), site_code: str = Query(...), delete_file: bool = Query(True)):
    sc = _safe_site_code(site_code)
    _require_site_access(username, sc)

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT file_path FROM am_documents WHERE id=? AND site_code=?", (document_id, sc))
    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Documento non trovato")

    file_path = row["file_path"]

    cur.execute("DELETE FROM am_documents WHERE id=? AND site_code=?", (document_id, sc))
    conn.commit()
    conn.close()

    # se vuoi: cancella anche il file fisico
    if delete_file and file_path:
        try:
            get_file_storage().delete(file_path)
        except Exception:
            pass

    return {"status": "ok", "document_id": document_id, "deleted": True}

