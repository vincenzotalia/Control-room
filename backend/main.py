# main.py
from fastapi import FastAPI, Query, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, time as time_class
from typing import Optional, List, Dict, Any
import threading
from pathlib import Path
import math
import re

import pandas as pd
import numpy as np  # ✅ NEW (per delta_pct e gestione inf)
from pydantic import BaseModel

from agora_analysis import run_agora_analysis, td_to_hours
from config import get_cors_origins
from storage import get_file_storage

# ✅ pallet check (modulo)
from pallet_check_service import (
    get_pallet_cache,
    refresh_pallet_cache,
)

# IMPORT Alert Hub (sub-app)
from alert_hub import app as alert_hub_app

# ✅ IMPORT Area Manager (sub-app)
from area_manager import app as area_manager_app


# ==========================================================
# ✅ APP DEVE ESSERE GLOBALE (colonna 0) altrimenti uvicorn non la vede
# ==========================================================
app = FastAPI(title="Warehouse Control Room API")

# ✅ monta sub-app UNA SOLA VOLTA
app.mount("/alert-hub", alert_hub_app)
app.mount("/area-manager", area_manager_app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# PATH INPUT FILE
# ============================
PALLET_FILE_NAME = "dati_pallet.xlsx"
CARRELLISTI_FILE_NAME = "carrellisti.xlsm"
DATA_INPUT_STORAGE_PREFIX = "data/input"
DATA_HISTORY_STORAGE_PREFIX = "data/history"

ALLOWED_EXT = {".csv", ".xlsx", ".xlsm", ".xls"}

# ============================
# ✅ PATH STORICO (NUOVO)
# ============================
HISTORY_FILE_NAME = "report_storico.xlsx"


def _storage_rel(*parts: str) -> str:
    return "/".join(str(part).strip("/\\") for part in parts if str(part).strip("/\\"))


def _input_storage_rel(file_name: str) -> str:
    return _storage_rel(DATA_INPUT_STORAGE_PREFIX, file_name)


def _history_storage_rel() -> str:
    return _storage_rel(DATA_HISTORY_STORAGE_PREFIX, HISTORY_FILE_NAME)


def _input_local_path(file_name: str) -> Path:
    return get_file_storage().ensure_local_copy(_input_storage_rel(file_name))


def _history_local_path() -> Path:
    return get_file_storage().ensure_local_copy(_history_storage_rel())


def _cleanup_picking_files() -> None:
    """
    Cancella i vecchi file di picking, ma NON tocca carrellisti.xlsm e NON tocca dati_pallet.xlsx.
    """
    storage = get_file_storage()
    for rel_path in storage.list_relative(DATA_INPUT_STORAGE_PREFIX):
        p = Path(rel_path)
        if p.name.lower() in {CARRELLISTI_FILE_NAME.lower(), PALLET_FILE_NAME.lower()}:
            continue
        if p.suffix.lower() in ALLOWED_EXT:
            storage.delete(rel_path)


# ============================
# CACHE IN MEMORIA (con lock)
# ============================
_analysis_cache = None
_cache_lock = threading.Lock()


def get_analysis():
    """
    Lazy-load: calcola l'analisi solo alla prima chiamata.
    """
    global _analysis_cache
    if _analysis_cache is None:
        with _cache_lock:
            if _analysis_cache is None:
                _analysis_cache = run_agora_analysis()
    return _analysis_cache


def refresh_analysis():
    """
    Forza ricalcolo e aggiorna la cache.
    """
    global _analysis_cache
    with _cache_lock:
        _analysis_cache = run_agora_analysis()
    return _analysis_cache


# ============================
# HELPERS
# ============================
def _parse_time_str(s: Optional[str]) -> Optional[time_class]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%H:%M").time()
    except Exception:
        return None


def _time_in_range_cross_midnight(t: time_class, start_t: time_class, end_t: time_class) -> bool:
    if start_t is None or end_t is None:
        return True
    if end_t >= start_t:
        return (t >= start_t) and (t <= end_t)
    return (t >= start_t) or (t <= end_t)


def _hhmm_from_bucket(bucket_iso: str) -> str:
    try:
        return bucket_iso[11:16]
    except Exception:
        return str(bucket_iso)


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _target_from_colli_lista(colli_lista: float) -> float:
    c = _safe_float(colli_lista, 0.0)
    if c <= 60:
        return 115.0
    elif c <= 100:
        return 130.0
    elif c <= 160:
        return 145.0
    elif c <= 220:
        return 160.0
    else:
        return 175.0


def _expected_by_bucket_from_lists(df_bucketed: pd.DataFrame) -> Dict[pd.Timestamp, float]:
    if df_bucketed.empty or "Lista" not in df_bucketed.columns or "bucket" not in df_bucketed.columns:
        return {}

    df_lists = (
        df_bucketed.groupby("Lista", as_index=False)
        .agg(colli_lista=("Colli", "sum"))
    )
    if df_lists.empty:
        return {}

    df_lists["target_lista"] = df_lists["colli_lista"].apply(_target_from_colli_lista)
    target_map: Dict[Any, float] = {row["Lista"]: float(row["target_lista"]) for _, row in df_lists.iterrows()}

    gb = (
        df_bucketed.groupby(["bucket", "Lista"], as_index=False)
        .agg(colli=("Colli", "sum"))
    )
    if gb.empty:
        return {}

    expected_by_bucket: Dict[pd.Timestamp, float] = {}
    for b, part in gb.groupby("bucket"):
        num = 0.0
        den = 0.0
        for _, r in part.iterrows():
            lst = r["Lista"]
            colli = _safe_float(r["colli"], 0.0)
            tgt = _safe_float(target_map.get(lst, 0.0), 0.0)
            if colli <= 0 or tgt <= 0:
                continue
            num += colli
            den += (colli / tgt)

        expected_by_bucket[b] = (num / den) if den > 0 else 0.0

    return expected_by_bucket


def _clean_json(obj):
    """
    Converte NaN/Inf -> None, e gestisce ricorsivamente dict/list.
    """
    if obj is None:
        return None

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_clean_json(x) for x in obj]

    return obj


