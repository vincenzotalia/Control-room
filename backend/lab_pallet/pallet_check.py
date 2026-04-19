# pallet_check.py
from pathlib import Path
from datetime import datetime, time as time_class
import re

import pandas as pd


# =========================
# CONFIG
# =========================
DEFAULT_INPUT = Path(__file__).with_name("dati_pallet.xlsx")
DEFAULT_OUTPUT = Path(__file__).with_name("risultato_incrocio.xlsx")

SHEET_SCARICO = "scarico"
SHEET_CARRELLISTI = "carrellisti"

COL_SUPPORTO = "SUPPORTO"                 # foglio scarico, colonna O
COL_ORA_INIZIO_CONSEGNA = "ORA INIZIO CONSEGNA"  # foglio scarico, colonna R

COL_PALLET_NUM = "Pallet:Numero"          # foglio carrellisti, colonna I
COL_CONS_ORA = "Cons:Ora"                 # foglio carrellisti, colonna AK (esce tipo 06.00.01)
COL_TP_MOV = "Tp Movimento"               # foglio carrellisti, colonna AV

MOV_TARGET = "RIPRIST.TOT DA SCORTA A PRESA"


# =========================
# HELPERS
# =========================
def normalize_time_to_time(x):
    """
    Converte:
      - datetime / Timestamp -> time
      - time -> time
      - string "06.00.01" o "06:00:01" -> time
    """
    if pd.isna(x):
        return None

    if isinstance(x, (pd.Timestamp, datetime)):
        return x.time()

    if isinstance(x, time_class):
        return x

    s = str(x).strip()
    if not s:
        return None

    # Excel esporta "06.00.01" -> lo trasformo in "06:00:01"
    s = s.replace(".", ":")

    parts = s.split(":")
    if len(parts) == 3:
        try:
            h = int(parts[0])
            m = int(parts[1])
            sec = int(parts[2])
            return time_class(h, m, sec)
        except Exception:
            return None

    if len(parts) == 2:
        try:
            h = int(parts[0])
            m = int(parts[1])
            return time_class(h, m, 0)
        except Exception:
            return None

    return None


def hour_bucket(t: time_class | None):
    if t is None:
        return None
    return f"{t.hour:02d}:00"


def pallet_from_supporto(val):
    """
    Replica logica Excel: =VALORE(DESTRA(O2;5))
    - prende gli ultimi 5 numeri
    - restituisce sia stringa a 5 cifre ("00012") sia int (12) per incrocio
    """
    if pd.isna(val):
        return (None, None)

    s = str(val)

    m = re.search(r"(\d{5})\s*$", s)
    if m:
        d5 = m.group(1)
    else:
        # fallback: prendo ultimi 5 caratteri e tengo solo numeri
        tail = s[-5:]
        only_digits = "".join(ch for ch in tail if ch.isdigit())
        if not only_digits:
            return (None, None)
        d5 = only_digits.rjust(5, "0")[:5]

    return (d5, int(d5))


