from __future__ import annotations

from pathlib import Path
from datetime import datetime, time as time_class
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# =========================
# CONFIG
# =========================
SHEET_SCARICO_DEFAULT = "scarico"       # se non esiste, uso il primo foglio
SHEET_CAR_DEFAULT = "carrellisti"       # se non esiste, uso il primo foglio

# Scarico
COL_SUPPORTO = "SUPPORTO"
COL_ORA_INIZIO_CONSEGNA = "ORA INIZIO CONSEGNA"
COL_ARTICOLO = "ARTICOLO"
COL_DESC_ARTICOLO = "DESCRIZIONE ARTICOLO"

# Carrellisti
COL_PALLET_NUM = "Pallet:Numero"
COL_CONS_ORA = "Cons.Ora"
COL_TP_MOV = "Tp Movimento"
COL_ARR_CORSIA = "ARR:Corsia"
COL_PAR_CORSIA = "PAR:Corsia"

MOV_ABBASSAMENTO = "RIPRIST.TOT DA SCORTA A PRESA"

# corsie
CORSIA_MIN = 13
CORSIA_MAX = 75
EXCLUDED_CORSIE = {"KAR"}

# cache separata
_pallet_cache: Optional[Dict[str, Any]] = None
_pallet_lock = threading.Lock()

_demand_cache: Optional[Dict[str, Any]] = None
_demand_lock = threading.Lock()


# =========================
# HELPERS
# =========================
def _pick_sheet(xls: pd.ExcelFile, preferred: str) -> str:
    names = list(xls.sheet_names or [])
    if not names:
        raise ValueError("Excel senza fogli")
    for n in names:
        if n.strip().lower() == preferred.strip().lower():
            return n
    return names[0]


