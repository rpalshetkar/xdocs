# Packaged Trade Dictionary

> Model-level reference for how a full multi-product OTC trade is represented.
> Three layers — **txn** (non-economic header) → **instrument** (market-conventional
> product) → **leg** (universal denormalized cashflow). One txn can compose many
> instruments; each instrument owns 1..N legs; every leg shares one schema.

## Design rules

1. **Txn is non-economic.** Identity, parties, xrefs, legal, confirmation. No rates. No notionals.
2. **Instrument is market-conventional.** Product names dealers use — `BOND`, `TRS`, `IRS`, `CCS`, `FX_SPOT`, `FX_SWAP`, `FX_NDF`. Each instrument carries its own clearing/fee block and owns its legs.
3. **Leg is denormalized universal.** One schema, one field list, sparsely populated. The `leg_type` plus sparsity tell you what product slice this leg represents.
4. **Masters are normalized.** Static instrument data (bond coupon/maturity/issuer, FX-pair conventions, FpML templates) lives in reference datasets. Per-trade recap only carries trade-specific deltas + a FK to the master.
5. **Links make the package.** `instrument.links[]` encodes cross-instrument relationships (`UNDERLYING_OF`, `HEDGES`, `FUNDED_BY`, `SETTLES`, `FUNDS`) — this is how a 7-instrument package stays coherent.
6. **Partial clearing is first-class.** Each instrument carries `clearing{}` independently. One packaged txn can have 2 instruments at LCH, 1 at KRX, 4 bilateral.

## Layer 1 — Txn (non-economic header)

```
txn_id                                (key)
txn_type              TRADE | ORDER | ALLOCATION | NOVATION | COMPRESSION
trade_date
booking_date
effective_date
termination_date
status                PENDING | CONFIRMED | CLEARED | SETTLED | CANCELLED
source                venue / message-source of origination
venue                 BILATERAL | TRADEWEB | BLOOMBERG_RFQ | ...

parties[]             role-based refs to parties dataset
  role                US | CPTY | CLEARING_CCP | CLEARING_MEMBER |
                      EXECUTING_BROKER | PRIME_BROKER | GIVE_UP_BROKER |
                      CALC_AGENT | PAYING_AGENT | CUSTODIAN
  party_id            FK → parties.name
  book_id             (optional) FK → books.name

xrefs[]               cross-system txn identifiers
  id_type             UTI | PACKAGE_ID | VENUE_REF | INTERNAL
  value
  source

is_package           bool — true when instruments[] length > 1

legal{}
  master_agreement_ref    ISDA / master netting agreement

confirmation{}
  method                  MARKITWIRE | PAPER | ELECTRONIC
  status                  PENDING | AFFIRMED | CONFIRMED | DISPUTED

instruments[]           ← the package
```

## Layer 2 — Instrument (market-conventional)

```
instrument_seq          ordering within txn (1..N)
role                    MAIN | UNDERLYING | HEDGE | FUNDING | SETTLEMENT |
                        RATE_HEDGE | LIQUIDITY | TERMINAL | INCEPTION
product_type            BOND | TRS | IRS | CCS | FX_SPOT | FX_SWAP | FX_NDF |
                        SWAPTION | FRA | REPO | CDS | FX_OPTION | EQUITY
instrument_master_id    optional FK → instruments dataset (static master)

recap{}                 product-level economics summary — headline terms only
                        (trade-specific slice; master holds shared static data)

conventions{}           market conventions that apply
                        (fx_pair ref, day_count, payment_freq, pricing_model, cut_time, ...)

clearing{}
  is_cleared
  ccp                   LCH | CME | EUREX | JSCC | KSPC | HKEX_OTC | SHCH
  clearing_member
  client_account
  clearing_ref
  clearing_date

fee{}                   optional fee attached to this instrument
  type                  COMMISSION | BROKERAGE | CLEARING | UPFRONT |
                        STRUCTURING | BREAK_FEE | MARKUP
  amount
  ccy
  bps_of_notional
  payment_date

links[]                 cross-instrument relationships within the package
  rel                   UNDERLYING_OF | HEDGES | FUNDED_BY | SETTLES |
                        FUNDS | MIRRORS
  target_instrument_seq

legs[]                  ← 1..N universal legs
```

