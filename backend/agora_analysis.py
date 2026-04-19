# backend/agora_analysis.py
import glob
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime  # ✅ storico

import pandas as pd
import numpy as np
import threading
import time

from config import DATA_HISTORY_DIR, DATA_INPUT_DIR

# ============================
# PARAMETRI GLOBALI
# ============================

SOGLIA_MINUTI = 40  # soglia per AJ = "SI" (00:40:00)

# parametri distanze serpentina (come macro Excel)
PASSO = 0.87
LARGHEZZA_CORSIA = 3.6
PASSAGGIO_CORSIA = 2.6

# ============================
# STORICO (report_storico.xlsx)
# ============================

HISTORY_DIR = DATA_HISTORY_DIR
HISTORY_FILE = "report_storico.xlsx"

# ============================
# CONTROL ROOM (integrazione 2° script)
# ============================

# usato SOLO per eventuale foglio Layout_$$$_Distanze (qui NON esportiamo excel, ma lo teniamo pronto)
FOCUS_CIRCUIT = "$$$"

AREA_TIGROS = "TI"
AREA_SOGEGROS = "SO"

# Recupero: chiavi in TIPO LISTA (normalizzato uppercase)
RECUPERO_KEYS = {"LISTA DI RECUPERO", "RECUPERO"}

# Circuiti speciali letti da colonna CIRCUITO (normalizzato uppercase)
CIRCUIT_MAP = {
    "ESP": "ESPOSITORI",
    "STG": "STAGIONALI",
    "PRO": "PROMO",
    "DPL": "DPL",
    "PCQ": "PCQ",
    "$$$": "LAYOUT",
}

AREA_ORDER = ["TIGROS", "SOGEGROS", "ALTRO_AREA"]
CIRCUIT_ORDER = ["ESPOSITORI", "STAGIONALI", "PROMO", "DPL", "PCQ", "LAYOUT", "ALTRO_CIRCUITO"]
EVENT_ORDER = ["RECUPERO", "RITORNI"]

# ============================
# CACHE (base + lazy blocks)
# ============================

_AGORA_CACHE: Optional[Dict[str, Any]] = None
_AGORA_CACHE_INPUT_DIR: Optional[Path] = None
_AGORA_CACHE_SIGNATURE: Optional[Tuple] = None

# opzionale: evita doppio calcolo in parallelo se partono più chiamate insieme
_ANALYSIS_LOCK = threading.Lock()

# ============================
# UTILS
# ============================


def _log(msg: str):
    # Commenta questa riga se non vuoi log
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def td_to_hours(td_series: pd.Series) -> float:
    """Converte una serie di Timedelta in ore (float)."""
    if td_series is None or td_series.empty:
        return 0.0
    return td_series.dt.total_seconds().sum() / 3600.0


def trova_colonna(df: pd.DataFrame, possibili_nomi, descrizione: str) -> str:
    mappa = {c.strip().lower(): c for c in df.columns}
    for nome in possibili_nomi:
        key = nome.strip().lower()
        if key in mappa:
            return mappa[key]
    raise KeyError(
        f"Colonna per '{descrizione}' non trovata. Nomi cercati: {possibili_nomi}. "
        f"Colonne presenti: {list(df.columns)}"
    )


# ============================
# STORICO - FUNZIONI
# ============================

def _find_sheet_case_insensitive(xls: pd.ExcelFile, wanted: str) -> str | None:
    wanted_l = wanted.strip().lower()
    for n in xls.sheet_names:
        if n.strip().lower() == wanted_l:
            return n
    return None


def load_history_report(history_path: Path) -> dict:
    """
    Legge report_storico.xlsx e restituisce:
    - storico_giornaliero (Data parse + colonne)
    """
    if not history_path.exists():
        return {"status": "missing", "path": str(history_path)}

    try:
        xls = pd.ExcelFile(history_path)
    except Exception as e:
        return {"status": "error", "path": str(history_path), "message": f"Impossibile aprire Excel: {e}"}

    sheet = _find_sheet_case_insensitive(xls, "Storico_Giornaliero")
    if not sheet:
        return {
            "status": "error",
            "path": str(history_path),
            "message": "Sheet 'Storico_Giornaliero' non trovato nel report_storico.xlsx",
            "sheets": xls.sheet_names,
        }

    try:
        df = pd.read_excel(history_path, sheet_name=sheet)
    except Exception as e:
        return {"status": "error", "path": str(history_path), "message": f"Errore lettura sheet storico: {e}"}

    if df is None or df.empty:
        return {"status": "empty", "path": str(history_path)}

    if "Data" in df.columns:
        df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
    else:
        df["Data_dt"] = pd.NaT

    df = df[df["Data_dt"].notna()].copy()
    df = df.sort_values("Data_dt").reset_index(drop=True)

    return {
        "status": "ok",
        "path": str(history_path),
        "days": int(len(df)),
        "from": df["Data_dt"].min().strftime("%Y-%m-%d"),
        "to": df["Data_dt"].max().strftime("%Y-%m-%d"),
        "storico_giornaliero": df,
    }


def build_history_comparison(history_df: pd.DataFrame, kpi_now: dict, last_n_days: int = 14) -> dict:
    """
    Confronto semplice: media ultimi N giorni vs KPI correnti.
    NON rompe nulla se mancano colonne: torna None / status.
    """
    if history_df is None or history_df.empty:
        return {"status": "empty"}

    df = history_df.copy().sort_values("Data_dt")
    if last_n_days > 0:
        df = df.tail(int(last_n_days))

    col_colli = "colli_totali" if "colli_totali" in df.columns else None
    col_ore = "tempo_netto_ore" if "tempo_netto_ore" in df.columns else None

    baseline = {}

    if col_colli and col_ore:
        ore = pd.to_numeric(df[col_ore], errors="coerce")
        colli = pd.to_numeric(df[col_colli], errors="coerce")
        prod = (colli / ore).replace([np.inf, -np.inf], np.nan)
        m = np.nanmean(prod.values) if len(prod) else np.nan
        baseline["units_per_hour_mean"] = float(m) if np.isfinite(m) else None
    else:
        baseline["units_per_hour_mean"] = None

    if "colli_per_lista" in df.columns:
        baseline["colli_per_lista_mean"] = float(pd.to_numeric(df["colli_per_lista"], errors="coerce").mean())
    else:
        baseline["colli_per_lista_mean"] = None

    # opzionale: se nello storico hai una colonna distanza
    if "dist_pulita_mean_m" in df.columns:
        baseline["dist_pulita_mean_m"] = float(pd.to_numeric(df["dist_pulita_mean_m"], errors="coerce").mean())
    else:
        baseline["dist_pulita_mean_m"] = None

    now_units = float(kpi_now.get("units_per_hour", 0.0) or 0.0)
    now_lista = float(kpi_now.get("colli_per_lista", 0.0) or 0.0)

    delta = {}
    if baseline["units_per_hour_mean"] is not None:
        delta["units_per_hour_vs_mean"] = round(now_units - baseline["units_per_hour_mean"], 2)
    else:
        delta["units_per_hour_vs_mean"] = None

    if baseline["colli_per_lista_mean"] is not None:
        delta["colli_per_lista_vs_mean"] = round(now_lista - baseline["colli_per_lista_mean"], 2)
    else:
        delta["colli_per_lista_vs_mean"] = None

    return {
        "status": "ok",
        "window_days": int(last_n_days),
        "baseline": baseline,
        "current": {
            "units_per_hour": round(now_units, 2),
            "colli_per_lista": round(now_lista, 2),
        },
        "delta": delta,
    }


