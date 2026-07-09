# Calculadora IR

Script em Python que auxilia na declaração anual do Imposto de Renda da Pessoa Física (DIRPF) a partir de planilhas exportadas da B3. Gera uma planilha pronta para a ficha **Bens e Direitos**, agrupando posições em ações, BDRs e fundos (FIIs/ETFs) e somando rendimentos, dividendos e JCP por ativo.

## O que o script faz

A partir de três planilhas de entrada, o script:

1. Lê o cadastro de empresas listadas na B3 (tipo, CNPJ, ticker).
2. Consolida os proventos por ativo (Rendimento, Juros Sobre Capital Próprio, Dividendo).
3. Para cada ativo com quantidade líquida positiva, monta uma linha com:
   - **Grupo** e **Código** corretos da declaração (Ações, BDRs, FIIs, ETFs).
   - **CNPJ** do produto.
   - **Discriminação** padrão (`Compra de TICKER na INSTITUIÇÃO com custo médio de R$ X,XX`).
   - **Situação final** (quantidade × preço médio de compra).
   - Totais de **Juros Sobre Capital Próprio**, **Dividendo** e **Rendimento**.
4. Exporta o resultado em [output/Bens_e_Direitos.xlsx](output/Bens_e_Direitos.xlsx).

## Pré-requisitos

- Python 3.9+
- [pandas](https://pandas.pydata.org/)
- [openpyxl](https://openpyxl.readthedocs.io/) (necessário para o pandas ler/escrever `.xlsx`)

Instalação:

```bash
pip install pandas openpyxl
```

## Estrutura de pastas

```
calculadora-IR/
├── calculator.py
├── data/
│   └── b3_enterprises.xlsx     # cadastro de empresas (versionado)
├── input/                      # arquivos de entrada (ignorados pelo git)
│   ├── earnings.xlsx
│   └── negotiation_summary.xlsx
└── output/                     # resultado (ignorado pelo git)
    └── Bens_e_Direitos.xlsx
```

Antes da primeira execução, crie as pastas `input/` e `output/`:

```bash
mkdir -p input output
```

## Arquivos de entrada

Todos os arquivos podem ser baixados na área do investidor da B3 ([investidor.b3.com.br](https://www.investidor.b3.com.br)).

### [data/b3_enterprises.xlsx](data/b3_enterprises.xlsx)

Já versionado no repositório. Contém o mapeamento entre `Ticker`, `Tipo` e `CNPJ` usado para preencher o campo CNPJ de cada ativo.

Colunas esperadas: `Ticker`, `Tipo`, `CNPJ`.

### [input/earnings.xlsx](input/earnings.xlsx)

Extrato de proventos exportado da B3 (menu **Extrato → Proventos**).

Colunas usadas: `Tipo de Evento`, `Produto`, `Valor líquido`.

Apenas eventos do tipo `Rendimento`, `Juros Sobre Capital Próprio` e `Dividendo` são considerados.

### [input/negotiation_summary.xlsx](input/negotiation_summary.xlsx)

Resumo de negociação da B3 (menu **Extrato → Negociação → aba Resumo**), exportado como Excel. Lê a aba `Negociação - Resumo`, que já traz uma linha por ativo com o preço médio de compra cumulativo.

**Importante:** ao exportar, selecione o período **desde a primeira compra** até `31/12` do ano-base. Caso contrário, `Preço Médio (Compra)` representará apenas a média do período exportado, e não o custo de aquisição real.

Após baixar, renomeie o arquivo para `negotiation_summary.xlsx` (a B3 nomeia com timestamp do tipo `negociacao-resumo-AAAA-MM-DD-HH-MM-SS.xlsx`).

Colunas usadas: `Código de Negociação`, `Instituição`, `Quantidade (Líquida)`, `Preço Médio (Compra)`.

Ativos com quantidade líquida ≤ 0 são ignorados. Tickers fracionários (terminados em `F`) são normalizados para o ticker padrão.

> **Migração:** versões anteriores deste script usavam `input/negotiation.xlsx` (relatório de Posição). Esse arquivo, assim como o histórico bruto de transações (`negociacao-AAAA-...xlsx`), não é mais usado e pode ser apagado.

## Como executar

A partir da raiz do projeto:

```bash
python calculator.py
```

O arquivo [output/Bens_e_Direitos.xlsx](output/Bens_e_Direitos.xlsx) será (re)criado com uma linha por ativo, pronto para conferência e lançamento manual no programa da Receita Federal.

## Regras de classificação

O grupo e código da declaração são inferidos pelo final do ticker:

| Final do ticker | Grupo                              | Código                                                                 |
| --------------- | ---------------------------------- | ---------------------------------------------------------------------- |
| `11` (IVVB11, SMAL11) | 07 - Fundos                  | 09 - Demais Fundos de Índice de Mercado (ETFs)                         |
| `11` (demais)   | 07 - Fundos                        | 03 - Fundos de Investimento Imobiliário (FII)                          |
| `34`            | 04 - Aplicações e Investimentos    | 04 - Ativos negociados em Bolsa no Brasil (BDRs, opções e outros...)   |
| outros          | 03 - Participações Societárias     | 01 - Ações (inclusive as listadas em bolsa)                            |

## Avisos

- O script não calcula imposto devido sobre ganho de capital nem preenche a ficha de **Rendimentos Isentos** ou **Tributação Exclusiva** — ele apenas consolida os dados para a ficha **Bens e Direitos**.
- Sempre confira os valores gerados contra os informes de rendimentos antes de transmitir a declaração.