## Layer 3 — Leg (universal denormalized)

One shape. All fields optional. Populate only what applies to `leg_type`.

```
leg_seq
leg_type                FIXED | FLOAT | SPOT | NEAR_LEG | FAR_LEG | NDF |
                        RETURN_LEG | FUNDING_LEG | BOND_LEG | PROTECTION_LEG |
                        PREMIUM_LEG | FEE | EQUITY_LEG
direction               PAY | RECEIVE | BUY | SELL | LONG | SHORT

# Size
notional
notional_ccy
quantity                for bonds/equities (units)

# Rate / Price
rate                    fixed rate / FX rate / option strike / bond coupon
index                   SOFR | EURIBOR | SONIA | KRW_CD91 | ...
spread_bps
price                   clean price for bonds
yield
fwd_points

# FX
ccy_pair
base_ccy
quote_ccy

# Dates
start_date              effective / value / trade-date
end_date                maturity / termination
fixing_date             NDF / rate-reset / option-exercise

# Calc conventions
day_count               ACT_360 | ACT_365 | 30_360 | ACT_ACT
payment_freq            MONTHLY | QUARTERLY | SEMI_ANNUAL | ANNUAL | AT_MATURITY
reset_freq              for floating legs
compounding             NONE | SIMPLE | COMPOUNDING | FLAT_COMPOUNDING
business_day_conv       MODIFIED_FOLLOWING | FOLLOWING | PRECEDING

# Product-specific (only one of these populated at a time)
underlying_ref          { instrument_seq: N }   — TRS, options, CDS
return_basis            TOTAL_RETURN | PRICE_ONLY | COUPON_ONLY   — TRS
fixing_source           WM_4PM | BFIX | BOK | BCB | RBI | EMTA | ...  — NDF
notional_exchange       bool                     — CCS principal flag
is_synthetic            bool                     — TRS reference leg flag

# Settlement (when leg produces a computed cash settlement)
settle{}
  ccy
  amount
  value_date
  formula                "notional * (fixing_rate - rate) / fixing_rate"
```

## Field usage by product

One leg schema, but sparsity tells the story. A `✓` means the field is
required for that product's leg; blank means left null.

| Field              | FX_SPOT | FX_SWAP | FX_NDF | IRS   | CCS   | TRS    | BOND  |
| ------------------ | ------- | ------- | ------ | ----- | ----- | ------ | ----- |
| notional + ccy     | ✓       | ✓       | ✓      | ✓     | ✓     | ✓      | ✓     |
| rate               | ✓       | ✓       | ✓      | ✓ fix | ✓ fix |        | ✓ cpn |
| index / spread_bps |         |         |        | ✓ flt | ✓ flt | ✓ fund |       |
| ccy_pair           | ✓       | ✓       | ✓      |       | ✓     |        |       |
| fwd_points         |         | ✓       |        |       |       |        |       |
| fixing_date/source |         |         | ✓      |       |       |        |       |
| day_count          |         |         |        | ✓     | ✓     | ✓      | ✓     |
| payment_freq       |         |         |        | ✓     | ✓     | ✓      | ✓     |
| reset_freq         |         |         |        | ✓ flt | ✓ flt | ✓ fund |       |
| underlying_ref     |         |         |        |       |       | ✓      |       |
| return_basis       |         |         |        |       |       | ✓      |       |
| settle{}           |         |         | ✓      |       |       |        |       |
| notional_exchange  |         |         |        |       | ✓     |        |       |
| quantity           |         |         |        |       |       |        | ✓     |

Every leg is queryable with the same field list. No product-specific
sub-schemas. Sparsity is the feature, not a cost.

## Worked example — "5Y synthetic USD-credit note for KRW client"

### Business rationale

**Client**: Korea Life Insurance Co. — KRW-natural, regulated by FSC, must book
KRW accounting, capital-treats USD securities punitively under K-ICS solvency.

**Investment objective**: 5Y exposure to USD-denominated Apple 4.50% 2031
corporate bond (higher spread than a KRW corporate of the same rating), but all
economics must be in KRW fixed.

**Why a single packaged trade, not seven separate ones**:

- Single ISDA confirm, single UTI, single MTM line in the client's risk system.
- One netting bucket across all seven instruments.
- Dealer's structuring team prices the package holistically; client doesn't leg
  into slippage.