# ============================
# PARAM (stile foglio PARAM)
# ============================

param_rows = [
    {"MediaMin": 0,   "MediaMax": 40,  "Prod_OK": 75,  "Prod_Att": 50,  "Prod_Crit": 0, "OreMin": 1.0},
    {"MediaMin": 40,  "MediaMax": 80,  "Prod_OK": 135, "Prod_Att": 110, "Prod_Crit": 0, "OreMin": 1.0},
    {"MediaMin": 80,  "MediaMax": 120, "Prod_OK": 165, "Prod_Att": 140, "Prod_Crit": 0, "OreMin": 1.0},
    {"MediaMin": 120, "MediaMax": 160, "Prod_OK": 210, "Prod_Att": 180, "Prod_Crit": 0, "OreMin": 1.5},
    {"MediaMin": 160, "MediaMax": 200, "Prod_OK": 230, "Prod_Att": 190, "Prod_Crit": 0, "OreMin": 1.5},
    {"MediaMin": 200, "MediaMax": 999, "Prod_OK": 260, "Prod_Att": 210, "Prod_Crit": 0, "OreMin": 2.0},
]


def soglia_ok_effettiva(media_lista: float):
    riga_param = None
    for pr in param_rows:
        if pr["MediaMin"] <= media_lista <= pr["MediaMax"]:
            riga_param = pr
            break
    if riga_param is None:
        return None

    sogliaOK = riga_param["Prod_OK"]

    # regole speciali
    if 75 <= media_lista <= 90:
        return 139.0
    elif media_lista > 90:
        return 144.0
    else:
        return sogliaOK


# ============================
# FILES: signature + list
# ============================

def _list_input_files(resolved_dir: Path) -> list[str]:
    pattern = str(resolved_dir / "*.*")
    return [
        f for f in glob.glob(pattern)
        if Path(f).suffix.lower() in (".xlsx", ".xlsm", ".xls", ".csv")
        and not Path(f).name.startswith("~$")
    ]


def _signature(files: list[str]) -> Tuple:
    """
    Firma dei file: se cambia uno tra mtime/size, si invalida la cache in memoria.
    """
    sig = []
    for f in sorted(files):
        p = Path(f)
        try:
            st = p.stat()
            sig.append((str(p.resolve()), int(st.st_mtime_ns), int(st.st_size)))
        except Exception:
            sig.append((str(p.resolve()), 0, 0))
    return tuple(sig)


# ============================
# PARQUET CACHE (Excel -> Parquet)
# ============================

def _cache_dir_for_file(p: Path) -> Path:
    d = p.parent / ".cache"
    d.mkdir(exist_ok=True)
    return d


def _hash_for_file(p: Path) -> str:
    st = p.stat()
    return f"{st.st_mtime_ns}_{st.st_size}"


def _parquet_path(p: Path) -> Path:
    return _cache_dir_for_file(p) / f"{p.stem}.parquet"


def _hash_path(p: Path) -> Path:
    return _cache_dir_for_file(p) / f"{p.stem}.hash"