def _normalize_time_to_time(x) -> Optional[time_class]:
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

    # "06.00.01" -> "06:00:01"
    s = s.replace(".", ":")

    parts = s.split(":")
    if len(parts) == 3:
        try:
            return time_class(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return None
    if len(parts) == 2:
        try:
            return time_class(int(parts[0]), int(parts[1]), 0)
        except Exception:
            return None

    return None


def _hour_bucket(t: Optional[time_class]) -> Optional[str]:
    if t is None:
        return None
    return f"{t.hour:02d}:00"


def _slot_bucket(t: Optional[time_class], window_min: int) -> Optional[str]:
    if t is None:
        return None
    w = int(window_min) if window_min else 30
    m = (t.minute // w) * w
    return f"{t.hour:02d}:{m:02d}"


def _parse_corsia_val(x) -> Optional[int]:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    # escludi stringhe come "KAR"
    s = str(x).strip().upper()
    if not s:
        return None
    if s in EXCLUDED_CORSIE:
        return None

    # se è numerico o "36.0"
    try:
        v = int(float(s))
    except Exception:
        return None

    if v < CORSIA_MIN or v > CORSIA_MAX:
        return None
    return v


def _pallet_from_supporto(val) -> tuple[Optional[str], Optional[int]]:
    """
    Replica Excel: =VALORE(DESTRA(O2;5))
    - estrae ultime 5 cifre
    - ritorna:
      - stringa 5 cifre ("00012") per display
      - int (12) per incrocio
    """
    if val is None:
        return (None, None)
    try:
        if pd.isna(val):
            return (None, None)
    except Exception:
        pass

    s = str(val)
    m = re.search(r"(\d{5})\s*$", s)
    if m:
        d5 = m.group(1)
    else:
        tail = s[-5:]
        only_digits = "".join(ch for ch in tail if ch.isdigit())
        if not only_digits:
            return (None, None)
        d5 = only_digits.rjust(5, "0")[:5]

    try:
        return (d5, int(d5))
    except Exception:
        return (d5, None)


def _clean_json(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()

    if isinstance(obj, float):
        # NaN/Inf -> None
        if obj != obj:
            return None
        if obj == float("inf") or obj == float("-inf"):
            return None
        return obj

    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    if isinstance(obj, dict):
        return {str(k): _clean_json(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_clean_json(x) for x in obj]

    try:
        if hasattr(obj, "item"):
            return _clean_json(obj.item())
    except Exception:
        pass

    return obj


def _df_to_records_safe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    return _clean_json(df.to_dict(orient="records"))


# =========================
# CORE: PALLET CHECK (vecchio endpoint)
# =========================
def compute_pallet_check(
    scarico_path: Path,
    carrellisti_path: Path,
    limit_rows: int = 5000,
) -> Dict[str, Any]:
    if not scarico_path.exists():
        return {"status": "missing", "detail": f"File scarico non trovato: {scarico_path}"}
    if not carrellisti_path.exists():
        return {"status": "missing", "detail": f"File carrellisti non trovato: {carrellisti_path}"}

    # --- Scarico
    xls_s = pd.ExcelFile(scarico_path)
    sheet_s = _pick_sheet(xls_s, SHEET_SCARICO_DEFAULT)
    df_s = pd.read_excel(scarico_path, sheet_name=sheet_s)

    # --- Carrellisti
    xls_c = pd.ExcelFile(carrellisti_path)
    sheet_c = _pick_sheet(xls_c, SHEET_CAR_DEFAULT)
    df_c = pd.read_excel(carrellisti_path, sheet_name=sheet_c)

    if COL_SUPPORTO not in df_s.columns:
        return {"status": "error", "detail": f"Manca colonna '{COL_SUPPORTO}' nel foglio scarico ({sheet_s})"}
    if COL_ORA_INIZIO_CONSEGNA not in df_s.columns:
        return {"status": "error", "detail": f"Manca colonna '{COL_ORA_INIZIO_CONSEGNA}' nel foglio scarico ({sheet_s})"}
    if COL_PALLET_NUM not in df_c.columns:
        return {"status": "error", "detail": f"Manca colonna '{COL_PALLET_NUM}' nel foglio carrellisti ({sheet_c})"}

    # pallet da supporto
    p5_list: List[Optional[str]] = []
    pn_list: List[Optional[int]] = []
    for v in df_s[COL_SUPPORTO]:
        p5, pn = _pallet_from_supporto(v)
        p5_list.append(p5)
        pn_list.append(pn)

    df_s["PALLET_SCARICATO_5"] = p5_list
    df_s["PALLET_SCARICATO_NUM"] = pn_list

    # ora inizio consegna -> bucket ora
    df_s["ORA_INIZIO_CONSEGNA_TIME"] = df_s[COL_ORA_INIZIO_CONSEGNA].apply(_normalize_time_to_time)
    df_s["ORA_INIZIO_CONSEGNA_HOUR"] = df_s["ORA_INIZIO_CONSEGNA_TIME"].apply(_hour_bucket)

    # carrellisti: pallet num + cons ora
    df_c["PALLET_NUM"] = pd.to_numeric(df_c[COL_PALLET_NUM], errors="coerce")

    if COL_CONS_ORA in df_c.columns:
        df_c["CONS_ORA_TIME"] = df_c[COL_CONS_ORA].apply(_normalize_time_to_time)
        df_c["CONS_ORA_HOUR"] = df_c["CONS_ORA_TIME"].apply(_hour_bucket)
    else:
        df_c["CONS_ORA_TIME"] = None
        df_c["CONS_ORA_HOUR"] = None

    # lookup per pallet (prima occorrenza)
    df_lookup = (
        df_c.dropna(subset=["PALLET_NUM"])
        .drop_duplicates(subset=["PALLET_NUM"])
        .set_index("PALLET_NUM")
    )

    corsia: List[Any] = []
    posto: List[Any] = []
    piano: List[Any] = []
    stoccato: List[str] = []

    for pn in df_s["PALLET_SCARICATO_NUM"]:
        if pn is None:
            corsia.append(None)
            posto.append(None)
            piano.append(None)
            stoccato.append("NON STOK")
            continue

        try:
            pn_key = float(pn)
        except Exception:
            pn_key = None

        if pn_key is None or pn_key not in df_lookup.index:
            corsia.append(None)
            posto.append(None)
            piano.append(None)
            stoccato.append("NON STOK")
            continue

        row = df_lookup.loc[pn_key]
        corsia.append(row.get(COL_ARR_CORSIA, None))
        posto.append(row.get("ARR:Posto", None))
        piano.append(row.get("ARR:Piano", None))
        stoccato.append("STOK")

    df_s["CORSIA"] = corsia
    df_s["POSTO"] = posto
    df_s["PIANO"] = piano
    df_s["STOCCATO"] = stoccato

    # pallet scaricati per ora
    df_s_hour = (
        df_s.dropna(subset=["ORA_INIZIO_CONSEGNA_HOUR"])
        .groupby("ORA_INIZIO_CONSEGNA_HOUR", as_index=False)
        .agg(
            pallet_scaricati=("PALLET_SCARICATO_NUM", "nunique"),
            righe=("PALLET_SCARICATO_NUM", "size"),
        )
        .sort_values("ORA_INIZIO_CONSEGNA_HOUR")
    )

    # RIPRIST per ora
    if COL_TP_MOV in df_c.columns:
        dff = df_c.copy()
        dff[COL_TP_MOV] = dff[COL_TP_MOV].astype(str).str.strip().str.upper()
        df_rip = dff[dff[COL_TP_MOV] == MOV_ABBASSAMENTO.upper()].copy()
    else:
        df_rip = df_c.iloc[0:0].copy()

    df_rip_hour = (
        df_rip.dropna(subset=["CONS_ORA_HOUR"])
        .groupby("CONS_ORA_HOUR", as_index=False)
        .agg(
            movimenti=(COL_TP_MOV, "size"),
            pallet_coinvolti=("PALLET_NUM", "nunique"),
        )
        .sort_values("CONS_ORA_HOUR")
    )

    incrocio_cols = [
        COL_SUPPORTO,
        COL_ORA_INIZIO_CONSEGNA,
        "ORA_INIZIO_CONSEGNA_HOUR",
        "PALLET_SCARICATO_5",
        "PALLET_SCARICATO_NUM",
        "STOCCATO",
        "CORSIA",
        "POSTO",
        "PIANO",
    ]
    incrocio_cols = [c for c in incrocio_cols if c in df_s.columns]
    df_incrocio = df_s[incrocio_cols].head(limit_rows).copy()

    payload = {
        "status": "ok",
        "meta": {
            "sheet_scarico": sheet_s,
            "sheet_carrellisti": sheet_c,
            "rows_scarico": int(len(df_s)),
            "rows_carrellisti": int(len(df_c)),
            "limit_rows": int(limit_rows),
        },
        "incrocio": _df_to_records_safe(df_incrocio),
        "scarico_by_hour": _df_to_records_safe(df_s_hour),
        "ripristino_by_hour": _df_to_records_safe(df_rip_hour),
    }
    return _clean_json(payload)


# =========================
# CORE: DEMAND MAP (NUOVO)
# =========================
def compute_pallet_demand(
    scarico_path: Path,
    carrellisti_path: Path,
    window_min: int = 30,
) -> Dict[str, Any]:
    """
    Produce timeseries per slot (30 min default) per corsia (13..75), escludendo KAR:
      - inbound_by_slot_corsia (da scarico matchato su pallet -> ARR:Corsia)
      - abb_arr_by_slot_corsia (RIPRIST.TOT -> ARR:Corsia)
      - abb_par_by_slot_corsia (RIPRIST.TOT -> PAR:Corsia)
    + lista NON STOK completa con articolo/descrizione.
    """

    if not scarico_path.exists():
        return {"status": "missing", "detail": f"File scarico non trovato: {scarico_path}"}
    if not carrellisti_path.exists():
        return {"status": "missing", "detail": f"File carrellisti non trovato: {carrellisti_path}"}

    w = int(window_min) if window_min else 30
    if w <= 0:
        w = 30

    # --- read scarico
    xls_s = pd.ExcelFile(scarico_path)
    sheet_s = _pick_sheet(xls_s, SHEET_SCARICO_DEFAULT)
    df_s = pd.read_excel(scarico_path, sheet_name=sheet_s)

    # --- read carrellisti
    xls_c = pd.ExcelFile(carrellisti_path)
    sheet_c = _pick_sheet(xls_c, SHEET_CAR_DEFAULT)
    df_c = pd.read_excel(carrellisti_path, sheet_name=sheet_c)

    # checks minimi
    for col in [COL_SUPPORTO, COL_ORA_INIZIO_CONSEGNA]:
        if col not in df_s.columns:
            return {"status": "error", "detail": f"Manca colonna '{col}' nel foglio scarico ({sheet_s})"}

    for col in [COL_PALLET_NUM, COL_ARR_CORSIA, COL_CONS_ORA, COL_TP_MOV]:
        if col not in df_c.columns:
            return {"status": "error", "detail": f"Manca colonna '{col}' nel foglio carrellisti ({sheet_c})"}

    # --------- scarico: pallet + slot
    p5_list: List[Optional[str]] = []
    pn_list: List[Optional[int]] = []
    for v in df_s[COL_SUPPORTO]:
        p5, pn = _pallet_from_supporto(v)
        p5_list.append(p5)
        pn_list.append(pn)
    df_s["PALLET_SCARICATO_5"] = p5_list
    df_s["PALLET_SCARICATO_NUM"] = pn_list

    df_s["_t"] = df_s[COL_ORA_INIZIO_CONSEGNA].apply(_normalize_time_to_time)
    df_s["_slot"] = df_s["_t"].apply(lambda t: _slot_bucket(t, w))

    # --------- carrellisti: pallet num + slot cons ora
    df_c["PALLET_NUM"] = pd.to_numeric(df_c[COL_PALLET_NUM], errors="coerce")
    df_c["_t_cons"] = df_c[COL_CONS_ORA].apply(_normalize_time_to_time)
    df_c["_slot"] = df_c["_t_cons"].apply(lambda t: _slot_bucket(t, w))

    # normalizza corsie
    df_c["_arr_corsia"] = df_c[COL_ARR_CORSIA].apply(_parse_corsia_val)
    df_c["_par_corsia"] = df_c.get(COL_PAR_CORSIA, None)
    if COL_PAR_CORSIA in df_c.columns:
        df_c["_par_corsia"] = df_c[COL_PAR_CORSIA].apply(_parse_corsia_val)
    else:
        df_c["_par_corsia"] = None

    # --------- lookup stock per pallet (per inbound)
    df_lookup = (
        df_c.dropna(subset=["PALLET_NUM"])
        .drop_duplicates(subset=["PALLET_NUM"])
        .set_index("PALLET_NUM")
    )

    # inbound: per ogni pallet scaricato, trova ARR corsia
    arr_corsia_list: List[Optional[int]] = []
    stoccato_list: List[str] = []
    for pn in df_s["PALLET_SCARICATO_NUM"]:
        if pn is None:
            arr_corsia_list.append(None)
            stoccato_list.append("NON STOK")
            continue

        try:
            pn_key = float(pn)
        except Exception:
            pn_key = None

        if pn_key is None or pn_key not in df_lookup.index:
            arr_corsia_list.append(None)
            stoccato_list.append("NON STOK")
            continue

        row = df_lookup.loc[pn_key]
        c = _parse_corsia_val(row.get(COL_ARR_CORSIA, None))
        arr_corsia_list.append(c)
        stoccato_list.append("STOK")

    df_s["_arr_corsia"] = arr_corsia_list
    df_s["_stoccato"] = stoccato_list

    # --------- NON STOK list (tutti)
    non_stok_df = df_s[df_s["_stoccato"] == "NON STOK"].copy()
    non_stok_cols = [
        COL_SUPPORTO,
        COL_ORA_INIZIO_CONSEGNA,
        "PALLET_SCARICATO_NUM",
        "PALLET_SCARICATO_5",
        COL_ARTICOLO,
        COL_DESC_ARTICOLO,
    ]
    non_stok_cols = [c for c in non_stok_cols if c in non_stok_df.columns]
    non_stok_df = non_stok_df[non_stok_cols].copy()

    # --------- inbound aggregation (slot + ARR corsia)
    inbound = df_s.dropna(subset=["_slot", "_arr_corsia"]).copy()
    inbound_by = (
        inbound.groupby(["_slot", "_arr_corsia"], as_index=False)
        .agg(pallet=("PALLET_SCARICATO_NUM", "nunique"))
    )

    # --------- abbassamenti: filtro RIPRIST.TOT e aggrega su ARR e PAR
    dff = df_c.copy()
    dff[COL_TP_MOV] = dff[COL_TP_MOV].astype(str).str.strip().str.upper()
    abb = dff[dff[COL_TP_MOV] == MOV_ABBASSAMENTO.upper()].copy()

    abb_arr = abb.dropna(subset=["_slot", "_arr_corsia"]).copy()
    abb_arr_by = (
        abb_arr.groupby(["_slot", "_arr_corsia"], as_index=False)
        .agg(movimenti=(COL_TP_MOV, "size"))
    )

    abb_par = abb.dropna(subset=["_slot", "_par_corsia"]).copy()
    abb_par_by = (
        abb_par.groupby(["_slot", "_par_corsia"], as_index=False)
        .agg(movimenti=(COL_TP_MOV, "size"))
    )

    # --------- slot list: unione (ordinata)
    slots = sorted(set(inbound_by["_slot"].dropna().astype(str).tolist()) | set(abb_arr_by["_slot"].dropna().astype(str).tolist()))
    # fallback: se vuoto, prova da scarico
    if not slots:
        slots = sorted(set(df_s["_slot"].dropna().astype(str).tolist()))

    # --------- build maps: slot -> corsia -> value
    def _empty_slot_map() -> Dict[int, int]:
        return {c: 0 for c in range(CORSIA_MIN, CORSIA_MAX + 1)}

    inbound_map: Dict[str, Dict[int, int]] = {s: _empty_slot_map() for s in slots}
    abb_arr_map: Dict[str, Dict[int, int]] = {s: _empty_slot_map() for s in slots}
    abb_par_map: Dict[str, Dict[int, int]] = {s: _empty_slot_map() for s in slots}

    for _, r in inbound_by.iterrows():
        s = str(r["_slot"])
        c = int(r["_arr_corsia"])
        v = int(r["pallet"])
        if s in inbound_map and c in inbound_map[s]:
            inbound_map[s][c] += v

    for _, r in abb_arr_by.iterrows():
        s = str(r["_slot"])
        c = int(r["_arr_corsia"])
        v = int(r["movimenti"])
        if s in abb_arr_map and c in abb_arr_map[s]:
            abb_arr_map[s][c] += v

    for _, r in abb_par_by.iterrows():
        s = str(r["_slot"])
        c = int(r["_par_corsia"])
        v = int(r["movimenti"])
        if s in abb_par_map and c in abb_par_map[s]:
            abb_par_map[s][c] += v

    payload = {
        "status": "ok",
        "meta": {
            "window_min": int(w),
            "available_slots": slots,
            "corsie_range": {"min": CORSIA_MIN, "max": CORSIA_MAX},
            "excluded": sorted(list(EXCLUDED_CORSIE)),
            "sheet_scarico": sheet_s,
            "sheet_carrellisti": sheet_c,
            "rows_scarico": int(len(df_s)),
            "rows_carrellisti": int(len(df_c)),
        },
        "series": {
            "inbound": inbound_map,
            "abb_arr": abb_arr_map,
            "abb_par": abb_par_map,
        },
        "non_stok": _df_to_records_safe(non_stok_df),
    }
    return _clean_json(payload)


# =========================
# CACHE: pallet-check
# =========================
def get_pallet_cache(
    scarico_path: Path,
    carrellisti_path: Path,
    limit_rows: int = 5000,
) -> Dict[str, Any]:
    global _pallet_cache
    if _pallet_cache is None:
        with _pallet_lock:
            if _pallet_cache is None:
                _pallet_cache = compute_pallet_check(scarico_path, carrellisti_path, limit_rows=limit_rows)
    return _pallet_cache


def refresh_pallet_cache(
    scarico_path: Path,
    carrellisti_path: Path,
    limit_rows: int = 5000,
) -> Dict[str, Any]:
    global _pallet_cache
    with _pallet_lock:
        _pallet_cache = compute_pallet_check(scarico_path, carrellisti_path, limit_rows=limit_rows)
    return _pallet_cache


# =========================
# CACHE: demand
# =========================
def get_pallet_demand_cache(
    scarico_path: Path,
    carrellisti_path: Path,
    window_min: int = 30,
) -> Dict[str, Any]:
    global _demand_cache
    if _demand_cache is None:
        with _demand_lock:
            if _demand_cache is None:
                _demand_cache = compute_pallet_demand(scarico_path, carrellisti_path, window_min=window_min)
    return _demand_cache


def refresh_pallet_demand_cache(
    scarico_path: Path,
    carrellisti_path: Path,
    window_min: int = 30,
) -> Dict[str, Any]:
    global _demand_cache
    with _demand_lock:
        _demand_cache = compute_pallet_demand(scarico_path, carrellisti_path, window_min=window_min)
    return _demand_cache


# =========================
# UTIL: build slot payload for API (slice)
# =========================
def build_demand_slot_payload(
    demand_cache: Dict[str, Any],
    slot: Optional[str],
    view: str = "mix",
) -> Dict[str, Any]:
    """
    Trasforma series complete -> risposta per 1 slot.
    view: inbound | abb_arr | abb_par | mix
    """
    if not demand_cache or demand_cache.get("status") != "ok":
        return demand_cache or {"status": "error", "detail": "Demand cache non valida"}

    meta = demand_cache.get("meta", {}) or {}
    slots = meta.get("available_slots", []) or []
    if not slots:
        return {"status": "ok", "meta": meta, "slot": None, "corsie": [], "kpi": {}, "top": {}, "non_stok": demand_cache.get("non_stok", []) or []}

    slot_use = slot if slot in slots else slots[-1]  # default: ultimo slot disponibile

    series = demand_cache.get("series", {}) or {}
    inbound_map = (series.get("inbound", {}) or {}).get(slot_use, {}) or {}
    abb_arr_map = (series.get("abb_arr", {}) or {}).get(slot_use, {}) or {}
    abb_par_map = (series.get("abb_par", {}) or {}).get(slot_use, {}) or {}

    def val_for(c: int) -> int:
        if view == "inbound":
            return int(inbound_map.get(c, 0) or 0)
        if view == "abb_arr":
            return int(abb_arr_map.get(c, 0) or 0)
        if view == "abb_par":
            return int(abb_par_map.get(c, 0) or 0)
        # mix
        return int(inbound_map.get(c, 0) or 0) + int(abb_arr_map.get(c, 0) or 0)

    corsie = []
    total_inbound = 0
    total_abb_arr = 0
    total_abb_par = 0
    total_mix = 0

    for c in range(CORSIA_MIN, CORSIA_MAX + 1):
        i = int(inbound_map.get(c, 0) or 0)
        a = int(abb_arr_map.get(c, 0) or 0)
        p = int(abb_par_map.get(c, 0) or 0)
        v = val_for(c)

        total_inbound += i
        total_abb_arr += a
        total_abb_par += p
        total_mix += (i + a)

        corsie.append({
            "corsia": c,
            "value": v,
            "inbound": i,
            "abb_arr": a,
            "abb_par": p,
        })

    def _top(arr_key: str) -> List[Dict[str, int]]:
        tmp = [{"corsia": x["corsia"], "value": int(x[arr_key])} for x in corsie]
        tmp = [t for t in tmp if t["value"] > 0]
        tmp.sort(key=lambda z: z["value"], reverse=True)
        return tmp[:10]

    top = {
        "inbound": _top("inbound"),
        "abb_arr": _top("abb_arr"),
        "abb_par": _top("abb_par"),
        "mix": [{"corsia": x["corsia"], "value": int(x["inbound"] + x["abb_arr"])} for x in corsie if (x["inbound"] + x["abb_arr"]) > 0][:0],
    }
    # ricostruisco mix top correttamente
    mix_top = [{"corsia": x["corsia"], "value": int(x["inbound"] + x["abb_arr"])} for x in corsie]
    mix_top = [t for t in mix_top if t["value"] > 0]
    mix_top.sort(key=lambda z: z["value"], reverse=True)
    top["mix"] = mix_top[:10]

    out = {
        "status": "ok",
        "meta": meta,
        "slot": slot_use,
        "view": view,
        "kpi": {
            "inbound": total_inbound,
            "abb_arr": total_abb_arr,
            "abb_par": total_abb_par,
            "mix": total_mix,
            "non_stok": int(len(demand_cache.get("non_stok", []) or [])),
        },
        "corsie": corsie,
        "top": top,
        "non_stok": demand_cache.get("non_stok", []) or [],
    }
    return _clean_json(out)