- Unwind is atomic — client can't end up with orphan hedges.

### Package composition

| #   | Instrument | Role       | Purpose for client                        | Bank's hedge view            |
| --- | ---------- | ---------- | ----------------------------------------- | ---------------------------- |
| 1   | BOND       | UNDERLYING | Reference asset — Apple 5Y 4.50% USD      | Held in inventory or TRS src |
| 2   | TRS        | MAIN       | Deliver bond total return synthetically   | Short TR, long SOFR + 60     |
| 3   | CCS        | FUNDING    | Convert USD SOFR leg to KRW CD91 funding  | Offsets CCS basis            |
| 4   | IRS (KRW)  | RATE_HEDGE | Fix KRW CD91 stream to KRW 3.25% fixed    | Offsets KRW curve duration   |
| 5   | FX_SPOT    | INCEPTION  | Day-0 USD funding via KRW sale            | Spot book                    |
| 6   | FX_SWAP    | LIQUIDITY  | Rolling 3M KRW/USD swap for periodic flow | Funding book                 |
| 7   | FX_NDF     | TERMINAL   | Non-deliverable hedge of final USD face   | NDF book                     |

**Client net economics**: pays KRW 3.25% fixed quarterly on KRW 13.28bn
notional; receives USD→KRW converted bond total return at maturity. No USD on
their books at any point.

### Full packaged trade

