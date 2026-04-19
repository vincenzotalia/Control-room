# backend/agora_analysis.py
import glob
from pathlib import Path
import pandas as pd

# ============================
# PARAMETRI GLOBALI
# ============================

SOGLIA_MINUTI = 40  # soglia max tra due movimenti consecutivi (picking AJ / forklift tempo valido)

# parametri distanze serpentina (come macro Excel)
PASSO = 0.87
LARGHEZZA_CORSIA = 3.6
PASSAGGIO_CORSIA = 2.6

# Limiti "anti-freeze" per payload animazioni (picking)
MAX_PATH_STEPS_PER_OPERATOR = 20000  # se hai settimane enormi, evita JSON mostruosi

# ============================
# CACHE
# ============================

_AGORA_CACHE = None
_AGORA_CACHE_INPUT_DIR = None


# ============================
# HELPERS GENERICI
# ============================

def td_to_hours(td_series: pd.Series) -> float:
    if td_series is None or td_series.empty:
        return 0.0
    return td_series.dt.total_seconds().sum() / 3600.0


def trova_colonna(df: pd.DataFrame, possibili_nomi, descrizione: str) -> str:
    """
    Trova una colonna cercando per nome (case-insensitive, spazi).
    """
    mappa = {str(c).strip().lower(): c for c in df.columns}
    for nome in possibili_nomi:
        key = str(nome).strip().lower()
        if key in mappa:
            return mappa[key]
    raise KeyError(
        f"Colonna per '{descrizione}' non trovata. Cercate: {possibili_nomi}. "
        f"Presenti: {list(df.columns)}"
    )


def _safe_time_to_str(x) -> str:
    """
    Normalizza un campo ora che può essere:
    - datetime/time
    - stringa "08:15:20" o "08.15.20"
    """
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
    """
    Normalizza un campo data (datetime/date o stringa "14/10/2025").
    """
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


# ============================
# FILE LOADER
# ============================

def read_any_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()

    if ext in (".xlsx", ".xlsm"):
        return pd.read_excel(p, engine="openpyxl")
    if ext == ".xls":
        return pd.read_excel(p, engine="xlrd")
    if ext == ".csv":
        return pd.read_csv(p, sep=";", dtype=str).fillna("")
    return pd.read_excel(p)


# =========================================================
# ===================== CARRELLISTI ========================
# =========================================================

MOVEMENT_FAMILY_MAP = {
    "STOCCAGGIO ARMADIO VERTICALE": "KARDEX",
    "RIPRIST.TOT DA SCORTA A PRESA": "ABBASSAMENTO",
    "STOCCAGGIO IN SCORTA": "STOCK",
    "STOCCAGGIO IN PRESA": "STOCK",
    "RIPRIST.PRZ DA SCORTA A PRESA": "PARZIALE",
    "RISTOCC. DOPO RIPR. PARZIALE": "STOCK",
}


def _norm_tp(tp: str) -> str:
    if tp is None:
        return ""
    s = str(tp).strip().upper()
    s = " ".join(s.split())
    return s


def movement_family(tp_mov: str) -> str:
    """
    Ritorna la "famiglia" (KARDEX/ABBASSAMENTO/STOCK/PARZIALE) usando:
    1) match esatto su mapping
    2) fallback per contenuto (robusto ma non distruttivo)
    """
    s = _norm_tp(tp_mov)

    for k, v in MOVEMENT_FAMILY_MAP.items():
        if s == _norm_tp(k):
            return v

    if "ARMADIO" in s and "VERTICALE" in s:
        return "KARDEX"
    if "RIPRIST" in s and "TOT" in s:
        return "ABBASSAMENTO"
    if "RIPRIST" in s and "PRZ" in s:
        return "PARZIALE"
    if "STOCCAGGIO" in s:
        return "STOCK"
    if "RISTOCC" in s:
        return "STOCK"

    return "ALTRO"


