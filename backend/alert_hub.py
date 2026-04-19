# alert_hub.py
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import sqlite3

from config import ALERT_HUB_DB_PATH, ALERT_HUB_PIN

app = FastAPI(title="Alert Hub - Control Room")

PIN_UNICO = ALERT_HUB_PIN
DB_PATH = ALERT_HUB_DB_PATH


# =========================
# ENUM UI
# =========================
class TipoAlert(str, Enum):
    NEAR_MISS = "NEAR_MISS"
    TICKET = "TICKET"


class Gravita(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class StatoAlert(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


# =========================
# MODELLI INPUT
# =========================
class AlertIn(BaseModel):
    warehouse: str
    tipo: TipoAlert
    gravita: Gravita
    descrizione: str


class MessageIn(BaseModel):
    mittente: str
    testo: str


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


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse TEXT NOT NULL,
        tipo TEXT NOT NULL,
        gravita TEXT NOT NULL,
        descrizione TEXT NOT NULL,
        data TEXT NOT NULL,
        stato TEXT NOT NULL,
        preso_in_carico_da TEXT,
        preso_in_carico_il TEXT,
        risolto_da TEXT,
        risolto_il TEXT,
        nota_risoluzione TEXT,
        archived INTEGER NOT NULL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS alert_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id INTEGER NOT NULL,
        data TEXT NOT NULL,
        mittente TEXT NOT NULL,
        testo TEXT NOT NULL,
        FOREIGN KEY(alert_id) REFERENCES alerts(id)
    )
    """)

    # migrazione soft (se DB vecchio senza archived)
    try:
        cur.execute("ALTER TABLE alerts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


init_db()


# =========================
# UTILS
# =========================
def get_alert_or_404(alert_id: int) -> Dict[str, Any]:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    return dict(row)


# =========================
# API
# =========================
@app.get("/")
def root():
    return {"status": "Alert Hub attivo"}


@app.post("/auth/pin")
def auth_pin(pin: str):
    if pin != PIN_UNICO:
        raise HTTPException(status_code=401, detail="PIN errato")
    return {"status": "ok"}


@app.post("/alerts")
def crea_alert(alert: AlertIn):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO alerts
        (warehouse, tipo, gravita, descrizione, data, stato,
         preso_in_carico_da, preso_in_carico_il,
         risolto_da, risolto_il, nota_risoluzione, archived)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 0)
    """, (
        alert.warehouse,
        alert.tipo.value,
        alert.gravita.value,
        alert.descrizione,
        now_iso(),
        StatoAlert.OPEN.value
    ))
    alert_id = cur.lastrowid

    cur.execute("""
        INSERT INTO alert_messages (alert_id, data, mittente, testo)
        VALUES (?, ?, ?, ?)
    """, (alert_id, now_iso(), "SYSTEM", f"Creato {alert.tipo.value} - gravità {alert.gravita.value}"))

    conn.commit()
    conn.close()
    return get_alert_or_404(alert_id)


@app.get("/alerts")
def lista_alert(
    # archived=0 => attivi; archived=1 => archivio
    archived: int = Query(0, ge=0, le=1),
    stato: Optional[StatoAlert] = None,
    warehouse: Optional[str] = None,
    tipo: Optional[TipoAlert] = None,
    # per default: in "attivi" non mostro i RESOLVED
    include_resolved: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    q = "SELECT * FROM alerts WHERE archived=?"
    params = [archived]

    if archived == 0 and not include_resolved:
        q += " AND stato<>?"
        params.append(StatoAlert.RESOLVED.value)

    if stato:
        q += " AND stato=?"
        params.append(stato.value)
    if warehouse:
        q += " AND warehouse=?"
        params.append(warehouse)
    if tipo:
        q += " AND tipo=?"
        params.append(tipo.value)

    q += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = db()
    cur = conn.cursor()
    cur.execute(q, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, responsabile: str):
    a = get_alert_or_404(alert_id)
    if a["stato"] == StatoAlert.RESOLVED.value:
        raise HTTPException(status_code=400, detail="Alert già risolto")
    if int(a.get("archived", 0)) == 1:
        raise HTTPException(status_code=400, detail="Alert archiviato: non puoi prenderlo in carico")

    conn = db()
    cur = conn.cursor()

    # ✅ FIX: qui prima avevi UPDATE sbagliato (metteva risolto_* e archived=1)
    cur.execute("""
        UPDATE alerts
        SET stato=?, preso_in_carico_da=?, preso_in_carico_il=?
        WHERE id=?
    """, (StatoAlert.IN_PROGRESS.value, responsabile, now_iso(), alert_id))

    cur.execute("""
        INSERT INTO alert_messages (alert_id, data, mittente, testo)
        VALUES (?, ?, ?, ?)
    """, (alert_id, now_iso(), "CONTROL_ROOM", f"Preso in carico da: {responsabile}"))

    conn.commit()
    conn.close()
    return get_alert_or_404(alert_id)


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, responsabile: str, nota: str = ""):
    _ = get_alert_or_404(alert_id)

    conn = db()
    cur = conn.cursor()

    # Risolvo + Archivio (sparisce dalla Control Room attiva)
    cur.execute("""
        UPDATE alerts
        SET stato=?, risolto_da=?, risolto_il=?, nota_risoluzione=?, archived=1
        WHERE id=?
    """, (StatoAlert.RESOLVED.value, responsabile, now_iso(), nota, alert_id))

    testo_msg = f"Risolto da: {responsabile}."
    if nota.strip():
        testo_msg += f" Nota: {nota.strip()}"

    cur.execute("""
        INSERT INTO alert_messages (alert_id, data, mittente, testo)
        VALUES (?, ?, ?, ?)
    """, (alert_id, now_iso(), "CONTROL_ROOM", testo_msg))

    conn.commit()
    conn.close()
    return get_alert_or_404(alert_id)


@app.post("/alerts/{alert_id}/archive")
def archive_alert(alert_id: int, responsabile: str, nota: str = ""):
    _ = get_alert_or_404(alert_id)

    conn = db()
    cur = conn.cursor()

    cur.execute("UPDATE alerts SET archived=1 WHERE id=?", (alert_id,))

    testo_msg = f"Archiviato da: {responsabile}."
    if nota.strip():
        testo_msg += f" Nota: {nota.strip()}"

    cur.execute("""
        INSERT INTO alert_messages (alert_id, data, mittente, testo)
        VALUES (?, ?, ?, ?)
    """, (alert_id, now_iso(), "CONTROL_ROOM", testo_msg))

    conn.commit()
    conn.close()
    return {"status": "ok", "alert_id": alert_id}


@app.post("/alerts/{alert_id}/messages")
def add_message(alert_id: int, msg: MessageIn):
    _ = get_alert_or_404(alert_id)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO alert_messages (alert_id, data, mittente, testo)
        VALUES (?, ?, ?, ?)
    """, (alert_id, now_iso(), msg.mittente, msg.testo))

    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/alerts/{alert_id}/messages")
def get_messages(alert_id: int):
    _ = get_alert_or_404(alert_id)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, alert_id, data, mittente, testo
        FROM alert_messages
        WHERE alert_id=?
        ORDER BY id ASC
    """, (alert_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