```yaml
txn_id: FTTX-2026-04-17-KRW-APPLE-TRS-001
txn_type: TRADE
trade_date: 2026-04-17
booking_date: 2026-04-17
effective_date: 2026-04-21
termination_date: 2031-04-21
status: CONFIRMED
source: TRADEWEB
venue: BILATERAL

parties:
  - { role: US,              party_id: ftp-bank-abc,       book_id: EM-STRUCTURED-CREDIT }
  - { role: CPTY,            party_id: ftp-krlife-ins-01 }
  - { role: CALC_AGENT,      party_id: ftp-bank-abc }
  - { role: PAYING_AGENT,    party_id: ftp-citi-kr }
  - { role: CLEARING_CCP,    party_id: ftp-lch-ltd }
  - { role: CLEARING_MEMBER, party_id: ftp-bank-abc }

xrefs:
  - { id_type: UTI,         value: 1000ABC.20260417.KRW-APPLE-TRS.001, source: INTERNAL }
  - { id_type: VENUE_REF,   value: TW-MLX-7729555,                     source: TRADEWEB }

is_package: true

legal:
  master_agreement_ref: ISDA-2002-BANK-KRLIFE-2024-03-11

confirmation:
  method: MARKITWIRE
  status: PENDING

instruments:

# ─── Instrument #1: BOND (underlying reference) ─────────────────────────
- instrument_seq: 1
  role: UNDERLYING
  instrument_master_id: ftsc-corp-apple-4.50-2031
  product_type: BOND
  recap:
    isin: US037833DT06
    coupon: 4.50
    maturity: 2031-04-15
    observed_price: 99.85
    accrued_at_start: 0
  clearing: { is_cleared: false }
  legs:
    - leg_seq: 1
      leg_type: BOND_LEG
      direction: LONG
      quantity: 10_000_000
      notional_ccy: USD
      price: 99.85
      day_count: 30_360
      payment_freq: SEMI_ANNUAL
      start_date: 2026-04-21
      end_date: 2031-04-15
      is_synthetic: true

# ─── Instrument #2: TRS (main economic package) ─────────────────────────
- instrument_seq: 2
  role: MAIN
  instrument_master_id: null
  product_type: TRS
  recap:
    notional: 9_985_000
    notional_ccy: USD
    return_basis: TOTAL_RETURN
    funding_index: SOFR
    funding_spread_bps: 60
    payment_freq: QUARTERLY
  conventions:
    day_count_funding: ACT_360
    reset_freq: DAILY
    compounding: COMPOUNDING
    lookback_days: 2
  clearing: { is_cleared: false }
  fee:
    type: STRUCTURING
    amount: 12_500
    ccy: USD
    bps_of_notional: 1.25
    payment_date: 2026-04-21
  links:
    - { rel: UNDERLYING_OF, target_instrument_seq: 1 }
    - { rel: FUNDED_BY,     target_instrument_seq: 3 }
  legs:
    - leg_seq: 1
      leg_type: RETURN_LEG
      direction: PAY
      notional: 9_985_000
      notional_ccy: USD
      underlying_ref: { instrument_seq: 1 }
      return_basis: TOTAL_RETURN
      payment_freq: QUARTERLY
      start_date: 2026-04-21
      end_date: 2031-04-21
    - leg_seq: 2
      leg_type: FUNDING_LEG
      direction: RECEIVE
      notional: 9_985_000
      notional_ccy: USD
      index: SOFR
      spread_bps: 60
      day_count: ACT_360
      payment_freq: QUARTERLY
      reset_freq: DAILY
      compounding: COMPOUNDING
      start_date: 2026-04-21
      end_date: 2031-04-21

# ─── Instrument #3: CCS (converts USD funding to KRW funding) ───────────
- instrument_seq: 3
  role: FUNDING
  product_type: CCS
  recap:
    notional_usd: 9_985_000
    notional_krw: 13_280_050_000
    payment_freq: QUARTERLY
    notional_exchange: true
  conventions:
    ccy_pair: USDKRW
    day_count_usd: ACT_360
    day_count_krw: ACT_365
    fx_rate_inception: 1330.00
  clearing:
    is_cleared: true
    ccp: LCH
    clearing_member: ftp-bank-abc
    client_account: CM-KRLIFE-01
    clearing_ref: LCH.CCS.USDKRW.7729555
  links:
    - { rel: HEDGES, target_instrument_seq: 2 }
  legs:
    - leg_seq: 1
      leg_type: FLOAT
      direction: PAY
      notional: 9_985_000
      notional_ccy: USD
      index: SOFR
      spread_bps: 60
      day_count: ACT_360
      payment_freq: QUARTERLY
      reset_freq: DAILY
      notional_exchange: true
      start_date: 2026-04-21
      end_date: 2031-04-21
    - leg_seq: 2
      leg_type: FLOAT
      direction: RECEIVE
      notional: 13_280_050_000
      notional_ccy: KRW
      index: KRW_CD91
      spread_bps: -15
      day_count: ACT_365
      payment_freq: QUARTERLY
      reset_freq: QUARTERLY
      notional_exchange: true
      start_date: 2026-04-21
      end_date: 2031-04-21

# ─── Instrument #4: IRS (fixes KRW floating leg for client) ─────────────
- instrument_seq: 4
  role: RATE_HEDGE
  product_type: IRS
  recap:
    notional: 13_280_050_000
    notional_ccy: KRW
    fixed_rate: 3.25
    benchmark: KRW_CD91
    payment_freq: QUARTERLY
  conventions:
    day_count_fixed: ACT_365
    day_count_float: ACT_365
    business_day_conv: MODIFIED_FOLLOWING
  clearing:
    is_cleared: true
    ccp: KRX_KSPC
    clearing_member: ftp-bank-abc
    client_account: KSPC-KRLIFE-01
    clearing_ref: KSPC.IRS.KRW.8821447
  links:
    - { rel: HEDGES, target_instrument_seq: 3 }
  legs:
    - leg_seq: 1
      leg_type: FIXED
      direction: RECEIVE
      notional: 13_280_050_000
      notional_ccy: KRW
      rate: 3.25
      day_count: ACT_365
      payment_freq: QUARTERLY
      start_date: 2026-04-21
      end_date: 2031-04-21
    - leg_seq: 2
      leg_type: FLOAT
      direction: PAY
      notional: 13_280_050_000
      notional_ccy: KRW
      index: KRW_CD91
      spread_bps: 0
      day_count: ACT_365
      payment_freq: QUARTERLY
      reset_freq: QUARTERLY
      start_date: 2026-04-21
      end_date: 2031-04-21

# ─── Instrument #5: FX_SPOT (day-0 funding) ────────────────────────────
- instrument_seq: 5
  role: INCEPTION
  product_type: FX_SPOT
  recap:
    ccy_pair: USDKRW
    rate: 1330.00
    value_date: 2026-04-21
  conventions:
    pair_id: FTP-FXP-USDKRW
    settlement_days: 2
    deliverability: NDF
  clearing: { is_cleared: false }
  links:
    - { rel: FUNDS, target_instrument_seq: 2 }
  legs:
    - leg_seq: 1
      leg_type: SPOT
      direction: BUY
      notional: 9_985_000
      notional_ccy: USD
      ccy_pair: USDKRW
      rate: 1330.00
      start_date: 2026-04-21
      end_date: 2026-04-21

# ─── Instrument #6: FX_SWAP (liquidity roll for quarterly payments) ─────
- instrument_seq: 6
  role: LIQUIDITY
  product_type: FX_SWAP
  recap:
    ccy_pair: USDKRW
    near_date: 2026-07-21
    far_date: 2026-10-21
    near_rate: 1332.50
    far_rate: 1335.75
    swap_points: 325
  conventions:
    pair_id: FTP-FXP-USDKRW
    fwd_pts_scale: 100
    deliverability: NDF
  clearing: { is_cleared: false }
  links:
    - { rel: HEDGES, target_instrument_seq: 2 }
  legs:
    - leg_seq: 1
      leg_type: NEAR_LEG
      direction: BUY
      notional: 9_985_000
      notional_ccy: USD
      ccy_pair: USDKRW
      rate: 1332.50
      start_date: 2026-07-21
      end_date: 2026-07-21
    - leg_seq: 2
      leg_type: FAR_LEG
      direction: SELL
      notional: 9_985_000
      notional_ccy: USD
      ccy_pair: USDKRW
      rate: 1335.75
      start_date: 2026-10-21
      end_date: 2026-10-21

# ─── Instrument #7: FX_NDF (terminal hedge at maturity) ────────────────
- instrument_seq: 7
  role: TERMINAL
  product_type: FX_NDF
  recap:
    ccy_pair: USDKRW
    notional: 9_985_000
    notional_ccy: USD
    rate: 1410.00
    fixing_date: 2031-04-17
    value_date: 2031-04-21
    ndf_settlement_ccy: USD
  conventions:
    pair_id: FTP-FXP-USDKRW
    deliverability: NDF
    fixing_source: BOK
    fallback_fixing: EMTA_LOCAL
    emta_template_ref: KRW10
  clearing: { is_cleared: false }
  links:
    - { rel: SETTLES, target_instrument_seq: 2 }
  legs:
    - leg_seq: 1
      leg_type: NDF
      direction: SELL
      notional: 9_985_000
      notional_ccy: USD
      ccy_pair: USDKRW
      rate: 1410.00
      fixing_date: 2031-04-17
      fixing_source: BOK
      start_date: 2031-04-17
      end_date: 2031-04-21
      settle:
        ccy: USD
        value_date: 2031-04-21
        formula: "notional * (fixing_rate - rate) / fixing_rate"
```