def build_forklift_df(df_raw_fk: pd.DataFrame) -> pd.DataFrame:
    """
    Logica carrellisti:
    - Operatore = Cons:Ope Rad.
    - start_ts = ESEC.Dt. Ini + ESEC.Ora Ini
    - TempoMov = diff per stesso operatore (start corrente - start precedente)
    - Se delta > 40 min => NON considerato nel tempo (durata_h = NA), MA il movimento conta lo stesso
    - Ogni riga = 1 movimento/pallet
    """
    if df_raw_fk is None or df_raw_fk.empty:
        return pd.DataFrame()

    df = df_raw_fk.copy()

    col_OP = trova_colonna(
        df,
        ["Cons:Ope Rad.", "Cons:Ope Rad", "Cons.Ope Rad.", "Cons.Ope Rad"],
        "Cons:Ope Rad."
    )
    col_DT = trova_colonna(df, ["ESEC.Dt. Ini", "ESEC.Dt Ini", "ESEC.Dt. Ini "], "ESEC.Dt. Ini")
    col_ORA = trova_colonna(df, ["ESEC.Ora Ini", "ESEC.OraIni", "ESEC. Ora Ini", "ESEC.Ora Ini "], "ESEC.Ora Ini")
    col_TP = trova_colonna(df, ["Tp Movimento", "TP MOVIMENTO", "TpMovimento"], "Tp Movimento")

    out = pd.DataFrame()
    out["Operatore"] = pd.to_numeric(df[col_OP], errors="coerce").fillna(0).astype(int)
    out["TpMovimento"] = df[col_TP].astype(str).map(_norm_tp)
    out["Famiglia"] = out["TpMovimento"].map(movement_family)

    start_date = df[col_DT].apply(_safe_date_to_str)
    start_time = df[col_ORA].apply(_safe_time_to_str)
    out["start_ts"] = pd.to_datetime(start_date + " " + start_time, errors="coerce", dayfirst=True)

    out = out.sort_values(["start_ts", "Operatore"], na_position="last").reset_index(drop=True)

    out["TempoMov"] = out.groupby("Operatore")["start_ts"].diff()

    soglia = pd.Timedelta(minutes=SOGLIA_MINUTI)
    out["Considera"] = (
        out["TempoMov"].notna()
        & (out["TempoMov"] >= pd.Timedelta(seconds=0))
        & (out["TempoMov"] <= soglia)
    )

    out["durata_h"] = out["TempoMov"].dt.total_seconds() / 3600.0
    out.loc[~out["Considera"], "durata_h"] = pd.NA

    out["Movimenti"] = 1
    return out


def forklift_kpi(df_fk: pd.DataFrame) -> tuple[dict, list[dict], list[dict]]:
    """
    KPI carrellisti:
    - overview: movimenti_totali, ore_totali (solo righe Considera), mov_ora
    - by_family: breakdown per Famiglia
    - by_tp: breakdown per TpMovimento (grezzo)
    """
    if df_fk is None or df_fk.empty:
        return (
            {"movimenti_totali": 0, "ore_totali": 0.0, "mov_ora": 0.0},
            [],
            []
        )

    df = df_fk.copy()
    mov_tot = int(df["Movimenti"].sum()) if "Movimenti" in df.columns else int(len(df))

    df_valid = df[df["durata_h"].notna() & (df["durata_h"] > 0)].copy()
    ore_tot = float(df_valid["durata_h"].sum()) if not df_valid.empty else 0.0
    mov_ora = (mov_tot / ore_tot) if ore_tot > 0 else 0.0

    overview = {
        "movimenti_totali": mov_tot,
        "ore_totali": round(ore_tot, 2),
        "mov_ora": round(mov_ora, 1),
    }

    rows_family: list[dict] = []
    if "Famiglia" in df.columns:
        for fam, g in df.groupby("Famiglia"):
            mov = int(g["Movimenti"].sum()) if "Movimenti" in g.columns else int(len(g))
            g_valid = g[g["durata_h"].notna() & (g["durata_h"] > 0)]
            ore = float(g_valid["durata_h"].sum()) if not g_valid.empty else 0.0
            prod = (mov / ore) if ore > 0 else 0.0
            rows_family.append({
                "famiglia": str(fam),
                "movimenti": mov,
                "ore": round(ore, 2),
                "mov_ora": round(prod, 1),
            })
        rows_family = sorted(rows_family, key=lambda r: r["movimenti"], reverse=True)

    rows_tp: list[dict] = []
    if "TpMovimento" in df.columns:
        for tp, g in df.groupby("TpMovimento"):
            mov = int(g["Movimenti"].sum()) if "Movimenti" in g.columns else int(len(g))
            g_valid = g[g["durata_h"].notna() & (g["durata_h"] > 0)]
            ore = float(g_valid["durata_h"].sum()) if not g_valid.empty else 0.0
            prod = (mov / ore) if ore > 0 else 0.0
            rows_tp.append({
                "tp_movimento": str(tp),
                "famiglia": movement_family(tp),
                "movimenti": mov,
                "ore": round(ore, 2),
                "mov_ora": round(prod, 1),
            })
        rows_tp = sorted(rows_tp, key=lambda r: r["movimenti"], reverse=True)

    return overview, rows_family, rows_tp


