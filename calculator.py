from core import (
    build_output_xlsx_bytes,
    get_assets_and_rights,
    get_earnings,
    load_catalog,
    read_earnings,
    read_negotiation_summary,
)

if __name__ == "__main__":
    products_info = load_catalog()
    earnings = get_earnings(read_earnings("input/earnings.xlsx"))
    negotiation = read_negotiation_summary("input/negotiation_summary.xlsx")
    assets = get_assets_and_rights(negotiation, earnings, products_info)

    with open("output/Bens_e_Direitos.xlsx", "wb") as f:
        f.write(build_output_xlsx_bytes(assets))