def _sanitize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rende i dati più "parquet-friendly" senza stravolgere la logica:
    - converte le colonne object in stringhe pulite (evita mix int/str/bytes)
    """
    df2 = df.copy()

    obj_cols = df2.select_dtypes(include=["object"]).columns
    for c in obj_cols:
        df2[c] = (
            df2[c]
            .astype(str)
            .str.strip()
            .replace({"nan": "", "None": ""})
        )

    return df2


def read_any_table(path: str | Path) -> pd.DataFrame:
    """
    Lettura intelligente:
    - Excel: usa cache parquet se valida (molto più veloce)
    - CSV: lettura diretta
    """
    p = Path(path)
    ext = p.suffix.lower()

    # ============================
    # EXCEL -> Parquet cache
    # ============================
    if ext in (".xlsx", ".xlsm", ".xls"):
        pq = _parquet_path(p)
        hp = _hash_path(p)
        cur_hash = _hash_for_file(p)

        cache_valid = False
        if pq.exists() and hp.exists():
            try:
                saved_hash = hp.read_text(encoding="utf-8").strip()
                cache_valid = (saved_hash == cur_hash)
            except Exception:
                cache_valid = False

        if cache_valid:
            try:
                _log(f"⚡ Parquet cache: {p.name}")
                return pd.read_parquet(pq)
            except Exception as e:
                _log(f"⚠️ Cache parquet fallita, rileggo Excel: {e}")

        _log(f"📖 Excel: {p.name} (prima volta crea cache)")
        if ext in (".xlsx", ".xlsm"):
            df = pd.read_excel(p, engine="openpyxl")
        else:
            df = pd.read_excel(p, engine="xlrd")

        try:
            df_pq = _sanitize_for_parquet(df)
            df_pq.to_parquet(pq, index=False)  # richiede pyarrow o fastparquet
            hp.write_text(cur_hash, encoding="utf-8")
            _log(f"✅ Cache creata: {pq.name}")
        except Exception as e:
            _log(f"⚠️ Impossibile creare cache parquet (installa pyarrow): {e}")

        return df

    # ============================
    # CSV
    # ============================
    if ext == ".csv":
        return pd.read_csv(
            p,
            sep=";",
            engine="python",
            encoding="utf-8",
            dtype=str
        ).fillna("")

    # ============================
    # altri casi
    # ============================
    return pd.read_excel(p)


# ============================
# CARRELLISTI (tuoi)
# ============================

KARDEX_TP = "STOCCAGGIO ARMADIO VERTICALE"
ABBASS_TP = {"RIPRIST.TOT DA SCORTA A PRESA", "RIPRIST.PRZ DA SCORTA A PRESA"}
STOK_TP = {"RISTOCC. DOPO RIPR. PARZIALE", "STOCCAGGIO IN SCORTA", "STOCCAGGIO IN PRESA"}


def _safe_time_to_str(x) -> str:
    if pd.isna(x):
        return ""
    if hasattr(x, "strftime"):
        try:
            return x.strftime("%H:%M:%S")
        except Exception:
            pass
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return ""
    s = s.replace(".", ":")
    if len(s) == 5 and s.count(":") == 1:
        s = s + ":00"
    return s


def _safe_date_to_str(x) -> str:
    if pd.isna(x):
        return ""
    if hasattr(x, "strftime"):
        try:
            return x.strftime("%d/%m/%Y")
        except Exception:
            pass
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return ""
    return s


def _norm_tp(s: str) -> str:
    return str(s).strip().upper()


def _tp_category(tp_norm: str) -> str:
    if tp_norm == _norm_tp(KARDEX_TP):
        return "KARDEX"
    if tp_norm in {_norm_tp(x) for x in ABBASS_TP}:
        return "ABBASSAMENTI"
    if tp_norm in {_norm_tp(x) for x in STOK_TP}:
        return "STOK"
    return "ALTRO"


def build_forklift_df(df_raw_fk: pd.DataFrame) -> pd.DataFrame:
    df_fk = df_raw_fk.copy()

    col_OP = trova_colonna(df_fk, ["Cons:Ope Rad.", "Cons:Ope Rad", "CONS:OPE RAD.", "CONS:OPE RAD"], "Cons:Ope Rad.")
    col_ESEC_DT = trova_colonna(df_fk, ["ESEC.Dt. Ini", "ESEC.Dt Ini", "ESEC.Dt. Ini "], "ESEC.Dt. Ini")
    col_ESEC_ORA = trova_colonna(df_fk, ["ESEC.Ora Ini", "ESEC.OraIni", "ESEC. Ora Ini"], "ESEC.Ora Ini")
    col_TP = trova_colonna(df_fk, ["Tp Movimento", "TP MOVIMENTO", "TP Movimento"], "Tp Movimento")

    out = pd.DataFrame()
    out["Operatore"] = pd.to_numeric(df_fk[col_OP], errors="coerce").fillna(0).astype(int)
    out["ESEC_dt_raw"] = df_fk[col_ESEC_DT]
    out["ESEC_ora_raw"] = df_fk[col_ESEC_ORA]
    out["TpMov_raw"] = df_fk[col_TP].astype(str)

    d = out["ESEC_dt_raw"].apply(_safe_date_to_str)
    t = out["ESEC_ora_raw"].apply(_safe_time_to_str)
    out["exec_ts"] = pd.to_datetime(d + " " + t, errors="coerce", dayfirst=True)

    out["Data_dt"] = pd.to_datetime(d, errors="coerce", dayfirst=True)
    out["Data"] = out["Data_dt"].dt.date

    out["TpMov"] = out["TpMov_raw"].map(_norm_tp)
    out["Categoria"] = out["TpMov"].map(_tp_category)

    out = out.sort_values(["Operatore", "Data_dt", "exec_ts"], na_position="last").reset_index(drop=True)

    out["delta_td"] = out.groupby(["Operatore", "Data"])["exec_ts"].diff()
    out["delta_sec"] = out["delta_td"].dt.total_seconds()
    out["delta_h"] = out["delta_sec"] / 3600.0

    soglia_sec = SOGLIA_MINUTI * 60
    out["delta_valid"] = out["delta_sec"].notna() & (out["delta_sec"] > 0) & (out["delta_sec"] <= soglia_sec)
    out.loc[~out["delta_valid"], "delta_h"] = pd.NA

    out["Pallet"] = 1
    return out


def _kpi_block(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0}
    pallet = int(len(df))
    ore = float(df["delta_h"].dropna().sum()) if "delta_h" in df.columns else 0.0
    pph = (pallet / ore) if ore > 0 else 0.0
    return {"pallet": pallet, "ore": round(ore, 2), "pallet_ora": round(pph, 1)}


def forklift_kpi_by_operator(df_fk: pd.DataFrame):
    if df_fk is None or df_fk.empty:
        empty_overview = {
            "pallet_totali": 0, "ore_totali": 0.0, "pallet_ora": 0.0,
            "kardex": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
            "stok": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
            "abbassamenti": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
        }
        return empty_overview, []

    df_kardex = df_fk[df_fk["Categoria"] == "KARDEX"].copy()
    df_stok = df_fk[df_fk["Categoria"] == "STOK"].copy()
    df_abb = df_fk[df_fk["Categoria"] == "ABBASSAMENTI"].copy()

    k_kardex = _kpi_block(df_kardex)
    k_stok = _kpi_block(df_stok[df_stok["Operatore"] != 0])
    k_abb = _kpi_block(df_abb[df_abb["Operatore"] != 0])

    df_global = df_fk[(df_fk["Categoria"] != "KARDEX") & (df_fk["Operatore"] != 0)].copy()
    k_global = _kpi_block(df_global)

    overview = {
        "pallet_totali": k_global["pallet"],
        "ore_totali": k_global["ore"],
        "pallet_ora": k_global["pallet_ora"],
        "kardex": k_kardex,
        "stok": k_stok,
        "abbassamenti": k_abb,
        # compatibilità vecchi nomi
        "colli_totali": k_global["pallet"],
        "movimenti": k_global["pallet"],
        "prod_colli_ora": k_global["pallet_ora"],
    }

    rows = []
    for op, g in df_fk.groupby("Operatore"):
        op = int(op)
        g_kardex = g[g["Categoria"] == "KARDEX"]
        g_stok = g[(g["Categoria"] == "STOK") & (g["Operatore"] != 0)]
        g_abb = g[(g["Categoria"] == "ABBASSAMENTI") & (g["Operatore"] != 0)]
        g_global = g[(g["Categoria"] != "KARDEX") & (g["Operatore"] != 0)]

        kk = _kpi_block(g_kardex)
        ks = _kpi_block(g_stok)
        ka = _kpi_block(g_abb)
        kg = _kpi_block(g_global)

        if op == 0 and kk["pallet"] == 0:
            continue

        rows.append({
            "name": str(op),
            "pallet": kg["pallet"],
            "ore": kg["ore"],
            "pallet_ora": kg["pallet_ora"],
            "kardex": kk,
            "stok": ks,
            "abbassamenti": ka,
            "colli": kg["pallet"],
            "movimenti": kg["pallet"],
            "units_per_hour": kg["pallet_ora"],
        })

    rows = sorted(rows, key=lambda r: (r["pallet_ora"] or 0), reverse=True)
    return overview, rows


# ============================
# VETTORIZZAZIONI (collega) adattate
# ============================

def _compute_ritorno_vectorized(df_pik: pd.DataFrame) -> pd.Series:
    """
    RITORNO = "Sì" sull'ultima riga della lista se la corsia finale > corsia minima della lista.
    Restituisce serie di stringhe "Sì"/"No" lunga quanto df_pik.
    """
    df = df_pik[["Data", "Operatore", "Lista", "Corsia_num"]].copy()
    key = df["Data"].astype(str) + "_" + df["Operatore"].astype(str) + "_" + df["Lista"].astype(str)

    valid_corsia = df["Corsia_num"].where(df["Corsia_num"] > 0)
    min_corsia = valid_corsia.groupby(key).transform("min")

    is_last = ~key.duplicated(keep="last")

    ritorno_bool = (
        is_last &
        df["Corsia_num"].notna() &
        (df["Corsia_num"] > min_corsia)
    )

    out = pd.Series("No", index=df_pik.index, dtype="object")
    out.loc[ritorno_bool.values] = "Sì"
    return out


def _compute_distances_vectorized(df_pik: pd.DataFrame) -> pd.Series:
    """
    dist_prev vettorizzato:
    distanza tra riga e precedente SOLO se stessa (Data,Operatore,Lista).
    """
    df = df_pik.sort_values(["Data_dt", "Operatore", "Lista", "Ora_ts"]).reset_index()
    idx = df["index"]

    c1 = df["Corsia_num"].shift(1)
    p1 = df["Posto_num"].shift(1)
    c2 = df["Corsia_num"]
    p2 = df["Posto_num"]

    same_task = (
        (df["Data"] == df["Data"].shift(1)) &
        (df["Operatore"] == df["Operatore"].shift(1)) &
        (df["Lista"] == df["Lista"].shift(1))
    )

    same_lane = (c1 == c2)
    same_parity = ((p1 % 2) == (p2 % 2))

    dist_same_lane = np.where(
        same_parity,
        np.abs(p1 - p2) / 2.0 * PASSO,
        LARGHEZZA_CORSIA
    )

    dir1_down = (c1 % 2 == 0)
    dir2_down = (c2 % 2 == 0)

    fine_c1 = np.where(dir1_down, 1, 256)
    inizio_c2 = np.where(dir2_down, 256, 1)

    d1 = np.abs(p1 - fine_c1) / 2.0 * PASSO
    d2 = np.abs(c1 - c2) * PASSAGGIO_CORSIA
    d3 = np.abs(p2 - inizio_c2) / 2.0 * PASSO

    dist_diff_lane = d1 + d2 + d3
    dist = np.where(same_lane, dist_same_lane, dist_diff_lane)

    valid = (
        same_task &
        c1.notna() & c2.notna() &
        p1.notna() & p2.notna()
    )

    dist_prev_sorted = np.zeros(len(df), dtype="float64")
    dist_prev_sorted[valid.values] = dist[valid.values]

    out = pd.Series(0.0, index=df_pik.index, dtype="float64")
    out.loc[idx.values] = dist_prev_sorted
    return out


# ============================
# CONTROL ROOM (da dist_prev) - FUNZIONI
# ============================

def _norm_upper_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.upper()


def _is_recupero_tipo(tipo_lista_raw: pd.Series) -> pd.Series:
    x = _norm_upper_series(tipo_lista_raw)
    return x.isin(RECUPERO_KEYS)


def _make_area_bucket(area_u: pd.Series) -> pd.Series:
    out = pd.Series("ALTRO_AREA", index=area_u.index, dtype="object")
    out.loc[area_u.eq(AREA_TIGROS)] = "TIGROS"
    out.loc[area_u.eq(AREA_SOGEGROS)] = "SOGEGROS"
    return out


def _make_circuit_bucket(circ_u: pd.Series) -> pd.Series:
    return circ_u.map(lambda x: CIRCUIT_MAP.get(x, "ALTRO_CIRCUITO"))


def _control_room_from_dist(dist_all: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Usa SOLO dist_prev > 0.
    Ritorna:
    - wide: 1 riga per data con colonne sia AREA_* che CIRCUIT_* che EVENTI
    - detail: long (Data, Dimensione, Bucket, mean_m, steps, pct_steps)
    """
    df = dist_all.copy()
    df = df[df["dist_prev"] > 0].copy()
    if df.empty:
        cols = ["Data", "Distanza_media_m", "Steps_tot"]
        for b in AREA_ORDER:
            cols += [f"{b}_mean_m", f"{b}_pct"]
        for b in CIRCUIT_ORDER:
            cols += [f"{b}_mean_m", f"{b}_pct"]
        for b in EVENT_ORDER:
            cols += [f"{b}_mean_m", f"{b}_pct"]

        return (
            pd.DataFrame(columns=cols),
            pd.DataFrame(columns=["Data", "Dimensione", "Bucket", "mean_m", "steps", "Steps_tot", "pct_steps"])
        )

    gtot = df.groupby("Data")["dist_prev"]
    daily = pd.DataFrame({
        "Data": gtot.mean().index,
        "Distanza_media_m": gtot.mean().values,
        "Steps_tot": gtot.size().values.astype(int),
    })
    daily["Distanza_media_m"] = daily["Distanza_media_m"].astype(float).round(2)

    df["AREA_BUCKET"] = _make_area_bucket(df["AreaUscita_u"])
    df["CIRCUIT_BUCKET"] = _make_circuit_bucket(df["Circuito_u"])

    df["EVENT_RECUPERO"] = df["is_recupero"].fillna(False).astype(bool)
    df["EVENT_RITORNI"] = df["ritorno"].fillna(False).astype(bool)

    def agg_and_pivot(bucket_col: str, bucket_order: list[str], prefix: str):
        gb = df.groupby(["Data", bucket_col])["dist_prev"].agg(["mean", "size"]).reset_index()
        gb.rename(columns={"mean": "mean_m", "size": "steps", bucket_col: "Bucket"}, inplace=True)
        gb["mean_m"] = gb["mean_m"].astype(float).round(2)
        gb["steps"] = gb["steps"].astype(int)

        gb = gb.merge(daily[["Data", "Steps_tot"]], on="Data", how="left")
        gb["pct_steps"] = np.where(gb["Steps_tot"] > 0, gb["steps"] / gb["Steps_tot"] * 100.0, 0.0).round(1)

        mean_w = gb.pivot_table(index="Data", columns="Bucket", values="mean_m", aggfunc="first") \
            .rename(columns=lambda c: f"{c}_mean_m")
        pct_w = gb.pivot_table(index="Data", columns="Bucket", values="pct_steps", aggfunc="first") \
            .rename(columns=lambda c: f"{c}_pct")

        wide = mean_w.join(pct_w, how="outer")

        cols = []
        for b in bucket_order:
            cols += [f"{b}_mean_m", f"{b}_pct"]
        for c in cols:
            if c not in wide.columns:
                wide[c] = np.nan
        wide = wide[cols].copy()

        long = gb.copy()
        long["Dimensione"] = prefix
        long = long[["Data", "Dimensione", "Bucket", "mean_m", "steps", "Steps_tot", "pct_steps"]].copy()

        return wide, long

    # AREA
    area_w, area_long = agg_and_pivot("AREA_BUCKET", AREA_ORDER, "AREA")
    # CIRCUITO
    circ_w, circ_long = agg_and_pivot("CIRCUIT_BUCKET", CIRCUIT_ORDER, "CIRCUITO")

    # EVENTI (separati)
    event_rows = []
    for ev_name, ev_mask in [("RECUPERO", df["EVENT_RECUPERO"]), ("RITORNI", df["EVENT_RITORNI"])]:
        dfe = df.loc[ev_mask].copy()
        if dfe.empty:
            continue
        ge = dfe.groupby("Data")["dist_prev"].agg(["mean", "size"]).reset_index()
        ge["Bucket"] = ev_name
        ge.rename(columns={"mean": "mean_m", "size": "steps"}, inplace=True)
        ge["mean_m"] = ge["mean_m"].astype(float).round(2)
        ge["steps"] = ge["steps"].astype(int)
        ge = ge.merge(daily[["Data", "Steps_tot"]], on="Data", how="left")
        ge["pct_steps"] = np.where(ge["Steps_tot"] > 0, ge["steps"] / ge["Steps_tot"] * 100.0, 0.0).round(1)
        ge["Dimensione"] = "EVENTO"
        event_rows.append(ge)

    if event_rows:
        ev = pd.concat(event_rows, ignore_index=True)
        ev_mean = ev.pivot_table(index="Data", columns="Bucket", values="mean_m", aggfunc="first") \
            .rename(columns=lambda c: f"{c}_mean_m")
        ev_pct = ev.pivot_table(index="Data", columns="Bucket", values="pct_steps", aggfunc="first") \
            .rename(columns=lambda c: f"{c}_pct")
        ev_w = ev_mean.join(ev_pct, how="outer")

        ev_cols = []
        for b in EVENT_ORDER:
            ev_cols += [f"{b}_mean_m", f"{b}_pct"]
        for c in ev_cols:
            if c not in ev_w.columns:
                ev_w[c] = np.nan
        ev_w = ev_w[ev_cols].copy()

        ev_long = ev[["Data", "Dimensione", "Bucket", "mean_m", "steps", "Steps_tot", "pct_steps"]].copy()
    else:
        ev_cols = []
        for b in EVENT_ORDER:
            ev_cols += [f"{b}_mean_m", f"{b}_pct"]
        ev_w = pd.DataFrame(index=daily["Data"]).copy()
        for c in ev_cols:
            ev_w[c] = np.nan
        ev_long = pd.DataFrame(columns=["Data", "Dimensione", "Bucket", "mean_m", "steps", "Steps_tot", "pct_steps"])

    wide = (
        daily.set_index("Data")
        .join(area_w, how="left")
        .join(circ_w, how="left")
        .join(ev_w, how="left")
        .reset_index()
        .sort_values("Data")
        .reset_index(drop=True)
    )

    detail = pd.concat([area_long, circ_long, ev_long], ignore_index=True)
    detail = detail.sort_values(["Data", "Dimensione", "Bucket"]).reset_index(drop=True)

    return wide, detail