# =========================
# MAIN
# =========================
def main(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT):
    print("📌 Avvio controllo pallet...")

    if not input_path.exists():
        raise FileNotFoundError(f"File non trovato: {input_path}")

    # leggo fogli
    scarico = pd.read_excel(input_path, sheet_name=SHEET_SCARICO)
    car = pd.read_excel(input_path, sheet_name=SHEET_CARRELLISTI)

    print("✅ Fogli letti correttamente")
    print(f" - righe scarico: {len(scarico)}")
    print(f" - righe carrellisti: {len(car)}")

    # =========================
    # 1) Calcolo pallet scaricato (da SUPPORTO)
    # =========================
    if COL_SUPPORTO not in scarico.columns:
        raise KeyError(f"Nel foglio '{SHEET_SCARICO}' manca la colonna '{COL_SUPPORTO}'")

    pallet_5 = []
    pallet_num = []
    for v in scarico[COL_SUPPORTO]:
        p5, pn = pallet_from_supporto(v)
        pallet_5.append(p5)
        pallet_num.append(pn)

    scarico["PALLET_SCARICATO_5"] = pallet_5      # mantiene "00012"
    scarico["PALLET_SCARICATO_NUM"] = pallet_num  # numero per incrocio

    # =========================
    # 2) Conversione ORA INIZIO CONSEGNA (scarico) e bucket ora
    # =========================
    if COL_ORA_INIZIO_CONSEGNA not in scarico.columns:
        raise KeyError(f"Nel foglio '{SHEET_SCARICO}' manca la colonna '{COL_ORA_INIZIO_CONSEGNA}'")

    scarico["ORA_INIZIO_CONSEGNA_TIME"] = scarico[COL_ORA_INIZIO_CONSEGNA].apply(normalize_time_to_time)
    scarico["ORA_INIZIO_CONSEGNA_HOUR"] = scarico["ORA_INIZIO_CONSEGNA_TIME"].apply(hour_bucket)

    # =========================
    # 3) Preparazione carrellisti: chiave pallet + conversione Cons:Ora + bucket ora
    # =========================
    if COL_PALLET_NUM not in car.columns:
        raise KeyError(f"Nel foglio '{SHEET_CARRELLISTI}' manca la colonna '{COL_PALLET_NUM}'")

    car["PALLET_NUM"] = pd.to_numeric(car[COL_PALLET_NUM], errors="coerce").astype("Int64")

    if COL_CONS_ORA in car.columns:
        car["CONS_ORA_TIME"] = car[COL_CONS_ORA].apply(normalize_time_to_time)
        car["CONS_ORA_HOUR"] = car["CONS_ORA_TIME"].apply(hour_bucket)
    else:
        # se un domani cambia nome, almeno non rompiamo tutto
        car["CONS_ORA_TIME"] = None
        car["CONS_ORA_HOUR"] = None

    # creo una tabella lookup per incrocio pallet -> info carrellisti
    # (tengo la prima occorrenza per ogni pallet)
    car_lookup = (
        car.dropna(subset=["PALLET_NUM"])
           .drop_duplicates(subset=["PALLET_NUM"])
           .set_index("PALLET_NUM")
    )

    # =========================
    # 4) Incrocio: se non trovato -> "NON STOK"
    # =========================
    corsia = []
    posto = []
    piano = []
    stoccato = []

    for pn in scarico["PALLET_SCARICATO_NUM"]:
        if pd.isna(pn):
            corsia.append(None)
            posto.append(None)
            piano.append(None)
            stoccato.append("NON STOK")
            continue

        pn_int = int(pn)
        if pn_int not in car_lookup.index:
            corsia.append(None)
            posto.append(None)
            piano.append(None)
            stoccato.append("NON STOK")
            continue

        row = car_lookup.loc[pn_int]
        corsia.append(row.get("ARR:Corsia", None))
        posto.append(row.get("ARR:Posto", None))
        piano.append(row.get("ARR:Piano", None))
        stoccato.append("STOK")

    scarico["CORSIA"] = corsia
    scarico["POSTO"] = posto
    scarico["PIANO"] = piano
    scarico["STOCCATO"] = stoccato   # ✅ QUI COMPARIRÀ "NON STOK" quando non matcha

    # =========================
    # 5) Conteggio pallet scaricati per ora (da ORA INIZIO CONSEGNA)
    # =========================
    scarico_hourly = (
        scarico.dropna(subset=["ORA_INIZIO_CONSEGNA_HOUR"])
              .groupby("ORA_INIZIO_CONSEGNA_HOUR", as_index=False)
              .agg(
                  pallet_scaricati=("PALLET_SCARICATO_NUM", "nunique"),
                  righe=("PALLET_SCARICATO_NUM", "size"),
              )
              .sort_values("ORA_INIZIO_CONSEGNA_HOUR")
    )

    # =========================
    # 6) Conteggio movimenti RIPRIST... per ora (carrellisti)
    # =========================
    if COL_TP_MOV in car.columns:
        car_rip = car[car[COL_TP_MOV].astype(str).str.strip().str.upper() == MOV_TARGET.upper()].copy()
    else:
        car_rip = car.iloc[0:0].copy()  # vuoto se manca colonna

    rip_hourly = (
        car_rip.dropna(subset=["CONS_ORA_HOUR"])
               .groupby("CONS_ORA_HOUR", as_index=False)
               .agg(
                   movimenti=(COL_TP_MOV, "size"),
                   pallet_coinvolti=("PALLET_NUM", "nunique"),
               )
               .sort_values("CONS_ORA_HOUR")
    )

    # =========================
    # 7) Scrittura output
    # =========================
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        scarico.to_excel(writer, sheet_name="scarico_incrociato", index=False)
        scarico_hourly.to_excel(writer, sheet_name="scarico_pallet_per_ora", index=False)
        rip_hourly.to_excel(writer, sheet_name="riprist_per_ora", index=False)

    print("✅ FATTO!")
    print(f"📁 File creato: {output_path.resolve()}")


if __name__ == "__main__":
    main()
