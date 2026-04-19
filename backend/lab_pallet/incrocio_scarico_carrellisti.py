import re
from pathlib import Path
import pandas as pd

INPUT_FILE = Path("dati_pallet.xlsx")          # <-- il tuo file unico
OUTPUT_FILE = Path("output_incrocio.xlsx")     # <-- risultato

SHEET_SCARICO = "scarico"
SHEET_CARRELLISTI = "carrellisti"

# Colonne (da tuoi screenshot)
COL_SUPPORTO = "SUPPORTO"          # nel foglio scarico (colonna O)
COL_PALLET_NUM = "Pallet:Numero"   # nel foglio carrellisti (colonna I)

OUT_COL_PALLET_STR = "PALLET_SCARICATO_STR"   # mantiene eventuali zeri: "00012"
OUT_COL_PALLET_INT = "PALLET_SCARICATO"       # numero per incrocio: 12 / 73462

# Campi che vogliamo riportare da carrellisti
CAR_FIELDS = [
    "Cons:Ora",
    "ARR:Corsia",
    "ARR:Posto",
    "ARR:Piano",
]

NOT_FOUND_VALUE = "NON STOK"


def extract_last5_digits(value) -> str | None:
    """
    Replica l'idea di DESTRA(...;5) ma robusta:
    - prende gli ultimi 5 caratteri
    - se non sono tutti numeri, prova a prendere le ultime 5 cifre presenti
    Ritorna stringa di 5 cifre (con zeri) oppure None.
    """
    if value is None:
        return None
    s = str(value).strip()

    if len(s) >= 5:
        tail = s[-5:]
        if tail.isdigit():
            return tail

    digits = re.findall(r"\d", s)
    if len(digits) >= 5:
        return "".join(digits[-5:])

    return None


def to_int_safe(x):
    try:
        return int(x)
    except Exception:
        return None


def normalize_time_str(x):
    """
    Gestisce '06.00.01' -> '06:00:01' e prova a normalizzare.
    Se è NaN/None lascia None.
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace(".", ":")
    return s


def main():
    # Leggo i due fogli
    df_scarico = pd.read_excel(INPUT_FILE, sheet_name=SHEET_SCARICO, dtype=str)
    df_car = pd.read_excel(INPUT_FILE, sheet_name=SHEET_CARRELLISTI)

    # --- Scarico: calcolo pallet da SUPPORTO
    if COL_SUPPORTO not in df_scarico.columns:
        raise ValueError(f"Nel foglio '{SHEET_SCARICO}' non trovo la colonna '{COL_SUPPORTO}'")

    df_scarico[OUT_COL_PALLET_STR] = df_scarico[COL_SUPPORTO].apply(extract_last5_digits)
    df_scarico[OUT_COL_PALLET_INT] = df_scarico[OUT_COL_PALLET_STR].apply(to_int_safe)

    # --- Carrellisti: preparo chiave pallet
    if COL_PALLET_NUM not in df_car.columns:
        raise ValueError(f"Nel foglio '{SHEET_CARRELLISTI}' non trovo la colonna '{COL_PALLET_NUM}'")

    # assicuro numerico per match (Excel di solito qui ha numeri)
    df_car["_pallet_key"] = pd.to_numeric(df_car[COL_PALLET_NUM], errors="coerce")

    # tengo SOLO la prima occorrenza come CERCA.X (prima riga che trova)
    df_car_first = df_car.dropna(subset=["_pallet_key"]).drop_duplicates(subset=["_pallet_key"], keep="first")

    # normalizzo campi tempo (se presente)
    if "Cons:Ora" in df_car_first.columns:
        df_car_first["Cons:Ora"] = df_car_first["Cons:Ora"].apply(normalize_time_str)

    # Se mancano alcune colonne richieste, le creo vuote (così non esplode)
    for c in CAR_FIELDS:
        if c not in df_car_first.columns:
            df_car_first[c] = None

    # Mi tengo solo chiave + campi utili
    df_lookup = df_car_first[["_pallet_key"] + CAR_FIELDS].copy()

    # --- Merge (left join): scarico -> carrellisti
    out = df_scarico.merge(
        df_lookup,
        how="left",
        left_on=OUT_COL_PALLET_INT,
        right_on="_pallet_key",
    ).drop(columns=["_pallet_key"])

    # Riempio i non trovati con NON STOK (come la tua CERCA.X con default)
    for c in CAR_FIELDS:
        out[c] = out[c].fillna(NOT_FOUND_VALUE)

    # Salvo output
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="incrocio", index=False)
        df_car.to_excel(writer, sheet_name="carrellisti_raw", index=False)

    print(f"OK! Creato: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