# ============================
# ✅ STORICO: lettura robusta report_storico.xlsx (NUOVO)
# ============================
def _read_history_df() -> pd.DataFrame:
    """
    Legge backend/data/history/report_storico.xlsx.
    Cerca prima il foglio "ControlRoom_Dettaglio" (quello del tuo report),
    poi "history", altrimenti scansiona i fogli finché trova colonne richieste:
      Dimensione | Bucket | mean_m
    (opzionale) Data
    """
    storage = get_file_storage()
    history_ref = _history_storage_rel()
    if not storage.exists(history_ref):
        return pd.DataFrame()
    p = _history_local_path()

    try:
        xls = pd.ExcelFile(p)

        # 1) preferito: ControlRoom_Dettaglio
        preferred = None
        for s in xls.sheet_names:
            if str(s).strip().lower() == "controlroom_dettaglio":
                preferred = s
                break

        # 2) fallback: history
        if preferred is None:
            for s in xls.sheet_names:
                if str(s).strip().lower() == "history":
                    preferred = s
                    break

        # 3) se ancora nulla: prendo il primo, poi provo a scansionare
        candidate_sheets = []
        if preferred is not None:
            candidate_sheets.append(preferred)
        candidate_sheets += [s for s in xls.sheet_names if s not in candidate_sheets]

        df = None
        for sheet in candidate_sheets:
            tmp = pd.read_excel(p, sheet_name=sheet)
            if tmp is None or tmp.empty:
                continue

            tmp.columns = [str(c).strip() for c in tmp.columns]
            needed = {"Dimensione", "Bucket", "mean_m"}
            if needed.issubset(set(tmp.columns)):
                df = tmp
                break

        if df is None or df.empty:
            return pd.DataFrame()

        # normalizza
        df.columns = [str(c).strip() for c in df.columns]
        df["Dimensione"] = df["Dimensione"].astype(str).str.strip().str.upper()
        df["Bucket"] = df["Bucket"].astype(str).str.strip().str.upper()
        df["mean_m"] = pd.to_numeric(df["mean_m"], errors="coerce")

        if "Data" in df.columns:
            df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
            df["Data"] = df["Data_dt"].dt.date

        df = df.dropna(subset=["mean_m"])
        return df

    except Exception:
        return pd.DataFrame()

# ============================
# ✅ PALLET DEMAND ENGINE (IN MAIN.PY)
# ============================
_demand_cache: Dict[int, Dict[str, Any]] = {}
_demand_lock = threading.Lock()

MOV_ABB = "RIPRIST.TOT DA SCORTA A PRESA"