# ============================
# LAZY BLOCKS (tuoi, veloci)
# ============================

def _build_operator_paths(df_pik: pd.DataFrame) -> list[dict]:
    """
    Versione veloce: itertuples() invece di iterrows().
    """
    mask_anim = (
        df_pik["Corsia_num"].notna() &
        df_pik["Posto_num"].notna() &
        (df_pik["PallettizzatoSN_str"] == "n") &
        (df_pik["Circuito"] != "SEN")
    )
    df_anim = df_pik.loc[mask_anim].copy().sort_values(["Data_dt", "Ora_ts"])

    operator_paths: list[dict] = []
    for op, g in df_anim.groupby("Operatore"):
        steps = []
        for r in g.itertuples(index=False):
            lane = getattr(r, "Corsia_num", None)
            pos = getattr(r, "Posto_num", None)
            if pd.isna(lane) or pd.isna(pos):
                continue

            step = {"lane": int(lane), "pos": float(pos)}

            lista = getattr(r, "Lista", None)
            colli_row = getattr(r, "Colli", 0)
            tempo_mov = getattr(r, "TempoMov", pd.NaT)
            ora_ts = getattr(r, "Ora_ts", pd.NaT)
            data_dt = getattr(r, "Data_dt", pd.NaT)

            if pd.notna(lista):
                try:
                    step["lista"] = int(lista)
                except Exception:
                    step["lista"] = str(lista)

            try:
                step["colli"] = int(colli_row)
            except Exception:
                step["colli"] = 0

            if pd.notna(tempo_mov):
                try:
                    step["tempo_mov_sec"] = int(tempo_mov.total_seconds())
                except Exception:
                    step["tempo_mov_sec"] = 0
            else:
                step["tempo_mov_sec"] = 0

            if pd.notna(ora_ts):
                step["time"] = ora_ts.isoformat()
            if pd.notna(data_dt):
                step["date"] = data_dt.isoformat()

            steps.append(step)

        if len(steps) >= 2:
            operator_paths.append({"operator": str(int(op)), "steps": steps})

    return operator_paths


