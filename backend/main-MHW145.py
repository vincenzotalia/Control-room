from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, time as time_class
from typing import Optional, List, Dict, Any

import pandas as pd
from pydantic import BaseModel

from agora_analysis import run_agora_analysis, td_to_hours

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# CACHE IN MEMORIA
# ============================

_analysis_cache = None


def get_analysis():
    global _analysis_cache
    if _analysis_cache is None:
        _analysis_cache = run_agora_analysis()
    return _analysis_cache


def refresh_analysis():
    global _analysis_cache
    _analysis_cache = run_agora_analysis()
    return _analysis_cache


# ============================
# FUNZIONI DI SUPPORTO
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
    else:
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


# ============================
# TARGET E ATTESO DINAMICO (LISTE)
# ============================

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
    target_map = {row["Lista"]: float(row["target_lista"]) for _, row in df_lists.iterrows()}

    gb = (
        df_bucketed.groupby(["bucket", "Lista"], as_index=False)
        .agg(colli=("Colli", "sum"))
    )
    if gb.empty:
        return {}

    expected_by_bucket = {}
    for b, part in gb.groupby("bucket"):
        num = 0.0
        den = 0.0
        for _, r in part.iterrows():
            colli = _safe_float(r["colli"], 0.0)
            tgt = _safe_float(target_map.get(r["Lista"], 0.0), 0.0)
            if colli > 0 and tgt > 0:
                num += colli
                den += (colli / tgt)
        expected_by_bucket[b] = (num / den) if den > 0 else 0.0

    return expected_by_bucket


# ============================
# MODELLI
# ============================

class AssistantRequest(BaseModel):
    question: str


class AssistantResponse(BaseModel):
    answer: str


# ============================
# ENDPOINT BASE (mancavano)
# ============================

@app.get("/")
def root():
    return {"status": "ok", "message": "Warehouse control room backend attivo"}


@app.get("/kpi/overview")
def get_kpi_overview():
    return get_analysis()["kpi_overview"]


@app.get("/operators")
def get_operators():
    return get_analysis()["operators"]


@app.get("/layout")
def get_layout():
    res = get_analysis()
    return {"cells": res["layout"]["cells"], "operator_paths": res["operator_paths"]}


@app.post("/refresh")
def refresh():
    refresh_analysis()
    return {"status": "ok", "message": "Analisi ricalcolata"}


# ============================
# PATHS STATS
# ============================

@app.get("/paths/stats")
def get_paths_stats(
    operators: str = Query(..., description="Lista operatori, separati da virgola. Es: 101,102"),
    start: Optional[str] = Query(None, description="Ora inizio HH:MM"),
    end: Optional[str] = Query(None, description="Ora fine HH:MM"),
):
    try:
        result = get_analysis()
        df_pik = result["df_pik"]

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
        if start_t is not None or end_t is not None:
            time_mask = time_mask & df_pik["Ora_ts"].dt.time.apply(
                lambda t: _time_in_range_cross_midnight(t, start_t, end_t)
            )

        mask_rows = mask_base & time_mask
        df_sel = df_pik.loc[mask_rows].copy()

        missions = int(df_sel["Lista"].nunique())
        rows = int(len(df_sel))
        colli = int(df_sel["Colli"].sum())

        considera_mask = df_pik["Considera"].fillna(False).astype(bool)

        mask_time = (
            df_pik["Operatore"].isin(op_list)
            & considera_mask
            & (df_pik["Circuito"] != "SEN")
        ) & time_mask

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
            if df_op.empty:
                by_operator.append({
                    "operator": str(op),
                    "missions": 0,
                    "rows": 0,
                    "colli": 0,
                    "hours": 0.0,
                    "prod_colli_ora": 0.0
                })
                continue

            missions_op = int(df_op["Lista"].nunique())
            rows_op = int(len(df_op))
            colli_op = int(df_op["Colli"].sum())

            mask_time_op = (
                (df_pik["Operatore"] == op)
                & considera_mask
                & (df_pik["Circuito"] != "SEN")
            ) & time_mask

            hours_op = float(td_to_hours(df_pik.loc[mask_time_op, "TempoMov"]))
            prod_op = float(colli_op / hours_op) if hours_op > 0 else 0.0

            by_operator.append({
                "operator": str(op),
                "missions": missions_op,
                "rows": rows_op,
                "colli": colli_op,
                "hours": round(hours_op, 2),
                "prod_colli_ora": round(prod_op, 1)
            })

        return {"overall": overall, "by_operator": by_operator}

    except Exception as e:
        return {
            "overall": {"operators": [], "missions": 0, "rows": 0, "colli": 0, "hours": 0.0, "prod_colli_ora": 0.0},
            "by_operator": [],
            "error": str(e),
        }


