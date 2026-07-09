import os
from io import BytesIO
from pathlib import Path

import pandas as pd

REAL_DECIMAL_PLACES = 2

CATALOG_PATH = Path("data/b3_enterprises.xlsx")
OVERRIDES_PATH = Path("data/cnpj_overrides.xlsx")

EARNINGS_REQUIRED_COLUMNS = ["Tipo de Evento", "Produto", "Valor líquido"]
NEGOTIATION_REQUIRED_COLUMNS = [
    "Código de Negociação",
    "Instituição",
    "Quantidade (Líquida)",
    "Preço Médio (Compra)",
]
NEGOTIATION_SHEET_NAME = "Negociação - Resumo"


def get_products_infos_map(df):
    products_map = {}
    for _, row in df.iterrows():
        product = row["Ticker"]
        products_map[product] = {
            "Tipo": row["Tipo"],
            "CNPJ": row["CNPJ"],
            "Ticker": product,
        }
    return products_map


def load_catalog():
    base = pd.read_excel(CATALOG_PATH)
    products_info = get_products_infos_map(base)
    if OVERRIDES_PATH.exists():
        overrides = pd.read_excel(OVERRIDES_PATH)
        for _, row in overrides.iterrows():
            ticker = row["Ticker"]
            products_info[ticker] = {
                "Tipo": row.get("Tipo", ""),
                "CNPJ": row["CNPJ"],
                "Ticker": ticker,
            }
    return products_info


def save_overrides(rows):
    """Merge new rows into data/cnpj_overrides.xlsx atomically.

    `rows` is an iterable of dicts with keys Ticker, Tipo, CNPJ.
    Existing tickers are replaced; new ones appended.
    """
    new_df = pd.DataFrame(list(rows), columns=["Ticker", "Tipo", "CNPJ"])
    new_df = new_df[new_df["CNPJ"].astype(str).str.strip() != ""]
    if new_df.empty:
        return

    if OVERRIDES_PATH.exists():
        existing = pd.read_excel(OVERRIDES_PATH)
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["Ticker"], keep="last")
    else:
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        merged = new_df

    tmp_path = OVERRIDES_PATH.with_suffix(".xlsx.tmp")
    merged.to_excel(tmp_path, index=False)
    os.replace(tmp_path, OVERRIDES_PATH)


def _check_columns(df, required, source):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{source}: faltando coluna(s) {missing}. "
            f"Colunas encontradas: {list(df.columns)}"
        )


def read_earnings(file_or_path):
    df = pd.read_excel(file_or_path)
    _check_columns(df, EARNINGS_REQUIRED_COLUMNS, "earnings.xlsx")
    return df


def read_negotiation_summary(file_or_path):
    try:
        df = pd.read_excel(file_or_path, sheet_name=NEGOTIATION_SHEET_NAME)
    except ValueError:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        df = pd.read_excel(file_or_path)
    _check_columns(df, NEGOTIATION_REQUIRED_COLUMNS, "negotiation_summary.xlsx")
    return df


def get_earnings(df):
    earnings_per_product = {}
    for _, row in df.iterrows():
        event_type = row["Tipo de Evento"]
        if event_type not in ["Rendimento", "Juros Sobre Capital Próprio", "Dividendo"]:
            continue

        product = row["Produto"].split(" - ")[0]
        value = row["Valor líquido"]

        if product not in earnings_per_product:
            earnings_per_product[product] = {
                "Rendimento": 0,
                "Juros Sobre Capital Próprio": 0,
                "Dividendo": 0,
            }
        earnings_per_product[product][event_type] = round(
            earnings_per_product[product][event_type] + value, REAL_DECIMAL_PLACES
        )

    return earnings_per_product


def get_assets_and_rights(df, earnings_per_product, products_info):
    assets_and_rights = []
    for _, row in df.iterrows():
        product = row["Código de Negociação"]
        if product.endswith("F"):
            product = product[:-1]

        institution = row["Instituição"]
        curr_quantity = row["Quantidade (Líquida)"]
        price_bought = row["Preço Médio (Compra)"]
        aquisition_value = curr_quantity * price_bought
        if curr_quantity <= 0:
            continue

        interest, dividend, earnings = 0, 0, 0
        if product in earnings_per_product:
            interest = round(earnings_per_product[product]["Juros Sobre Capital Próprio"], REAL_DECIMAL_PLACES)
            dividend = round(earnings_per_product[product]["Dividendo"], REAL_DECIMAL_PLACES)
            earnings = round(earnings_per_product[product]["Rendimento"], REAL_DECIMAL_PLACES)

        assets_and_rights.append({
            "Produto": product,
            "Grupo": get_product_group(product),
            "Código": get_product_code(product),
            "CNPJ": get_product_cnpj(product, products_info),
            "Discriminação": get_discrimination(product, institution, price_bought),
            "Situação final": round(aquisition_value, REAL_DECIMAL_PLACES),
            "Juros Sobre Capital Próprio": interest,
            "Dividendo": dividend,
            "Rendimento": earnings,
        })

    return assets_and_rights


def get_product_group(ticker):
    """Retorna o grupo da declaração de IR com base no tipo do ativo."""
    if ticker.endswith("11"):
        return "07 - Fundos"
    elif ticker.endswith("34"):
        return "04 - Aplicações e Investimentos"
    else:
        return "03 - Participações Societárias"


def get_product_code(ticker):
    if ticker.endswith("11"):
        if ticker in {"IVVB11", "SMAL11"}:
            return "09 - Demais Fundos de Índice de Mercado (ETFs)"
        else:
            return "03 - Fundos de Investimento Imobiliário (FII)"
    elif ticker.endswith("34"):
        return "04 - Ativos negociados em Bolsa no Brasil (BDRs, opções e outros - exceto ações e fundos)"
    else:
        return "01 - Ações (inclusive as listadas em bolsa)"


def get_product_cnpj(product, products_info):
    if product not in products_info:
        return "Não encontrado"
    return products_info[product]["CNPJ"]


def get_discrimination(product, institution, price_bought):
    return f"Compra de {product} na {institution} com custo médio de R$ {price_bought:.{REAL_DECIMAL_PLACES}f}"


def build_output_xlsx_bytes(assets_and_rights):
    buffer = BytesIO()
    pd.DataFrame(assets_and_rights).to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer.getvalue()