def _build_layout(df_pik: pd.DataFrame, recupero_by_lane: dict, issues_by_lane: dict) -> dict:
    mask_layout = (
        df_pik["Corsia_num"].notna() &
        (df_pik["PallettizzatoSN_str"] == "n") &
        (df_pik["AreaUscita_clean"] != "KAR") &
        (df_pik["Circuito"] != "SEN")
    )
    df_layout = df_pik.loc[mask_layout].copy()
    df_layout["Corsia_int"] = df_layout["Corsia_num"].astype(int)

    colli_per_corsia = df_layout.groupby("Corsia_int")["Colli"].sum().sort_index()
    righe_per_corsia = df_layout.groupby("Corsia_int").size()
    ritorni_per_corsia = (
        df_layout[df_layout["RITORNO"] == "Sì"]
        .groupby("Corsia_int")["RITORNO"]
        .size()
    )
    max_colli_corsia = colli_per_corsia.max() if not colli_per_corsia.empty else 1

    cells = []
    x = 0.0
    for corsia, colli_corsia in colli_per_corsia.items():
        righe_c = int(righe_per_corsia.get(corsia, 0))
        ritorni_c = int(ritorni_per_corsia.get(corsia, 0))
        recuperi_c = int(recupero_by_lane.get(corsia, 0))
        issues_c = int(issues_by_lane.get(corsia, ritorni_c + recuperi_c))
        return_rate_c = ritorni_c / righe_c if righe_c > 0 else 0.0
        intensity = colli_corsia / max_colli_corsia if max_colli_corsia > 0 else 0.0

        cells.append({
            "id": f"C{int(corsia)}",
            "x": x, "y": 0, "w": 0.6, "h": 8,
            "type": "rack",
            "label": int(corsia),
            "colli": int(colli_corsia),
            "intensity": float(round(intensity, 3)),
            "return_count": ritorni_c,
            "recupero_count": recuperi_c,
            "issues_total": issues_c,
            "return_rate": float(round(return_rate_c, 4)),
        })
        x += 0.7

    return {"cells": cells}