# ============================
# TEST CARRELLISTI
# ============================

@app.get("/test/forklift")
def test_forklift():
    result = get_analysis()
    return {
        "status": "ok",
        "overview": result.get("forklift_kpi_overview", {}),
        "by_family": result.get("forklift_by_family", []),
        "by_movement_top10": result.get("forklift_by_movement", [])[:10],
        "debug": {
            "forklift_files": result.get("meta", {}).get("forklift_files", []),
            "forklift_rows": result.get("meta", {}).get("forklift_rows", 0),
        },
    }


# ============================
# FATIGUE (PICKING)
# ============================

@app.get("/fatigue")
def fatigue_curve(
    operator: int = Query(...),
    start: str = Query("06:00"),
    end: str = Query("22:00"),
    window_min: int = Query(60),
    min_net_minutes: int = Query(15),
):
    result = get_analysis()
    df_pik = result["df_pik"]
    kpi = result.get("kpi_overview", {}) or {}

    expected_base = _safe_float(
        kpi.get("target_units_per_hour") or kpi.get("prod_target_colli_ora") or 0.0
    )

    start_t = _parse_time_str(start)
    end_t = _parse_time_str(end)

    df = df_pik[
        (df_pik["Operatore"] == operator)
        & (df_pik["PallettizzatoSN_str"] == "n")
        & (df_pik["Circuito"] != "SEN")
        & df_pik["Ora_ts"].notna()
    ].copy()

    if df.empty:
        return {"status": "ok", "data": []}

    df["hhmm_time"] = df["Ora_ts"].dt.time
    df = df[df["hhmm_time"].apply(lambda t: _time_in_range_cross_midnight(t, start_t, end_t))]
    if df.empty:
        return {"status": "ok", "data": []}

    df["bucket"] = df["Ora_ts"].dt.floor(f"{window_min}min")

    g_colli = df.groupby("bucket")["Colli"].sum()

    considera_mask = df["Considera"].fillna(False).astype(bool)
    df_valid = df[considera_mask & df["TempoMov"].notna()]

    g_seconds = df_valid.groupby("bucket")["TempoMov"].apply(lambda s: s.dt.total_seconds().sum())

    expected_by_bucket = _expected_by_bucket_from_lists(df)

    out = []
    cum_colli = 0.0
    cum_hours = 0.0
    cum_expected = 0.0

    for b in sorted(set(g_colli.index) | set(g_seconds.index)):
        sec = float(g_seconds.get(b, 0.0))
        net_min = sec / 60.0
        if net_min < min_net_minutes:
            continue

        hours = sec / 3600.0
        colli = float(g_colli.get(b, 0.0))

        prod_real = colli / hours if hours > 0 else 0.0

        cum_colli += colli
        cum_hours += hours
        avg_to_now = cum_colli / cum_hours if cum_hours > 0 else 0.0

        expected = float(expected_by_bucket.get(b, 0.0)) or expected_base
        exp_colli = expected * hours
        cum_expected += exp_colli
        loss_cum = max(0.0, cum_expected - cum_colli)

        fatigue_pct = (prod_real / expected * 100.0) if expected > 0 else None

        out.append({
            "bucket": b.isoformat(),
            "label": _hhmm_from_bucket(b.isoformat()),
            "net_minutes": round(net_min, 1),
            "colli": int(colli),
            "prod_real": round(prod_real, 1),
            "avg_to_now": round(avg_to_now, 1),
            "expected": round(expected, 1),
            "fatigue_pct": round(fatigue_pct, 1) if fatigue_pct is not None else None,
            "loss_colli_cum": round(loss_cum, 1),
        })

    if not out:
        insight = ""
    else:
        avg_real = sum(r["prod_real"] for r in out) / len(out)
        avg_exp = sum(r["expected"] for r in out) / len(out) if len(out) > 0 else 0.0
        delta = avg_real - avg_exp

        if avg_exp <= 0:
            insight = f"Operatore {operator}: atteso non disponibile nel perimetro selezionato."
        elif delta >= 10:
            insight = (
                f"Operatore {operator}: sopra l’atteso di circa {delta:.1f} colli/ora. "
                "Trend complessivamente positivo."
            )
        elif delta <= -10:
            insight = (
                f"Operatore {operator}: sotto l’atteso di circa {abs(delta):.1f} colli/ora. "
                "Qui c’è un gap reale rispetto al target del mix liste."
            )
        else:
            insight = (
                f"Operatore {operator}: in linea con l’atteso (scarto ~{delta:.1f} colli/ora). "
                "Andamento complessivamente stabile."
            )

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