## What this dictionary gives you

| Property                              | How                                                                                                       |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| One UTI, one package                  | `is_package: true` on txn header + single UTI across all instruments.                                     |
| Partial clearing supported            | Each instrument carries its own `clearing{}`. CCS+IRS at LCH/KRX, bond/FX/TRS bilateral — all in one txn. |
| No economics duplicated               | Bond terms live in master; TRS references via `underlying_ref: {instrument_seq: 1}`.                      |
| One leg schema for all products       | Every leg has the same field list, populated sparsely per `leg_type`.                                     |
| Instrument links traceable            | `links[]` encodes HEDGES / FUNDED_BY / UNDERLYING_OF / SETTLES / FUNDS — queryable graph.                 |
| Fee is structural                     | `fee{}` on instrument. Also expressible as `leg_type: FEE` when a standalone fee instrument is needed.    |
| Master + recap pattern normalizes ref | 1000 trades on the same bond ISIN = 1 master row + 1000 slim recaps. No static data duplication.          |

## See also

- [README.md](README.md) — ontology overview and dataset catalog
- [schemas/txn.yaml](schemas/txn.yaml) — txn schema (current; to be restructured per this doc)
- [schemas/leg.yaml](schemas/leg.yaml) — leg schema (current; to be aligned with universal shape)
- [schemas/instrument.yaml](schemas/instrument.yaml) — instrument master schema
- [schemas/fx_pair.yaml](schemas/fx_pair.yaml) — FX-pair reference master (Slice 2)
- [schemas/_partials/fx_conventions.yaml](schemas/_partials/fx_conventions.yaml) — FX conventions block