# ============================
# ANALISI PRINCIPALE (base + lazy)
# ============================

def run_agora_analysis(
    input_dir: str | Path | None = None,
    force: bool = False,
    include_paths: bool = False,
    include_layout: bool = False,
) -> dict:
    """
    Esegue l'analisi base e, opzionalmente, i blocchi pesanti:
    - include_paths=True -> operator_paths
    - include_layout=True -> layout

    Cache:
    - si invalida se cambiano i file (mtime/size)
    """
    global _AGORA_CACHE, _AGORA_CACHE_INPUT_DIR, _AGORA_CACHE_SIGNATURE

    resolved_dir = DATA_INPUT_DIR if input_dir is None else Path(input_dir).resolve()

    files = _list_input_files(resolved_dir)
    if not files:
        raise RuntimeError(f"Nessun file trovato in {resolved_dir}")

    sig = _signature(files)

    # ✅ se cache valida, restituisci e calcola eventuali lazy mancanti
    if (not force) and (_AGORA_CACHE is not None) and (_AGORA_CACHE_INPUT_DIR == resolved_dir) and (_AGORA_CACHE_SIGNATURE == sig):
        if include_paths and _AGORA_CACHE.get("operator_paths") is None:
            _AGORA_CACHE["operator_paths"] = _build_operator_paths(_AGORA_CACHE["df_pik"])
        if include_layout and _AGORA_CACHE.get("layout") is None:
            _AGORA_CACHE["layout"] = _build_layout(
                _AGORA_CACHE["df_pik"],
                _AGORA_CACHE.get("_recupero_by_lane", {}) or {},
                _AGORA_CACHE.get("_issues_by_lane", {}) or {},
            )
        return _AGORA_CACHE

    # 🔒 lock: evita che due chiamate partano insieme e rifacciano tutta l’analisi
    with _ANALYSIS_LOCK:
        # ricontrollo cache (magari nel frattempo è stata calcolata)
        if (not force) and (_AGORA_CACHE is not None) and (_AGORA_CACHE_INPUT_DIR == resolved_dir) and (_AGORA_CACHE_SIGNATURE == sig):
            if include_paths and _AGORA_CACHE.get("operator_paths") is None:
                _AGORA_CACHE["operator_paths"] = _build_operator_paths(_AGORA_CACHE["df_pik"])
            if include_layout and _AGORA_CACHE.get("layout") is None:
                _AGORA_CACHE["layout"] = _build_layout(
                    _AGORA_CACHE["df_pik"],
                    _AGORA_CACHE.get("_recupero_by_lane", {}) or {},
                    _AGORA_CACHE.get("_issues_by_lane", {}) or {},
                )
            return _AGORA_CACHE

        # ============================
        # 1) LETTURA FILE
        # ============================
        forklift_files = [f for f in files if Path(f).stem.lower().startswith("carrellisti")]
        picking_files = [f for f in files if f not in forklift_files]

        if not picking_files:
            raise RuntimeError(
                f"Nessun file picking trovato in {resolved_dir}. "
                f"Metti almeno un file picking (.xlsx/.xlsm/.xls/.csv) e (opzionale) carrellisti.*"
            )

        dfs = [read_any_table(p) for p in picking_files]
        df = pd.concat(dfs, ignore_index=True)

        # ============================
        # 2) PICKING - colonne
        # ============================
        col_DATA = trova_colonna(df, ["DATA PREPARAZIONE", "DATA PREPARAZ."], "DATA PREPARAZIONE")
        col_ORA = trova_colonna(df, ["ORA PREP:", "ORA PREP.", "ORA PREP"], "ORA PREP")
        col_OPER = trova_colonna(df, ["OPERATORE"], "OPERATORE")
        col_CIRC = trova_colonna(df, ["CIRCUITO"], "CIRCUITO")
        col_AREA = trova_colonna(df, ["AREA USCITA"], "AREA USCITA")
        col_COLL = trova_colonna(df, ["COLLI PREPARATI"], "COLLI PREPARATI")
        col_LISTA = trova_colonna(df, ["NUMERO LISTA"], "NUMERO LISTA")
        col_CORSIA = trova_colonna(df, ["CORSIA"], "CORSIA")
        col_POSTO = trova_colonna(df, ["POSTO"], "POSTO")
        col_TIPOLISTA = trova_colonna(df, ["TIPO LISTA"], "TIPO LISTA")
        col_PALSN = trova_colonna(df, ["PALLETTIZZATO S/N"], "PALLETTIZZATO S/N")
        col_SUPP = trova_colonna(df, ["SUPPORTO"], "SUPPORTO")
        col_SUPPMOV = trova_colonna(df, ["SUPPORTO MOV.", "SUPPORTO MOV"], "SUPPORTO MOV.")

        df[col_ORA] = df[col_ORA].astype(str).str.replace(".", ":", regex=False)

        # ============================
        # 3) DF_PIK
        # ============================
        df_pik = pd.DataFrame()
        df_pik["Data"] = df[col_DATA]
        df_pik["Ora_raw"] = df[col_ORA]
        df_pik["Operatore"] = df[col_OPER]
        df_pik["Circuito"] = df[col_CIRC]
        df_pik["AreaUscita"] = df[col_AREA]
        df_pik["Colli"] = df[col_COLL]
        df_pik["Lista"] = df[col_LISTA]
        df_pik["Corsia"] = df[col_CORSIA]
        df_pik["Posto"] = df[col_POSTO]
        df_pik["TipoLista"] = df[col_TIPOLISTA]
        df_pik["PallettizzatoSN"] = df[col_PALSN]
        df_pik["Supporto"] = df[col_SUPP]
        df_pik["SupportoMov"] = df[col_SUPPMOV]

        df_pik["Colli"] = pd.to_numeric(df_pik["Colli"], errors="coerce").fillna(0).astype(int)
        df_pik["Operatore"] = pd.to_numeric(df_pik["Operatore"], errors="coerce").fillna(0).astype(int)

        df_pik["Data_dt"] = pd.to_datetime(df_pik["Data"], errors="coerce", dayfirst=True)
        df_pik["Data"] = df_pik["Data_dt"].dt.date

        # accetta anche HH:MM
        ora_norm = df_pik["Ora_raw"].astype(str).str.strip()
        ora_norm = ora_norm.where(ora_norm.str.len() != 5, ora_norm + ":00")
        df_pik["Ora_ts"] = pd.to_datetime(ora_norm, format="%H:%M:%S", errors="coerce")

        df_pik = df_pik.sort_values(by=["Data_dt", "Operatore", "Ora_ts"], ascending=[True, True, True]).reset_index(drop=True)

        # ============================
        # 4) TEMPO MOVIMENTO + AJ
        # ============================
        df_pik["TempoMov"] = df_pik.groupby(["Operatore", "Data"])["Ora_ts"].diff()
        soglia_td = pd.Timedelta(minutes=SOGLIA_MINUTI)
        df_pik["AJ_flag"] = df_pik["TempoMov"] < soglia_td
        df_pik.loc[df_pik["TempoMov"].isna(), "AJ_flag"] = False
        df_pik["Considera"] = df_pik["AJ_flag"]

        # ============================
        # 5) campi puliti
        # ============================
        df_pik["PallettizzatoSN_str"] = df_pik["PallettizzatoSN"].astype(str).str.strip().str.lower()
        df_pik["TipoMissione"] = df_pik["PallettizzatoSN_str"].map(lambda x: "PALLETTIZZATO" if x == "s" else "PIK")

        df_pik["AreaUscita_clean"] = df_pik["AreaUscita"].astype(str).str.strip().str.upper()
        df_pik["TipoLista_clean"] = df_pik["TipoLista"].astype(str).str.strip().str.lower()
        df_pik["SupportoMov_clean"] = df_pik["SupportoMov"].astype(str).str.strip().str.lower()

        df_pik["Corsia_num"] = pd.to_numeric(df_pik["Corsia"], errors="coerce")
        df_pik["Posto_num"] = pd.to_numeric(df_pik["Posto"], errors="coerce")

        # ============================
        # 6) cambio missione
        # ============================
        df_pik["CambioMiss"] = ""
        mask_cambio = (df_pik["Operatore"] == df_pik["Operatore"].shift(1)) & (df_pik["Lista"] != df_pik["Lista"].shift(1))
        df_pik.loc[mask_cambio, "CambioMiss"] = "CAMBIO MISS"

        mask_cm_base = (
            (df_pik["SupportoMov_clean"] != "cas") &
            (df_pik["PallettizzatoSN_str"] != "s") &
            (df_pik["CambioMiss"] == "CAMBIO MISS") &
            (df_pik["Considera"]) &
            (df_pik["Operatore"] != 200)
        )
        serie_cm_gen = df_pik.loc[mask_cm_base, "TempoMov"].dropna()
        tempo_medio_cambio_ore_gen = (serie_cm_gen.mean().total_seconds() / 3600.0) if not serie_cm_gen.empty else 0.0

        # ============================
        # 7) RITORNI + RECUPERO + DISTANZE
        # ============================
        df_pik["RITORNO"] = _compute_ritorno_vectorized(df_pik)
        df_pik["RECUPERO"] = df_pik["TipoLista_clean"] == "lista di recupero"

        df_ret = df_pik[(df_pik["Corsia_num"].notna()) & (df_pik["RITORNO"] == "Sì")].copy()
        df_ret["Corsia_int"] = df_ret["Corsia_num"].astype(int)
        ritorni_by_lane = df_ret.groupby("Corsia_int").size().to_dict()

        df_rec = df_pik[(df_pik["Corsia_num"].notna()) & (df_pik["RECUPERO"])].copy()
        df_rec["Corsia_int"] = df_rec["Corsia_num"].astype(int)
        rec_lists = df_rec.groupby(["Corsia_int", "Lista"]).size().reset_index()[["Corsia_int", "Lista"]]
        recupero_by_lane = rec_lists.groupby("Corsia_int")["Lista"].nunique().to_dict()

        issues_by_lane: dict[int, int] = {}
        corsie_uniche = df_pik["Corsia_num"].dropna().astype(int).unique()
        for c in corsie_uniche:
            issues_by_lane[c] = int(ritorni_by_lane.get(c, 0)) + int(recupero_by_lane.get(c, 0))
        total_issues = int(sum(issues_by_lane.values()))

        df_pik["dist_prev"] = _compute_distances_vectorized(df_pik)

        valid_steps = df_pik["dist_prev"] > 0
        dist_media_step = float(df_pik.loc[valid_steps, "dist_prev"].mean()) if valid_steps.any() else 0.0
        dist_per_mission = df_pik.groupby(["Data", "Operatore", "Lista"])["dist_prev"].sum()
        dist_media_missione = float(dist_per_mission.mean()) if not dist_per_mission.empty else 0.0

        # ============================
        # 7B) CONTROL ROOM (NUOVO) - NON ROMPE KPI
        # ============================
        df_pik["Circuito_u"] = df_pik["Circuito"].astype(str).str.strip().str.upper()
        df_pik["AreaUscita_u"] = df_pik["AreaUscita"].astype(str).str.strip().str.upper()
        df_pik["is_recupero"] = _is_recupero_tipo(df_pik["TipoLista"])

        df_dist = df_pik[df_pik["Ora_ts"].notna()].copy()
        df_dist["ritorno"] = (df_dist["RITORNO"] == "Sì")

        cr_wide_df, cr_detail_df = _control_room_from_dist(df_dist)
        control_room_wide = cr_wide_df.to_dict(orient="records") if not cr_wide_df.empty else []
        control_room_detail = cr_detail_df.to_dict(orient="records") if not cr_detail_df.empty else []

        # ============================
        # 8–13) KPI + operatori
        # ============================
        mask_aj = df_pik["Considera"]

        mask_tempo_gen = (mask_aj & (df_pik["Operatore"] != 0) & (df_pik["TipoMissione"] == "PIK"))
        tempo_gen_ore = td_to_hours(df_pik.loc[mask_tempo_gen, "TempoMov"])

        mask_colli_gen = (
            (df_pik["PallettizzatoSN_str"] == "n") &
            (df_pik["AreaUscita_clean"] != "KAR") &
            (df_pik["Circuito"] != "SEN")
        )
        colli_gen = int(df_pik.loc[mask_colli_gen, "Colli"].sum())
        prod_gen = colli_gen / tempo_gen_ore if tempo_gen_ore > 0 else 0.0

        n_liste_gen = df_pik.loc[mask_colli_gen, "Lista"].nunique()
        media_colli_lista_gen = (colli_gen / n_liste_gen) if n_liste_gen > 0 else 0.0
        sogliaOKEff_gen = soglia_ok_effettiva(media_colli_lista_gen)

        if sogliaOKEff_gen is not None and sogliaOKEff_gen > 0:
            capacity_ratio = max(0.0, min(prod_gen / sogliaOKEff_gen, 2.0))
            prod_target_colli_ora = sogliaOKEff_gen
        else:
            capacity_ratio = 0.0
            prod_target_colli_ora = 0.0
            media_colli_lista_gen = 0.0

        righe_totali_gen = int(mask_colli_gen.sum())
        colli_per_riga_gen = (colli_gen / righe_totali_gen) if righe_totali_gen > 0 else 0.0

        mask_utenti = (
            (df_pik["Operatore"] != 0) &
            (df_pik["PallettizzatoSN_str"] == "n") &
            (df_pik["Circuito"] != "SEN")
        )

        df_op_colli = df_pik.loc[mask_utenti].groupby("Operatore", as_index=False).agg(colli=("Colli", "sum"))

        df_time = df_pik.loc[(mask_aj & (df_pik["Circuito"] != "SEN"))].groupby("Operatore")["TempoMov"].apply(td_to_hours).reset_index()
        df_time.columns = ["Operatore", "ore"]

        df_op = df_op_colli.merge(df_time, on="Operatore", how="left")
        df_op["ore"] = df_op["ore"].fillna(0.0)
        df_op["prod"] = np.where(df_op["ore"] > 0, df_op["colli"] / df_op["ore"], 0.0)

        df_prod = df_op.rename(columns={"Operatore": "Utente", "ore": "Ore_lavorate_ore", "colli": "Colli", "prod": "Prod_colli_ora"})
        df_prod = df_prod.sort_values("Prod_colli_ora", ascending=False).reset_index(drop=True)

        kpi_overview = {
            "units_per_hour": round(float(prod_gen), 1),
            "capacity_utilization": float(round(capacity_ratio, 3)),
            "target_units_per_hour": float(round(prod_target_colli_ora, 1)),
            "prod_target_colli_ora": float(round(prod_target_colli_ora, 1)),
            "colli_per_riga": float(round(colli_per_riga_gen, 2)),
            "colli_per_lista": float(round(media_colli_lista_gen, 1)),
            "media_colli_lista": float(round(media_colli_lista_gen, 1)),
            "return_rate": int(total_issues),
            "colli_totali": int(colli_gen),
            "tempo_netto_ore": float(round(tempo_gen_ore, 2)),
            "tempo_medio_cambio_ore": float(round(tempo_medio_cambio_ore_gen, 3)),
            # ✅ ripristinate e SEMPRE presenti
            "dist_media_missione_m": float(round(dist_media_missione, 1)),
            "dist_media_step_m": float(round(dist_media_step, 1)),
        }

        operators = [
            {
                "name": str(int(row.Utente)),
                "units_per_hour": round(float(row.Prod_colli_ora), 1),
                "colli": int(row.Colli),
                "ore": round(float(row.Ore_lavorate_ore), 2),
            }
            for row in df_prod.itertuples(index=False)
        ]

        # ============================
        # STORICO: carico report_storico.xlsx (se presente)
        # ============================
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        history_path = HISTORY_DIR / HISTORY_FILE
        history_pack = load_history_report(history_path)

        history_cmp = {"status": history_pack.get("status")}
        if history_pack.get("status") == "ok":
            df_hist = history_pack.get("storico_giornaliero")
            history_cmp = build_history_comparison(df_hist, kpi_overview, last_n_days=14)

        history_info = {
            "status": history_pack.get("status"),
            "path": history_pack.get("path"),
            "days": history_pack.get("days"),
            "from": history_pack.get("from"),
            "to": history_pack.get("to"),
            "comparison": history_cmp,
        }

        # ============================
        # CARRELLISTI
        # ============================
        df_fk = pd.DataFrame()
        forklift_kpi_overview = {
            "pallet_totali": 0, "ore_totali": 0.0, "pallet_ora": 0.0,
            "kardex": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
            "stok": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
            "abbassamenti": {"pallet": 0, "ore": 0.0, "pallet_ora": 0.0},
        }
        forklift_operators = []

        if forklift_files:
            dfs_fk = [read_any_table(f) for f in forklift_files]
            df_raw_fk = pd.concat(dfs_fk, ignore_index=True)
            df_fk = build_forklift_df(df_raw_fk)
            forklift_kpi_overview, forklift_operators = forklift_kpi_by_operator(df_fk)

        # ============================
        # RESULT (base) + lazy placeholders
        # ============================
        result = {
            "kpi_overview": kpi_overview,
            "operators": operators,

            # ✅ CONTROL ROOM (NUOVO, JSON-ready)
            "control_room_wide": control_room_wide,
            "control_room_detail": control_room_detail,

            # ✅ STORICO (NUOVO)
            "history": history_info,

            # base
            "df_pik": df_pik,
            "df_prod": df_prod,

            # carrellisti
            "forklift_kpi_overview": forklift_kpi_overview,
            "forklift_operators": forklift_operators,
            "df_fk": df_fk,

            # lazy blocks: NON calcolati finché non richiesti
            "layout": None,
            "operator_paths": None,

            # cache interna per costruire layout velocemente
            "_recupero_by_lane": recupero_by_lane,
            "_issues_by_lane": issues_by_lane,
        }

        if include_paths:
            result["operator_paths"] = _build_operator_paths(df_pik)
        if include_layout:
            result["layout"] = _build_layout(df_pik, recupero_by_lane, issues_by_lane)

        _AGORA_CACHE = result
        _AGORA_CACHE_INPUT_DIR = resolved_dir
        _AGORA_CACHE_SIGNATURE = sig
        return result