def _norm_time_obj(x) -> Optional[time_class]:
    """Accetta datetime.time, Timestamp, '06.00.01', '06:00:01', '06:00'."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    if isinstance(x, (pd.Timestamp, datetime)):
        return x.time()
    if isinstance(x, time_class):
        return x

    s = str(x).strip()
    if not s:
        return None

    s = s.replace(".", ":")
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return time_class(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return time_class(int(parts[0]), int(parts[1]), 0)
    except Exception:
        return None
    return None


def _floor_slot_str(t: Optional[time_class], window_min: int) -> Optional[str]:
    """Ritorna 'HH:MM' con floor su window_min."""
    if t is None:
        return None
    m = int(t.hour) * 60 + int(t.minute)
    w = int(window_min)
    flo = (m // w) * w
    hh = flo // 60
    mm = flo % 60
    return f"{hh:02d}:{mm:02d}"


def _pallet_num_from_supporto(val) -> Optional[int]:
    """Estrae ultime 5 cifre dal SUPPORTO (es 615/2026/0064775 -> 64775)."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    s = str(val)
    m = re.search(r"(\d{5})\s*$", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _as_corsia_num(series: pd.Series) -> pd.Series:
    """Converte corsia a numerico (KAR -> NaN), poi tiene solo 13..75."""
    s = pd.to_numeric(series, errors="coerce")
    s = s.where(s.between(13, 75))
    return s


def _compute_pallet_demand_cache(scarico_path: Path, car_path: Path, window_min: int) -> Dict[str, Any]:
    # --- leggi scarico
    xls_s = pd.ExcelFile(scarico_path)  # ✅ FIX refuso
    sheet_s = (xls_s.sheet_names[0] if xls_s.sheet_names else "scarico")
    if "scarico" in [x.lower() for x in xls_s.sheet_names]:
        for n in xls_s.sheet_names:
            if n.strip().lower() == "scarico":
                sheet_s = n
                break

    df_s = pd.read_excel(scarico_path, sheet_name=sheet_s)

    # --- leggi carrellisti
    xls_c = pd.ExcelFile(car_path)
    sheet_c = xls_c.sheet_names[0]
    df_c = pd.read_excel(car_path, sheet_name=sheet_c)

    # colonne base
    if "SUPPORTO" not in df_s.columns or "ORA INIZIO CONSEGNA" not in df_s.columns:
        return _clean_json({
            "status": "error",
            "message": "Nel file scarico mancano colonne SUPPORTO / ORA INIZIO CONSEGNA",
            "meta": {"sheet_scarico": sheet_s, "sheet_carrellisti": sheet_c},
            "slots": [],
            "corsie_all": list(range(75, 12, -1)),
            "by_slot": {},
            "top_by_slot": {},
            "non_stok": [],
        })

    if ("Pallet:Numero" not in df_c.columns) or ("Cons.Ora" not in df_c.columns) or ("Tp Movimento" not in df_c.columns):
        return _clean_json({
            "status": "error",
            "message": "Nel file carrellisti mancano colonne Pallet:Numero / Cons.Ora / Tp Movimento",
            "meta": {"sheet_scarico": sheet_s, "sheet_carrellisti": sheet_c},
            "slots": [],
            "corsie_all": list(range(75, 12, -1)),
            "by_slot": {},
            "top_by_slot": {},
            "non_stok": [],
        })

    # --- normalizza scarico
    df_s = df_s.copy()
    df_s["PALLET_NUM"] = df_s["SUPPORTO"].apply(_pallet_num_from_supporto)
    df_s["ORA_T"] = df_s["ORA INIZIO CONSEGNA"].apply(_norm_time_obj)
    df_s["SLOT"] = df_s["ORA_T"].apply(lambda t: _floor_slot_str(t, window_min))

    # --- normalizza carrellisti
    df_c = df_c.copy()
    df_c["PALLET_NUM"] = pd.to_numeric(df_c["Pallet:Numero"], errors="coerce")
    df_c["CONS_T"] = df_c["Cons.Ora"].apply(_norm_time_obj)
    df_c["SLOT"] = df_c["CONS_T"].apply(lambda t: _floor_slot_str(t, window_min))

    df_c["ARR_CORSIA_RAW"] = df_c.get("ARR:Corsia")
    df_c["PAR_CORSIA_RAW"] = df_c.get("PAR:Corsia")
    df_c["ARR_CORSIA_NUM"] = _as_corsia_num(df_c.get("ARR:Corsia"))
    df_c["PAR_CORSIA_NUM"] = _as_corsia_num(df_c.get("PAR:Corsia"))

    df_lookup = (
        df_c.dropna(subset=["PALLET_NUM"])
            .drop_duplicates(subset=["PALLET_NUM"])
            .set_index("PALLET_NUM")
    )

    def _has_any_stock(pn) -> bool:
        if pn is None or (isinstance(pn, float) and pd.isna(pn)):
            return False
        try:
            key = float(pn)
        except Exception:
            return False
        return key in df_lookup.index

    def _match_arr_corsia_raw(pn):
        if pn is None or (isinstance(pn, float) and pd.isna(pn)):
            return None
        try:
            key = float(pn)
        except Exception:
            return None
        if key not in df_lookup.index:
            return None
        row = df_lookup.loc[key]
        return row.get("ARR_CORSIA_RAW", None)

    def _match_arr_corsia_num(pn):
        if pn is None or (isinstance(pn, float) and pd.isna(pn)):
            return None
        try:
            key = float(pn)
        except Exception:
            return None
        if key not in df_lookup.index:
            return None
        row = df_lookup.loc[key]
        return row.get("ARR_CORSIA_NUM", None)

    df_s["ARR_CORSIA_RAW"] = df_s["PALLET_NUM"].apply(_match_arr_corsia_raw)
    df_s["ARR_CORSIA_NUM"] = df_s["PALLET_NUM"].apply(_match_arr_corsia_num)

    df_s["STOCCATO"] = df_s["PALLET_NUM"].apply(lambda pn: "STOK" if _has_any_stock(pn) else "NON STOK")

    non_stok_cols = []
    for c in ["SUPPORTO", "ORA INIZIO CONSEGNA", "PALLET_NUM", "ARTICOLO", "DESCRIZIONE ARTICOLO"]:
        if c in df_s.columns:
            non_stok_cols.append(c)

    df_non = df_s[df_s["STOCCATO"] == "NON STOK"].copy()
    if "SUPPORTO" in df_non.columns:
        df_non = df_non.drop_duplicates(subset=["SUPPORTO"])
    elif "PALLET_NUM" in df_non.columns:
        df_non = df_non.drop_duplicates(subset=["PALLET_NUM"])

    df_non = df_non[non_stok_cols].copy()
    non_stok = _clean_json(df_non.to_dict(orient="records"))

    df_in = df_s.dropna(subset=["SLOT", "ARR_CORSIA_NUM"]).copy()
    df_in["ARR_CORSIA_NUM"] = pd.to_numeric(df_in["ARR_CORSIA_NUM"], errors="coerce")
    df_in = df_in[df_in["ARR_CORSIA_NUM"].between(13, 75)]

    if "SUPPORTO" in df_in.columns:
        df_in["SUPPORTO_STR"] = df_in["SUPPORTO"].astype(str).str.strip()
    else:
        df_in["SUPPORTO_STR"] = None

    inbound = (
        df_in.groupby(["SLOT", "ARR_CORSIA_NUM"], as_index=False)
             .agg(inbound=("SUPPORTO_STR", "nunique"))
    )

    dff = df_c.copy()
    dff["TP_MOV_UP"] = dff["Tp Movimento"].astype(str).str.strip().str.upper()
    df_rip = dff[dff["TP_MOV_UP"] == MOV_ABB.upper()].copy()

    abb_arr = (
        df_rip.dropna(subset=["SLOT", "ARR_CORSIA_NUM"])
              .groupby(["SLOT", "ARR_CORSIA_NUM"], as_index=False)
              .agg(abb_arr=("PALLET_NUM", "nunique"))
    )

    abb_par = (
        df_rip.dropna(subset=["SLOT", "PAR_CORSIA_NUM"])
              .groupby(["SLOT", "PAR_CORSIA_NUM"], as_index=False)
              .agg(abb_par=("PALLET_NUM", "nunique"))
    )

    slots = sorted(set(df_s["SLOT"].dropna().unique().tolist()) | set(df_c["SLOT"].dropna().unique().tolist()))
    corsie_all = list(range(75, 12, -1))

    by_slot: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for s in slots:
        by_slot[s] = {c: {"corsia": c, "inbound": 0, "abb_arr": 0, "abb_par": 0, "mix": 0} for c in corsie_all}

    for _, r in inbound.iterrows():
        s = r["SLOT"]
        c = int(r["ARR_CORSIA_NUM"])
        if s in by_slot and c in by_slot[s]:
            by_slot[s][c]["inbound"] = int(r["inbound"])

    for _, r in abb_arr.iterrows():
        s = r["SLOT"]
        c = int(r["ARR_CORSIA_NUM"])
        if s in by_slot and c in by_slot[s]:
            by_slot[s][c]["abb_arr"] = int(r["abb_arr"])

    for _, r in abb_par.iterrows():
        s = r["SLOT"]
        c = int(r["PAR_CORSIA_NUM"])
        if s in by_slot and c in by_slot[s]:
            by_slot[s][c]["abb_par"] = int(r["abb_par"])

    for s in slots:
        for c in corsie_all:
            v = by_slot[s][c]
            v["mix"] = int(v["inbound"]) + int(v["abb_arr"])

    def _top_for(slot_key: str, metric: str, k: int = 10):
        arr = list(by_slot.get(slot_key, {}).values())
        arr = sorted(arr, key=lambda x: x.get(metric, 0), reverse=True)
        arr = [x for x in arr if (x.get(metric, 0) or 0) > 0][:k]
        return arr

    top_by_slot: Dict[str, Dict[str, Any]] = {}
    for s in slots:
        top_by_slot[s] = {
            "inbound": _top_for(s, "inbound", 10),
            "abb_arr": _top_for(s, "abb_arr", 10),
            "abb_par": _top_for(s, "abb_par", 10),
            "mix": _top_for(s, "mix", 10),
        }

    return _clean_json({
        "status": "ok",
        "meta": {
            "sheet_scarico": sheet_s,
            "sheet_carrellisti": sheet_c,
            "rows_scarico": int(len(df_s)),
            "rows_carrellisti": int(len(df_c)),
            "window_min": int(window_min),
        },
        "slots": slots,
        "corsie_all": corsie_all,
        "by_slot": by_slot,
        "top_by_slot": top_by_slot,
        "non_stok": non_stok,
    })


def get_pallet_demand_cache(scarico_path: Path, car_path: Path, window_min: int) -> Dict[str, Any]:
    key = int(window_min)
    with _demand_lock:
        if key not in _demand_cache:
            _demand_cache[key] = _compute_pallet_demand_cache(scarico_path, car_path, window_min=key)
        return _demand_cache[key]


def refresh_pallet_demand_cache(scarico_path: Path, car_path: Path, window_min: int) -> Dict[str, Any]:
    key = int(window_min)
    with _demand_lock:
        _demand_cache[key] = _compute_pallet_demand_cache(scarico_path, car_path, window_min=key)
        return _demand_cache[key]


def build_demand_slot_payload(cache: Dict[str, Any], slot: Optional[str], view: str) -> Dict[str, Any]:
    """
    Costruisce payload coerente per:
    - slot normale (AUTO o HH:MM)
    - slot = ALL (totale giornata)
    NOTA: top è calcolata SEMPRE sullo stesso dataset di corsie (evita mismatch mappa/top).
    """
    if not cache or cache.get("status") != "ok":
        return cache or {"status": "error", "message": "Cache vuota"}

    slots = cache.get("slots") or []
    corsie_all = cache.get("corsie_all") or list(range(75, 12, -1))
    by_slot = cache.get("by_slot") or {}

    slot_norm = None
    if slot:
        s = str(slot).strip()
        if s.upper() == "ALL":
            slot_norm = "ALL"
        else:
            slot_norm = s[:5] if len(s) >= 5 else s

    def _top_from_list(arr: list, metric: str, k: int = 10):
        arr2 = sorted(arr, key=lambda x: (x.get(metric, 0) or 0), reverse=True)
        arr2 = [x for x in arr2 if (x.get(metric, 0) or 0) > 0][:k]
        return arr2

    if not slots:
        empty_corsie = [{"corsia": c, "inbound": 0, "abb_arr": 0, "abb_par": 0, "mix": 0} for c in corsie_all]
        return _clean_json({
            "status": "ok",
            "slot": None,
            "slots": ["ALL"],
            "view": view,
            "corsie": empty_corsie,
            "top": {"inbound": [], "abb_arr": [], "abb_par": [], "mix": []},
            "non_stok": cache.get("non_stok") or [],
            "meta": cache.get("meta") or {},
        })

    if slot_norm == "ALL":
        agg = {c: {"corsia": c, "inbound": 0, "abb_arr": 0, "abb_par": 0, "mix": 0} for c in corsie_all}

        for s in slots:
            corsie_map = by_slot.get(s) or {}
            for c in corsie_all:
                v = corsie_map.get(c) or {}
                agg[c]["inbound"] += int(v.get("inbound", 0) or 0)
                agg[c]["abb_arr"] += int(v.get("abb_arr", 0) or 0)
                agg[c]["abb_par"] += int(v.get("abb_par", 0) or 0)

        for c in corsie_all:
            agg[c]["mix"] = int(agg[c]["inbound"]) + int(agg[c]["abb_arr"])

        corsie = list(agg.values())

        top = {
            "inbound": _top_from_list(corsie, "inbound", 10),
            "abb_arr": _top_from_list(corsie, "abb_arr", 10),
            "abb_par": _top_from_list(corsie, "abb_par", 10),
            "mix": _top_from_list(corsie, "mix", 10),
        }

        return _clean_json({
            "status": "ok",
            "slot": "ALL",
            "slots": ["ALL"] + slots,
            "view": view,
            "corsie": corsie,
            "top": top,
            "non_stok": cache.get("non_stok") or [],
            "meta": cache.get("meta") or {},
        })

    slot_pick = slot_norm if (slot_norm and slot_norm in slots) else slots[-1]

    corsie_map = (by_slot.get(slot_pick) or {})
    corsie = list(corsie_map.values()) if corsie_map else [
        {"corsia": c, "inbound": 0, "abb_arr": 0, "abb_par": 0, "mix": 0} for c in corsie_all
    ]

    top = {
        "inbound": _top_from_list(corsie, "inbound", 10),
        "abb_arr": _top_from_list(corsie, "abb_arr", 10),
        "abb_par": _top_from_list(corsie, "abb_par", 10),
        "mix": _top_from_list(corsie, "mix", 10),
    }

    return _clean_json({
        "status": "ok",
        "slot": slot_pick,
        "slots": ["ALL"] + slots,
        "view": view,
        "corsie": corsie,
        "top": top,
        "non_stok": cache.get("non_stok") or [],
        "meta": cache.get("meta") or {},
    })


# ============================
# UPLOAD FILE (Excel/CSV)
# ============================
@app.post("/data/upload")
async def upload_data(
    dataset: str = Form(...),   # operators / picking / pallet / history
    file: UploadFile = File(...)
):
    dataset = (dataset or "").strip().lower()
    if dataset not in ["operators", "picking", "pallet", "history"]:
        raise HTTPException(
            status_code=400,
            detail="Dataset non valido. Usa: operators oppure picking oppure pallet oppure history"
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Estensione non supportata: {ext}")

    storage = get_file_storage()

    if dataset == "history":
        dest = storage.save_upload(_history_storage_rel(), file)

        refresh_analysis()
        return {
            "status": "ok",
            "message": f"Caricato storico '{HISTORY_FILE_NAME}' e ricalcolata analisi",
            "saved_to": dest,
        }

    if dataset == "operators":
        dest = storage.save_upload(_input_storage_rel(CARRELLISTI_FILE_NAME), file)

        refresh_analysis()

        scarico_ref = _input_storage_rel(PALLET_FILE_NAME)
        scarico_path = _input_local_path(PALLET_FILE_NAME)
        car_path = _input_local_path(CARRELLISTI_FILE_NAME)
        try:
            if storage.exists(scarico_ref):
                refresh_pallet_cache(scarico_path, car_path, limit_rows=5000)
                refresh_pallet_demand_cache(scarico_path, car_path, window_min=30)
        except Exception:
            pass

        return {"status": "ok", "message": "Caricato carrellisti.xlsm e ricalcolata analisi", "saved_to": dest}

    if dataset == "pallet":
        dest = storage.save_upload(_input_storage_rel(PALLET_FILE_NAME), file)

        scarico_path = _input_local_path(PALLET_FILE_NAME)
        car_ref = _input_storage_rel(CARRELLISTI_FILE_NAME)
        car_path = _input_local_path(CARRELLISTI_FILE_NAME)
        try:
            if storage.exists(car_ref):
                refresh_pallet_cache(scarico_path, car_path, limit_rows=5000)
                refresh_pallet_demand_cache(scarico_path, car_path, window_min=30)
        except Exception:
            pass

        return {"status": "ok", "message": f"Caricato '{PALLET_FILE_NAME}' (sovrascritto)", "saved_to": dest}

    _cleanup_picking_files()

    original_name = Path(file.filename).name
    dest = storage.save_upload(_input_storage_rel(original_name), file)

    refresh_analysis()

    return {
        "status": "ok",
        "message": f"Caricato picking file '{original_name}' (vecchi cancellati) e ricalcolata analisi",
        "saved_to": dest,
    }


# ============================
# ENDPOINT BASE
# ============================
@app.get("/")
def root():
    return {"status": "ok", "message": "Warehouse control room backend attivo"}


@app.get("/kpi/overview")
def get_kpi_overview():
    result = get_analysis()
    return result.get("kpi_overview", {})


@app.get("/operators")
def get_operators():
    result = get_analysis()
    return result.get("operators", [])


@app.get("/layout")
def get_layout():
    r = run_agora_analysis(include_layout=True)
    layout = r.get("layout") or {}
    return {"cells": layout.get("cells", [])}


@app.get("/operator-paths")
def get_operator_paths():
    r = run_agora_analysis(include_paths=True)
    return {"operator_paths": r.get("operator_paths") or []}


# ✅ ENDPOINT STORICO (NUOVO)
@app.get("/history")
def get_history():
    r = get_analysis()
    return _clean_json(r.get("history", {}) or {})


# ✅ ENDPOINT BREAKDOWN DISTANZA (NUOVO)
@app.get("/kpi/dist-breakdown")
def dist_breakdown_and_compare(
    date: str | None = Query(None, description="YYYY-MM-DD. Se nullo usa ultima data disponibile."),
):
    r = get_analysis()

    detail = r.get("control_room_detail") or []
    if not detail:
        return {
            "status": "missing",
            "message": "control_room_detail vuoto. Verifica che agora_analysis.py lo produca.",
        }

    df_det = pd.DataFrame(detail)
    if df_det.empty or "Data" not in df_det.columns:
        return {"status": "missing", "message": "control_room_detail senza colonna Data o vuoto."}

    df_det["Data_dt"] = pd.to_datetime(df_det["Data"], errors="coerce")
    df_det["Data"] = df_det["Data_dt"].dt.date

    # -------------------------
    # DATA TARGET
    # -------------------------
    d = None
    if date:
        try:
            d = pd.to_datetime(date, errors="raise").date()
        except Exception:
            d = None

    if d is None:
        d = df_det["Data"].dropna().max()

    if d is None:
        return {"status": "missing", "message": "Impossibile determinare una data valida dai dati."}

    df_day = df_det[df_det["Data"] == d].copy()
    if df_day.empty:
        return {"status": "missing", "message": f"Nessun dato per la data {d}"}

    # -------------------------
    # BREAKDOWN OGGI
    # -------------------------
    def _pack_dim(dim: str):
        part = df_day[df_day["Dimensione"].astype(str).str.upper() == dim.upper()].copy()
        if part.empty:
            return []

        part["Bucket"] = part["Bucket"].astype(str).str.strip().str.upper()
        part["mean_m"] = pd.to_numeric(part["mean_m"], errors="coerce")

        if "pct_steps" not in part.columns:
            part["pct_steps"] = None
        if "steps" not in part.columns:
            part["steps"] = None

        part = part.dropna(subset=["mean_m"])
        part = part.sort_values("pct_steps", ascending=False, na_position="last")

        return part[["Bucket", "mean_m", "steps", "pct_steps"]].to_dict(orient="records")

    breakdown = {
        "AREA": _pack_dim("AREA"),
        "CIRCUITO": _pack_dim("CIRCUITO"),
        "EVENTO": _pack_dim("EVENTO"),
    }

    kpi = (r.get("kpi_overview") or {})
    dist_step_today = float(
        kpi.get("dist_media_step_m")
        or 0.0
    )

    # -------------------------
    # LETTURA STORICO
    # -------------------------
    df_hist = _read_history_df()
    compare = {"status": "missing", "mode": None, "rows": []}

    if not df_hist.empty:

        # filtro storico prima della data corrente
        if "Data" in df_hist.columns:
            base = df_hist[df_hist["Data"] < d].copy()
            mode = "weighted_mean_before_date"
        else:
            base = df_hist.copy()
            mode = "weighted_mean_overall"

        if not base.empty:

            # 🔥 MEDIA PESATA PER STEPS
            if "steps" not in base.columns:
                base["steps"] = 1  # fallback sicurezza

            base["weighted"] = base["mean_m"] * base["steps"]

            base_agg = (
                base.groupby(["Dimensione", "Bucket"], as_index=False)
                .agg(
                    weighted_sum=("weighted", "sum"),
                    steps_sum=("steps", "sum")
                )
            )

            base_agg["mean_m_base"] = (
                base_agg["weighted_sum"] / base_agg["steps_sum"]
            )

            base_agg["Dimensione"] = base_agg["Dimensione"].astype(str).str.upper()
            base_agg["Bucket"] = base_agg["Bucket"].astype(str).str.upper()

            base_agg = base_agg[["Dimensione", "Bucket", "mean_m_base"]]

            # -------------------------
            # MERGE CON OGGI
            # -------------------------
            cur = df_day.copy()
            cur["Dimensione"] = cur["Dimensione"].astype(str).str.upper()
            cur["Bucket"] = cur["Bucket"].astype(str).str.upper()
            cur["mean_m_today"] = pd.to_numeric(cur["mean_m"], errors="coerce")

            merged = cur.merge(base_agg, on=["Dimensione", "Bucket"], how="left")

            merged["delta_m"] = merged["mean_m_today"] - merged["mean_m_base"]
            merged["delta_pct"] = (merged["delta_m"] / merged["mean_m_base"] * 100.0)

            merged["delta_pct"] = merged["delta_pct"].replace([np.inf, -np.inf], np.nan)

            if "pct_steps" not in merged.columns:
                merged["pct_steps"] = None

            rows = merged[
                ["Dimensione", "Bucket", "mean_m_today", "mean_m_base",
                 "delta_m", "delta_pct", "pct_steps"]
            ].copy()

            rows = rows.sort_values(
                ["Dimensione", "pct_steps"],
                ascending=[True, False],
                na_position="last"
            )

            compare = {
                "status": "ok",
                "mode": mode,
                "rows": _clean_json(rows.to_dict(orient="records")),
            }

    return _clean_json({
        "status": "ok",
        "date": str(d),
        "dist_media_step_m": dist_step_today,
        "breakdown": breakdown,
        "compare": compare,
    })
# ============================
# STATISTICHE PERCORSI
# ============================
@app.get("/paths/stats")
def get_paths_stats(
    operators: str = Query(..., description="Lista operatori separati da virgola. Es: 101,102"),
    start: Optional[str] = Query(None, description="Ora inizio HH:MM"),
    end: Optional[str] = Query(None, description="Ora fine HH:MM"),
):
    result = get_analysis()
    df_pik = result.get("df_pik")

    if df_pik is None or getattr(df_pik, "empty", True):
        return {
            "overall": {"operators": [], "missions": 0, "rows": 0, "colli": 0, "hours": 0.0, "prod_colli_ora": 0.0},
            "by_operator": [],
        }

    op_list: List[int] = []
    for part in operators.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            op_list.append(int(part))
        except ValueError:
            continue

    if not op_list:
        return {
            "overall": {"operators": [], "missions": 0, "rows": 0, "colli": 0, "hours": 0.0, "prod_colli_ora": 0.0},
            "by_operator": [],
        }

    start_t = _parse_time_str(start)
    end_t = _parse_time_str(end)

    mask_base = (
        df_pik["Corsia_num"].notna()
        & df_pik["Posto_num"].notna()
        & (df_pik["PallettizzatoSN_str"] == "n")
        & (df_pik["Circuito"] != "SEN")
        & df_pik["Operatore"].isin(op_list)
    )

    time_mask = df_pik["Ora_ts"].notna()
    if start_t:
        time_mask = time_mask & (df_pik["Ora_ts"].dt.time >= start_t)
    if end_t:
        time_mask = time_mask & (df_pik["Ora_ts"].dt.time <= end_t)

    df_sel = df_pik.loc[mask_base & time_mask].copy()

    missions = int(df_sel["Lista"].nunique())
    rows = int(len(df_sel))
    colli = int(df_sel["Colli"].sum())

    mask_time = (df_pik["Operatore"].isin(op_list) & df_pik["Considera"] & (df_pik["Circuito"] != "SEN")) & time_mask
    hours = float(td_to_hours(df_pik.loc[mask_time, "TempoMov"]))
    prod = float(colli / hours) if hours > 0 else 0.0

    overall = {
        "operators": [str(o) for o in op_list],
        "missions": missions,
        "rows": rows,
        "colli": colli,
        "hours": round(hours, 2),
        "prod_colli_ora": round(prod, 1),
    }

    by_operator = []
    for op in op_list:
        df_op = df_sel[df_sel["Operatore"] == op]
        missions_op = int(df_op["Lista"].nunique()) if not df_op.empty else 0
        rows_op = int(len(df_op)) if not df_op.empty else 0
        colli_op = int(df_op["Colli"].sum()) if not df_op.empty else 0

        mask_time_op = ((df_pik["Operatore"] == op) & df_pik["Considera"] & (df_pik["Circuito"] != "SEN")) & time_mask
        hours_op = float(td_to_hours(df_pik.loc[mask_time_op, "TempoMov"]))
        prod_op = float(colli_op / hours_op) if hours_op > 0 else 0.0

        by_operator.append({
            "operator": str(op),
            "missions": missions_op,
            "rows": rows_op,
            "colli": colli_op,
            "hours": round(hours_op, 2),
            "prod_colli_ora": round(prod_op, 1),
        })

    return {"overall": overall, "by_operator": by_operator}


# ============================
# ASSISTENTE
# ============================
class AssistantRequest(BaseModel):
    question: str


class AssistantResponse(BaseModel):
    answer: str


@app.post("/assistant", response_model=AssistantResponse)
def assistant_endpoint(payload: AssistantRequest):
    analysis = get_analysis()
    kpi = analysis.get("kpi_overview", {}) or {}

    units = float(kpi.get("units_per_hour", 0.0) or 0.0)
    target = float((kpi.get("target_units_per_hour") or kpi.get("prod_target_colli_ora") or 0.0) or 0.0)
    colli_tot = int(kpi.get("colli_totali", 0) or 0)
    ore = float(kpi.get("tempo_netto_ore", 0.0) or 0.0)
    tempo_cambio = float(kpi.get("tempo_medio_cambio_ore", 0.0) or 0.0)
    colli_riga = float(kpi.get("colli_per_riga", 0.0) or 0.0)
    colli_lista = float(kpi.get("colli_per_lista", 0.0) or 0.0)
    issues = int(kpi.get("return_rate", 0) or 0)

    parts = []
    parts.append("Ti do una lettura veloce della situazione basata sui dati attualmente caricati.\n")
    parts.append(f"- Produttività complessiva: circa **{units:.1f} colli/ora** netti di movimento.")

    if target > 0:
        delta = units - target
        if delta >= 5:
            parts.append(f"- Benchmark teorico (PARAM): **{target:.1f} colli/ora**, quindi sei **sopra** di circa {delta:.1f}.")
        elif delta <= -5:
            parts.append(f"- Benchmark teorico (PARAM): **{target:.1f} colli/ora**, quindi sei **sotto** di circa {abs(delta):.1f}.")
        else:
            parts.append(f"- Benchmark teorico (PARAM): **{target:.1f} colli/ora**, sei sostanzialmente in linea.")

    parts.append(f"- Volume lavorato: **{colli_tot:,} colli** in circa **{ore:.1f} ore nette**.".replace(",", "."))

    if tempo_cambio:
        parts.append(f"- Tempo medio cambio missione: circa **{tempo_cambio*60:.1f} minuti** a cambio lista.")
    if colli_riga:
        parts.append(f"- Riga media: **{colli_riga:.2f} colli**; Lista media: **{colli_lista:.1f} colli**.")
    if issues:
        parts.append(f"- Rilevati **{issues} fenomeni** tra ritorni e recuperi.")

    parts.append("\nSe vuoi posso aiutarti su una lettura specifica dei KPI o sugli scostamenti.")
    return AssistantResponse(answer="\n".join(parts))


# ============================
# FATIGUE
# ============================
@app.get("/fatigue")
def fatigue_curve(
    operator: int = Query(..., description="Operatore, es: 220"),
    start: str = Query("06:00", description="Ora inizio HH:MM"),
    end: str = Query("22:00", description="Ora fine HH:MM"),
    window_min: int = Query(60, description="Ampiezza finestra in minuti"),
    min_net_minutes: int = Query(15, description="Minuti netti minimi per considerare attendibile una finestra"),
):
    result = get_analysis()
    df_pik = result.get("df_pik")
    kpi = result.get("kpi_overview", {}) or {}

    if df_pik is None or getattr(df_pik, "empty", True):
        return {"status": "ok", "insight": "Dati picking non disponibili nella cache.", "data": []}

    expected_base = _safe_float(
        kpi.get("target_units_per_hour")
        or kpi.get("prod_target_colli_ora")
        or kpi.get("units_per_hour_target")
        or 0.0,
        0.0
    )

    start_t = _parse_time_str(start)
    end_t = _parse_time_str(end)
    if start_t is None or end_t is None:
        return {"status": "error", "message": "Formato start/end non valido. Usa HH:MM", "data": []}

    base = (
        (df_pik["Operatore"] == operator)
        & (df_pik["PallettizzatoSN_str"] == "n")
        & (df_pik["Circuito"] != "SEN")
        & (df_pik["Ora_ts"].notna())
    )
    df = df_pik.loc[base].copy()
    if df.empty:
        return {"status": "ok", "insight": "Nessun dato per l'operatore nel perimetro scelto.", "data": []}

    df["hhmm_time"] = df["Ora_ts"].dt.time
    df = df[df["hhmm_time"].apply(lambda t: _time_in_range_cross_midnight(t, start_t, end_t))]
    if df.empty:
        return {"status": "ok", "insight": "Nessuna riga nella fascia oraria selezionata.", "data": []}

    freq = f"{int(window_min)}min"
    df["bucket"] = df["Ora_ts"].dt.floor(freq)

    g_colli = df.groupby("bucket")["Colli"].sum()

    df_valid_time = df[df["Considera"] & df["TempoMov"].notna()].copy()
    if df_valid_time.empty:
        return {"status": "ok", "insight": "Tempo netto non disponibile (Considera/TempoMov vuoti).", "data": []}

    g_seconds = df_valid_time.groupby("bucket")["TempoMov"].apply(lambda s: float(s.dt.total_seconds().sum()))
    buckets = sorted(set(g_colli.index).union(set(g_seconds.index)))

    expected_by_bucket = _expected_by_bucket_from_lists(df)

    out = []
    cum_colli = 0.0
    cum_hours = 0.0
    cum_expected_colli = 0.0
    worst_gap = 0.0
    worst_time = None

    for b in buckets:
        colli = float(g_colli.get(b, 0.0))
        sec = float(g_seconds.get(b, 0.0))
        net_min = sec / 60.0
        if net_min < float(min_net_minutes):
            continue

        hours = sec / 3600.0
        prod_real = (colli / hours) if hours > 0 else 0.0

        cum_colli += colli
        cum_hours += hours
        avg_to_now = (cum_colli / cum_hours) if cum_hours > 0 else 0.0

        expected = float(expected_by_bucket.get(b, 0.0)) or (expected_base if expected_base > 0 else 0.0)
        exp_colli_window = expected * hours
        gap_window = exp_colli_window - colli

        if gap_window > worst_gap:
            worst_gap = gap_window
            worst_time = b.isoformat()

        cum_expected_colli += exp_colli_window
        cum_gap = cum_expected_colli - cum_colli
        loss_cum = max(0.0, cum_gap)

        fatigue_ratio = (prod_real / expected) if expected > 0 else None
        fatigue_pct = (fatigue_ratio * 100.0) if fatigue_ratio is not None else None

        out.append({
            "bucket": b.isoformat(),
            "label": _hhmm_from_bucket(b.isoformat()),
            "net_minutes": round(net_min, 1),
            "colli": int(round(colli)),
            "prod_real": round(prod_real, 1),
            "avg_to_now": round(avg_to_now, 1),
            "expected": round(expected, 1),
            "fatigue_ratio": round(fatigue_ratio, 3) if fatigue_ratio is not None else None,
            "fatigue_pct": round(fatigue_pct, 1) if fatigue_ratio is not None else None,
            "gap_window_colli": round(gap_window, 1),
            "loss_colli_cum": round(loss_cum, 1),
            "prod_colli_ora": round(prod_real, 1),
        })

    if not out:
        insight = "Nessuna finestra valida con i filtri attuali (prova ad abbassare i minuti netti minimi)."
    else:
        loss_final = out[-1]["loss_colli_cum"]
        if loss_final <= 0:
            insight = f"Operatore {operator}: nella fascia {start}–{end} non emerge una perdita a consuntivo."
        else:
            t0 = worst_time[11:16] if worst_time else "N/D"
            insight = f"Operatore {operator}: perdita stimata ~{round(loss_final, 0)} colli. Peggior calo intorno alle {t0}."

    return {
        "status": "ok",
        "operator": str(operator),
        "start": start,
        "end": end,
        "window_min": window_min,
        "min_net_minutes": min_net_minutes,
        "expected_base": round(expected_base, 1),
        "insight": insight,
        "data": out,
    }


# ============================
# FORKLIFT (SU CACHE DI AGORA_ANALYSIS)
# ============================
@app.get("/forklift/overview")
def get_forklift_overview(force: bool = False):
    if force:
        refresh_analysis()
    r = get_analysis()
    return r.get("forklift_kpi_overview", {})


@app.get("/forklift/operators")
def get_forklift_operators(force: bool = False):
    if force:
        refresh_analysis()
    r = get_analysis()
    return r.get("forklift_operators", [])


@app.get("/forklift/activities")
def get_forklift_activities(
    limit: int = Query(50, ge=1, le=500),
    operator_id: int | None = None,
    tipo: str | None = None,
    force: bool = False,
):
    if force:
        refresh_analysis()

    r = get_analysis()
    df = r.get("df_fk")
    if df is None or getattr(df, "empty", True):
        return {"rows": 0, "data": []}

    dff = df
    if operator_id is not None and "Operatore" in dff.columns:
        dff = dff[dff["Operatore"] == operator_id]

    if tipo and "TipoMov" in dff.columns:
        dff = dff[dff["TipoMov"].astype(str).str.upper() == tipo.strip().upper()]

    cols = [c for c in ["Operatore", "TipoMov", "DescrizioneMov", "start_ts", "durata_sec", "durata_h", "Considera"]
            if c in dff.columns]
    if "start_ts" in dff.columns:
        dff = dff.sort_values("start_ts", na_position="last")

    data = dff[cols].head(limit).to_dict(orient="records")
    return {"rows": int(len(dff)), "data": data}


# ============================
# PALLET CHECK (NELLA PAGINA CARRELLISTI)
# ============================
@app.get("/forklift/pallet-check")
def forklift_pallet_check(
    limit_rows: int = Query(5000, ge=1, le=200000),
    force: bool = False,
):
    storage = get_file_storage()
    scarico_ref = _input_storage_rel(PALLET_FILE_NAME)
    car_ref = _input_storage_rel(CARRELLISTI_FILE_NAME)

    if not storage.exists(scarico_ref):
        return {"status": "missing", "message": f"Manca {PALLET_FILE_NAME}. Caricalo con dataset='pallet'."}
    if not storage.exists(car_ref):
        return {"status": "missing", "message": f"Manca {CARRELLISTI_FILE_NAME}. Caricalo con dataset='operators'."}

    scarico_path = _input_local_path(PALLET_FILE_NAME)
    car_path = _input_local_path(CARRELLISTI_FILE_NAME)

    cache = (
        refresh_pallet_cache(scarico_path, car_path, limit_rows=limit_rows)
        if force else
        get_pallet_cache(scarico_path, car_path, limit_rows=limit_rows)
    )

    incrocio = (cache.get("incrocio", []) or [])[:limit_rows]

    scarico_by_hour = cache.get("scarico_by_hour", []) or []
    ripristino_by_hour = cache.get("ripristino_by_hour", []) or []

    payload = {
        "status": cache.get("status", "ok"),
        "rows": len(incrocio),
        "incrocio": incrocio,

        "scarico_by_hour": scarico_by_hour,
        "ripristino_by_hour": ripristino_by_hour,

        "scarico_per_ora": scarico_by_hour,
        "riprist_per_ora": ripristino_by_hour,

        "meta": cache.get("meta", {}) or {},
    }
    return _clean_json(payload)


# ============================
# PALLET DEMAND (NUOVA MAPPA "WOW")
# ============================
@app.get("/forklift/pallet-demand")
def forklift_pallet_demand(
    slot: str | None = Query(None, description="Slot HH:MM (es 07:00). Se nullo: ultimo slot. Usa ALL per totale giornata."),
    view: str = Query("mix", description="inbound | abb_arr | abb_par | mix"),
    window_min: int = Query(30, ge=5, le=120, description="Ampiezza slot in minuti (default 30)"),
    force: bool = False,
):
    storage = get_file_storage()
    scarico_ref = _input_storage_rel(PALLET_FILE_NAME)
    car_ref = _input_storage_rel(CARRELLISTI_FILE_NAME)

    if not storage.exists(scarico_ref):
        return {"status": "missing", "message": f"Manca {PALLET_FILE_NAME}. Caricalo con dataset='pallet'."}
    if not storage.exists(car_ref):
        return {"status": "missing", "message": f"Manca {CARRELLISTI_FILE_NAME}. Caricalo con dataset='operators'."}

    scarico_path = _input_local_path(PALLET_FILE_NAME)
    car_path = _input_local_path(CARRELLISTI_FILE_NAME)

    view = (view or "mix").strip().lower()
    if view not in {"inbound", "abb_arr", "abb_par", "mix"}:
        view = "mix"

    demand_cache = (
        refresh_pallet_demand_cache(scarico_path, car_path, window_min=window_min)
        if force else
        get_pallet_demand_cache(scarico_path, car_path, window_min=window_min)
    )

    payload = build_demand_slot_payload(demand_cache, slot=slot, view=view)
    return _clean_json(payload)
