import pandas as pd

REAL_DECIMAL_PLACES = 2

def get_earnings(df):
  earnings_per_product = {}
  for index, row in df.iterrows():
    event_type = row["Tipo de Evento"]
    if event_type not in ["Rendimento", "Juros Sobre Capital Próprio", "Dividendo"]:
      continue

    product_name = row["Produto"]
    product = product_name.split(" - ")[0]
    value = row["Valor líquido"]

    if product not in earnings_per_product:
      earnings_per_product[product] = {
        "Rendimento": 0,
        "Juros Sobre Capital Próprio": 0,
        "Dividendo": 0,
      }
    earnings_per_product[product][event_type] = round(earnings_per_product[product][event_type] + value, REAL_DECIMAL_PLACES)

  return earnings_per_product

def get_assets_and_rights(df, earnings_per_product):
  assets_and_rights = []
  for index, row in df.iterrows():
    product = row["Código de Negociação"]
    if product.endswith("F"):
      product = product[:-1]

    institution = row["Instituição"]
    curr_quantity = row["Quantidade (Líquida)"]
    price_bought = row["Preço Médio (Compra)"]
    aquisition_value = curr_quantity * price_bought
    if (curr_quantity <= 0): 
      continue

    interest, dividend, earnings = 0, 0, 0
    if product in earnings_per_product:
      interest = round(earnings_per_product[product]["Juros Sobre Capital Próprio"], REAL_DECIMAL_PLACES)
      dividend = round(earnings_per_product[product]["Dividendo"], REAL_DECIMAL_PLACES)
      earnings = round(earnings_per_product[product]["Rendimento"], REAL_DECIMAL_PLACES)


    assets_and_rights.append({
      "Grupo": get_product_group(product),
      "Código": get_product_code(product),
      "CNPJ": get_product_cnpj(product),
      "Discriminação": get_discrimination(product, institution, price_bought),
      "Situação final": round(aquisition_value, REAL_DECIMAL_PLACES),
      "Juros Sobre Capital Próprio": interest,
      "Dividendo": dividend,
      "Rendimento": earnings,
    })

  return assets_and_rights

def get_product_group(product):
  return "03 - Participações Societárias"

def get_product_code(product):
  return "01 - Ações"

def get_product_cnpj(product):
  return "Em desenvolvimento..."

def get_discrimination(product, institution, price_bought):
  return f"Compra de {product} na {institution} com custo médio de R$ {price_bought:.{REAL_DECIMAL_PLACES}f}"

if __name__ == "__main__":
  negotiation_df = pd.read_excel("input/negotiation.xlsx")
  earnings_df = pd.read_excel("input/earnings.xlsx")

  earnings = get_earnings(earnings_df)

  assets_and_rights = get_assets_and_rights(negotiation_df, earnings)

  pd.DataFrame(assets_and_rights).to_excel("output/Bens_e_Direitos.xlsx", index=False)