# =========================================================
# ===================== PICKING (INVARIATO) ================
# =========================================================

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
    if 75 <= media_lista <= 90:
        return 139.0
    elif media_lista > 90:
        return 144.0
    else:
        return sogliaOK


# =========================================================
# ===================== MAIN ===============================
# =========================================================

def run_agora_analysis(input_dir: str | Path | None = None, force: bool = False) -> dict:
    """
    Esegue analisi:
    - PICKING: kpi_overview, operators, layout, operator_paths
    - CARRELLISTI: forklift_kpi_overview + breakdown
    """
    global _AGORA_CACHE, _AGORA_CACHE_INPUT_DIR

    resolved_dir = Path(input_dir).resolve() if input_dir else Path(__file__).parent / "data" / "input"

    if (not force) and (_AGORA_CACHE is not None) and (_AGORA_CACHE_INPUT_DIR == resolved_dir):
        return _AGORA_CACHE

    # ----------------------------
    # 1) Lista file
    # ----------------------------
    pattern = str(resolved_dir / "*.*")
    file_list = [
        f for f in glob.glob(pattern)
        if Path(f).suffix.lower() in (".xlsx", ".xlsm", ".xls", ".csv")
        and not Path(f).name.startswith("~$")
    ]
    if not file_list:
        raise RuntimeError(f"Nessun file trovato in {resolved_dir}")

    forklift_files = [f for f in file_list if Path(f).stem.lower().startswith("carrellisti")]
    picking_files = [f for f in file_list if f not in forklift_files]

    if not picking_files:
        raise RuntimeError(
            f"Nessun file picking trovato in {resolved_dir}. "
            f"Metti almeno un file picking (.xlsx/.xlsm/.xls/.csv) "
            f"e (opzionale) file carrellisti.*"
        )

    # ----------------------------
    # 2) PICKING (uguale al tuo)
    # ----------------------------
    dfs = [read_any_table(f) for f in picking_files]
    df = pd.concat(dfs, ignore_index=True)

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

    df_pik["Ora_ts"] = pd.to_datetime(
        df_pik["Ora_raw"].astype(str),
        format="%H:%M:%S",
        errors="coerce"
    )

    df_pik = df_pik.sort_values(
        by=["Data_dt", "Operatore", "Ora_ts"],
        ascending=[True, True, True]
    ).reset_index(drop=True)

    df_pik["TempoMov"] = df_pik.groupby(["Operatore", "Data"])["Ora_ts"].diff()
    soglia_td = pd.Timedelta(minutes=SOGLIA_MINUTI)
    df_pik["AJ_flag"] = df_pik["TempoMov"] < soglia_td
    df_pik.loc[df_pik["TempoMov"].isna(), "AJ_flag"] = False
    df_pik["Considera"] = df_pik["AJ_flag"]

    df_pik["PallettizzatoSN_str"] = df_pik["PallettizzatoSN"].astype(str).str.strip().str.lower()
    df_pik["TipoMissione"] = df_pik["PallettizzatoSN_str"].map(
        lambda x: "PALLETTIZZATO" if x == "s" else "PIK"
    )

    df_pik["AreaUscita_clean"] = df_pik["AreaUscita"].astype(str).str.strip().str.upper()
    df_pik["TipoLista_clean"] = df_pik["TipoLista"].astype(str).str.strip().str.lower()
    df_pik["SupportoMov_clean"] = df_pik["SupportoMov"].astype(str).str.strip().str.lower()

    df_pik["Corsia_num"] = pd.to_numeric(df_pik["Corsia"], errors="coerce")
    df_pik["Posto_num"] = pd.to_numeric(df_pik["Posto"], errors="coerce")

    # Cambio missione + tempo medio
    df_pik["CambioMiss"] = ""
    mask_cambio = (
        (df_pik["Operatore"] == df_pik["Operatore"].shift(1)) &
        (df_pik["Lista"] != df_pik["Lista"].shift(1))
    )
    df_pik.loc[mask_cambio, "CambioMiss"] = "CAMBIO MISS"

    mask_cm_base = (
        (df_pik["SupportoMov_clean"] != "cas") &
        (df_pik["PallettizzatoSN_str"] != "s") &
        (df_pik["CambioMiss"] == "CAMBIO MISS") &
        (df_pik["Considera"]) &
        (df_pik["Operatore"] != 200)
    )

    serie_cm_gen = df_pik.loc[mask_cm_base, "TempoMov"].dropna()
    if not serie_cm_gen.empty:
        mean_td_gen = serie_cm_gen.mean()
        tempo_medio_cambio_ore_gen = mean_td_gen.total_seconds() / 3600.0
    else:
        tempo_medio_cambio_ore_gen = 0.0

    # RITORNO / RECUPERO / DISTANZE (come tuo)
    df_pik["RITORNO"] = "No"
    for (data_mis, operatore, lista), group in df_pik.groupby(["Data", "Operatore", "Lista"]):
        idx = group.index
        corsie = df_pik.loc[idx, "Corsia_num"]
        corsie_valid = corsie[corsie > 0]
        if corsie_valid.empty:
            continue
        min_corsia = corsie_valid.min()
        last_corsia = corsie.iloc[-1]
        if pd.notna(last_corsia) and last_corsia > min_corsia:
            df_pik.loc[idx[-1], "RITORNO"] = "Sì"

    df_pik["RECUPERO"] = df_pik["TipoLista_clean"] == "lista di recupero"

    df_ret = df_pik[(df_pik["Corsia_num"].notna()) & (df_pik["RITORNO"] == "Sì")].copy()
    df_ret["Corsia_int"] = df_ret["Corsia_num"].astype(int)
    ritorni_by_lane = df_ret.groupby("Corsia_int").size().to_dict()

    df_rec = df_pik[(df_pik["Corsia_num"].notna()) & (df_pik["RECUPERO"])].copy()
    df_rec["Corsia_int"] = df_rec["Corsia_num"].astype(int)
    rec_lists = (
        df_rec.groupby(["Corsia_int", "Lista"])
        .size()
        .reset_index()[["Corsia_int", "Lista"]]
    )
    recupero_by_lane = rec_lists.groupby("Corsia_int")["Lista"].nunique().to_dict()

    issues_by_lane: dict[int, int] = {}
    corsie_uniche = df_pik["Corsia_num"].dropna().astype(int).unique()
    for c in corsie_uniche:
        issues_by_lane[int(c)] = int(ritorni_by_lane.get(int(c), 0)) + int(recupero_by_lane.get(int(c), 0))
    total_issues = int(sum(issues_by_lane.values()))

    df_pik["dist_prev"] = 0.0
    for (data_mis, operatore, lista), group in df_pik.groupby(["Data", "Operatore", "Lista"]):
        group_sorted = group.sort_values("Ora_ts")
        valid = group_sorted[group_sorted["Corsia_num"].notna() & group_sorted["Posto_num"].notna()]
        if valid.empty:
            continue
        idxs = valid.index.to_list()
        corsie = valid["Corsia_num"].astype(int).to_list()
        posti = valid["Posto_num"].astype(int).to_list()
        if len(idxs) == 1:
            c = corsie[0]
            p = posti[0]
            d = (abs(256 - p) / 2.0 * PASSO) if (c % 2 == 0) else (abs(p - 1) / 2.0 * PASSO)
            df_pik.at[idxs[0], "dist_prev"] = d
        else:
            df_pik.at[idxs[0], "dist_prev"] = 0.0
            for i in range(len(idxs) - 1):
                c1, p1 = corsie[i], posti[i]
                c2, p2 = corsie[i + 1], posti[i + 1]
                if c1 == c2:
                    d = (abs(p1 - p2) / 2.0 * PASSO) if ((p1 % 2) == (p2 % 2)) else LARGHEZZA_CORSIA
                else:
                    dir1 = "down" if (c1 % 2 == 0) else "up"
                    dir2 = "down" if (c2 % 2 == 0) else "up"
                    fineC1 = 1 if dir1 == "down" else 256
                    inizioC2 = 256 if dir2 == "down" else 1
                    d1 = abs(p1 - fineC1) / 2.0 * PASSO
                    d2 = abs(c1 - c2) * PASSAGGIO_CORSIA
                    d3 = abs(p2 - inizioC2) / 2.0 * PASSO
                    d = d1 + d2 + d3
                df_pik.at[idxs[i + 1], "dist_prev"] = d

    valid_steps = df_pik["dist_prev"] > 0
    dist_media_step = float(df_pik.loc[valid_steps, "dist_prev"].mean()) if valid_steps.any() else 0.0
    dist_per_mission = df_pik.groupby(["Data", "Operatore", "Lista"])["dist_prev"].sum()
    dist_media_missione = float(dist_per_mission.mean()) if not dist_per_mission.empty else 0.0

    # KPI picking
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
        prod_target_colli_ora = float(sogliaOKEff_gen)
    else:
        capacity_ratio = 0.0
        prod_target_colli_ora = 0.0

    righe_totali_gen = int(mask_colli_gen.sum())
    colli_per_riga_gen = (colli_gen / righe_totali_gen) if righe_totali_gen > 0 else 0.0

    # per operatore picking
    mask_utenti = (
        (df_pik["Operatore"] != 0) &
        (df_pik["PallettizzatoSN_str"] == "n") &
        (df_pik["Circuito"] != "SEN")
    )
    utenti = sorted(df_pik.loc[mask_utenti, "Operatore"].unique())

    rows_prod = []
    for op in utenti:
        mask_op_base = df_pik["Operatore"] == op
        mask_time = mask_op_base & mask_aj & (df_pik["Circuito"] != "SEN")
        ore_ore = td_to_hours(df_pik.loc[mask_time, "TempoMov"])
        mask_colli_op = mask_op_base & (df_pik["PallettizzatoSN_str"] == "n") & (df_pik["Circuito"] != "SEN")
        colli_op = int(df_pik.loc[mask_colli_op, "Colli"].sum())
        prod_op = colli_op / ore_ore if ore_ore > 0 else 0.0
        rows_prod.append({
            "Utente": int(op),
            "Ore_lavorate_ore": float(ore_ore),
            "Colli": int(colli_op),
            "Prod_colli_ora": float(prod_op),
        })

    # operator paths (picking)
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
        for _, r in g.iterrows():
            lane = r["Corsia_num"]
            pos = r["Posto_num"]
            if pd.isna(lane) or pd.isna(pos):
                continue
            step = {"lane": int(lane), "pos": float(pos)}
            lista = r.get("Lista", None)
            colli_row = r.get("Colli", 0)
            tempo_mov = r.get("TempoMov", pd.NaT)

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

            if pd.notna(r["Ora_ts"]):
                step["time"] = r["Ora_ts"].isoformat()
            if pd.notna(r["Data_dt"]):
                step["date"] = r["Data_dt"].isoformat()

            steps.append(step)

            if len(steps) >= MAX_PATH_STEPS_PER_OPERATOR:
                break

        if len(steps) >= 2:
            operator_paths.append({"operator": str(int(op)), "steps": steps})

    # layout picking
    mask_layout = (
        df_pik["Corsia_num"].notna() &
        (df_pik["PallettizzatoSN_str"] == "n")  &
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
    layout = {"cells": cells}

    kpi_overview = {
        "units_per_hour": round(prod_gen, 1),
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
        "dist_media_missione_m": float(round(dist_media_missione, 1)),
        "dist_media_step_m": float(round(dist_media_step, 1)),
    }

    operators = [
        {
            "name": str(int(r["Utente"])),
            "units_per_hour": round(float(r["Prod_colli_ora"]), 1),
            "colli": int(r["Colli"]),
            "ore": round(float(r["Ore_lavorate_ore"]), 2),
        }
        for r in rows_prod
    ]

    # ----------------------------
    # 3) CARRELLISTI (KPI)
    # ----------------------------
    df_fk = pd.DataFrame()
    forklift_kpi_overview = {"movimenti_totali": 0, "ore_totali": 0.0, "mov_ora": 0.0}
    forklift_by_family: list[dict] = []
    forklift_by_movement: list[dict] = []

    if forklift_files:
        dfs_fk = [read_any_table(f) for f in forklift_files]
        df_raw_fk = pd.concat(dfs_fk, ignore_index=True)
        df_fk = build_forklift_df(df_raw_fk)
        forklift_kpi_overview, forklift_by_family, forklift_by_movement = forklift_kpi(df_fk)

    # ----------------------------
    # 4) RESULT
    # ----------------------------
    result = {
        # PICKING
        "kpi_overview": kpi_overview,
        "operators": operators,
        "layout": layout,
        "operator_paths": operator_paths,

        # >>> NECESSARIO PER LA PAGINA FATICA PICKING (main.py legge result["df_pik"]) <<<
        "df_pik": df_pik,

        # CARRELLISTI (solo KPI)
        "forklift_kpi_overview": forklift_kpi_overview,
        "forklift_by_family": forklift_by_family,
        "forklift_by_movement": forklift_by_movement,

        "meta": {
            "input_dir": str(resolved_dir),
            "picking_files": [Path(f).name for f in picking_files],
            "forklift_files": [Path(f).name for f in forklift_files],
            "picking_rows": int(len(df_pik)),
            "forklift_rows": int(len(df_fk)) if not df_fk.empty else 0,
        }
    }

    _AGORA_CACHE = result
    _AGORA_CACHE_INPUT_DIR = resolved_dir
    return result
