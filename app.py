import warnings

import pandas as pd
import streamlit as st

from core import (
    build_output_xlsx_bytes,
    get_assets_and_rights,
    get_earnings,
    load_catalog,
    read_earnings,
    read_negotiation_summary,
    save_overrides,
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

st.set_page_config(page_title="Calculadora IR", layout="wide")


@st.cache_data(show_spinner=False)
def _cached_catalog():
    return load_catalog()


@st.cache_data(show_spinner=False)
def _cached_earnings(file_bytes: bytes):
    from io import BytesIO
    return get_earnings(read_earnings(BytesIO(file_bytes)))


@st.cache_data(show_spinner=False)
def _cached_negotiation(file_bytes: bytes):
    from io import BytesIO
    return read_negotiation_summary(BytesIO(file_bytes))


def _missing_cnpj_df(assets):
    return pd.DataFrame([
        {"Produto": a["Produto"], "Grupo": a["Grupo"], "CNPJ": ""}
        for a in assets
        if a["CNPJ"] == "Não encontrado"
    ])


with st.sidebar:
    st.title("Calculadora IR")
    st.markdown(
        "Auxiliar para a ficha **Bens e Direitos** do IRPF a partir dos "
        "extratos da B3 (área do investidor → Extrato → Proventos / Negociação)."
    )
    st.markdown(
        "Faça upload do **extrato de Proventos** e do **Resumo de Negociação** "
        "(período desde a primeira compra até 31/12 do ano-base)."
    )
    if st.button("Recarregar catálogo"):
        st.cache_data.clear()
        st.rerun()

st.header("Calculadora IR — Bens e Direitos")

col1, col2 = st.columns(2)
with col1:
    earnings_file = st.file_uploader(
        "Proventos (earnings.xlsx)", type="xlsx", key="earnings_upload"
    )
with col2:
    negotiation_file = st.file_uploader(
        "Resumo de Negociação", type="xlsx", key="negotiation_upload"
    )

if not (earnings_file and negotiation_file):
    st.info("Suba os dois arquivos para gerar a prévia.")
    st.stop()

try:
    catalog = _cached_catalog()
    earnings = _cached_earnings(earnings_file.getvalue())
    negotiation = _cached_negotiation(negotiation_file.getvalue())
    assets = get_assets_and_rights(negotiation, earnings, catalog)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.subheader(f"Prévia — Bens e Direitos ({len(assets)} ativos)")
st.dataframe(pd.DataFrame(assets), use_container_width=True, hide_index=True)

missing_df = _missing_cnpj_df(assets)
if not missing_df.empty:
    st.warning(
        f"{len(missing_df)} ativo(s) sem CNPJ no catálogo. "
        "Preencha abaixo e salve para reaproveitar nas próximas execuções."
    )
    edited = st.data_editor(
        missing_df,
        num_rows="fixed",
        disabled=["Produto", "Grupo"],
        column_config={
            "CNPJ": st.column_config.TextColumn(
                "CNPJ",
                help="Pode colar com pontuação ou só dígitos.",
                required=False,
            ),
        },
        key="cnpj_editor",
        use_container_width=True,
    )
    if st.button("Salvar no catálogo", type="primary"):
        rows_to_save = [
            {"Ticker": r["Produto"], "Tipo": r["Grupo"], "CNPJ": str(r["CNPJ"]).strip()}
            for r in edited.to_dict(orient="records")
            if str(r["CNPJ"]).strip()
        ]
        if not rows_to_save:
            st.error("Nenhum CNPJ preenchido — nada para salvar.")
        else:
            save_overrides(rows_to_save)
            st.cache_data.clear()
            st.success(f"{len(rows_to_save)} CNPJ(s) salvos em data/cnpj_overrides.xlsx.")
            st.rerun()

st.divider()
st.download_button(
    "Baixar Bens_e_Direitos.xlsx",
    data=build_output_xlsx_bytes(assets),
    file_name="Bens_e_Direitos.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
