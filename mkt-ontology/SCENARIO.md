# Scenario Analysis Engine — Design Specification

> Composable shift blocks + scenario definitions + MCP tool contracts
> for structured, disciplined P&L impact analysis across book hierarchy dimensions.
>
> **Core principle:** P&L impact = sensitivity × shift. Every greek in `measure.yaml`
> links to market data in `mkt.yaml` via shared axis coordinates. Shift blocks perturb
> mkt; the engine multiplies the matching greek by the perturbation to produce impact.

---

## Architecture Overview

```
┌─────────────────┐    composes     ┌───────────────────┐
│  SHIFT BLOCKS   │◄───────────────│    SCENARIOS       │
│  (atoms)        │  N shifts per   │  (compositions)   │
│                 │  scenario,      │   │
│  ta/tb/tc       │  with optional  │  components[]     │
│  filter + delta │  overrides      │  + override{}     │
│  metric_map     │                 │   │
└───────┬─────────┘                 └───────┬───────────┘
        │                               │
        │ shifts target mkt │ scenario_id
        │ + map to greeks               │
        ▼                                   ▼
┌─────────────────┐  shared axes   ┌───────────────────┐
│  MKT DATA       │◄─────────────►│  MEASURES          │
│  (mkt.yaml)     │  ta.tb.tc      │  (measure.yaml)   │
│                 │  coordinate    │    │
│  ta.tb.tc keys  │  join          │  ta.tb.tc keys    │
│  ya = level     │                │  ya = greek       │
│                 │                │  mkt_id = FK →mkt │
└────────┬────────┘                └───────┬───────────┘
         │                              │
         │ ya + delta     │ greek × delta
         │ = shocked level │ = P&L impact
         ▼                                 ▼
┌──────────────────────────────────────────────────────┐
│                 SCENARIO ENGINE       │
│                                       │
│  For each shift in scenario:          │
│    1. Find mkt records matching (ta,tb,tc) filter    │
│    2. Compute effective_delta per mkt point          │
│    3. Find measures with matching (ta,tb,tc) coords  │
│    4. P&L impact = measure.ya × effective_delta      │
│    5. Aggregate by slice group_by dimensions         │
│                                       │
│  measure.mkt_id FK links greek to its mkt input     │
│  book metadata (desk,lob,country) drives slicing    │
└──────────────────────────┬───────────────────────────┘
                                        │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌───────────────┐ ┌──────────────┐ ┌───────────────────┐
│  BOOK         │ │  MCP TOOL    │ │  SCENARIO RESULT  │
│  (enriched)   │ │  xds_*       │ │  (computed)       │
│               │ │              │ │    │
│  desk, lob,   │ │  slice{}     │ │  per group:       │
│  country,     │ │  group_by[]  │ │   greek (base)    │
│  trader_id,   │ │  metrics[]   │ │   shift (delta)   │
│  sub_desk     │ │              │ │   impact (g × Δ)  │
└───────────────┘ └──────────────┘ └───────────────────┘
```

**The discipline chain:**

1. Shift blocks target valid `mkt_key` patterns (ta/tb/tc axis convention)
2. Each shift declares a `metric_map` — which greek(s) in `measure.yaml` it impacts
3. The engine joins shift → mkt → measure via shared (ta, tb, tc) coordinates
4. `measure.mkt_id` FK provides the audit trail: which mkt point produced this greek
5. P&L impact = `measure.ya` (sensitivity) × `effective_delta` (from shift)
6. Scenarios compose registered shift blocks (FK enforced) + override specific fields
7. MCP tools only accept enum-bound slice dimensions (no free-form)
8. Results always show: `greek` (base sensitivity) → `shift` (delta applied) → `impact` (greek × shift)

---

## P&L Computation Model

The fundamental equation:

```
P&L_impact = Σ (sensitivity_i × shift_i)
```

Where:
- `sensitivity_i` comes from `measure.yaml` (the greek — DV01, FXDELTA, VEGA, etc.)
- `shift_i` comes from the scenario's shift block (the perturbation to mkt data)
- The join key is the shared `(ta, tb, tc)` axis coordinates

### Greek-to-Shift Mapping

Each shift block's `asset_class` determines which greeks in `measure.yaml` are used:

| Shift `asset_class` | Shift targets (mkt.tb)   | Matching Greek (measure.metric) | Measure axes used                | P&L formula                                    |
| ------------------- | ------------------------ | ------------------------------- | -------------------------------- | ---------------------------------------------- |
| `IR`                | `SOFR_SWAP`, `SOFR_DEPO` | `DV01`                          | ta=ccy, tb=curve, tc=tenor       | `DV01.ya × delta_bps`                          |
| `IR`                | `SOFR_3M6M_BASIS`        | `TBO1`                          | ta=ccy, tb=short_curve, tc=tenor | `TBO1.ya × delta_bps`                          |
| `FX` (SPOT)         | `FX_SPOT`                | `FXDELTA`                       | ta=pair, tb=cross                | `FXDELTA.ya × (delta_pct / 100)`               |
| `FX` (VOL)          | `FX_VOL`                 | `FXVEGA`                        | ta=pair, tb=tenor                | `FXVEGA.ya × delta_abs`                        |
| `CREDIT`            | `CDS_*`                  | `CS01` (credit DV01)            | ta=entity, tb=sector, tc=tenor   | `CS01.ya × delta_bps`                          |
| `IR_VOL`            | `IR_SWPNVOL`             | `VEGA`                          | ta=ccy, tb=expiry, tc=tenor      | `VEGA.ya × delta_bps`                          |
| `CORR`              | `CORR`                   | `CORR`                          | ta=factor1, tb=factor2           | `CORR.ya × delta_abs`                          |
| `FX` (FWD)          | `FX_FWD`                 | `FXDELTA` + `RHO`               | ta=pair, tb=tenor                | `FXDELTA.ya × fwd_delta + RHO.ya × rate_delta` |

### Coordinate Join Logic

The shift block's `(ta_filter, tb_filter, tc_filter)` matches BOTH mkt and measure records
because they share the same axis namespace:

```
Shift Block                  MKT record                MEASURE record
─────────────               ──────────                ──────────────
ta_filter: USD        ──►   ta: USD            ◄──►   ta: USD
tb_filter: SOFR_SWAP  ──►   tb: SOFR_SWAP      ◄──►   tb: SOFR        (curve name)
tc_filter: 5Y         ──►   tc: 5Y             ◄──►   tc: 5Y
                             mkt_id: ftmk-xxx   ◄────  mkt_id: ftmk-xxx  (FK audit)
                             ya: 4.25 (rate)           ya: -45000 (DV01/bp)
```

The `measure.mkt_id` FK closes the loop — it tells you exactly which mkt observation
was used to compute the greek. This provides:
- **Audit trail**: "This DV01 was computed using the 5Y SOFR rate of 4.25% from EOD snap"
- **Consistency**: shocked P&L uses the same mkt point the greek was calibrated against
- **Revaluation**: full reval can re-derive greeks from shocked mkt if needed

### Worked Example: Fed Hike 75bp on a 5Y IRS

```
Given:
  Book:     ftb-rates-flow-ny (desk=Rates Flow, lob=FICC, country=US)
  Trade:    5Y pay-fixed IRS, $50M notional

Step 1 — Load base measures (from measure.yaml, snap=EOD):
  DV01 at 5Y SOFR:   measure.ya = -45,000/bp    measure.mkt_id → ftmk-sofr-5y
  FXDELTA on EURUSD:  measure.ya = 0             (USD-denominated, no FX risk)
  THETA:              measure.ya = -3,200/day

Step 2 — Load base mkt (from mkt.yaml, snap=EOD):
  ftmk-sofr-5y:  ta=USD, tb=SOFR_SWAP, tc=5Y, ya=4.25 (rate)

Step 3 — Apply shift (IR.PARALLEL.USD_SOFR_UP75):
  Matches mkt where ta=USD, tb=SOFR_*, tc=*
  ftmk-sofr-5y matches → effective_delta = +75bp
  shocked ya = 4.25 + 0.75 = 5.00

Step 4 — Compute P&L impact via greeks:
  IR impact  = DV01 × shift  = -45,000 × 75  = -$3,375,000
  FX impact  = FXDELTA × 0   = $0
  Theta      = not shifted    = $0 (theta is time decay, not market shift)
  ─────────────────────────────────────────────
  Total P&L impact = -$3,375,000

Step 5 — Also apply FX shift (FX.SPOT.EURUSD_DN3PCT):
  No EURUSD exposure on this trade → $0 additional impact

Step 6 — Also apply credit shift (CREDIT.SPREAD.IG_WIDEN50):
  No credit exposure on vanilla IRS → $0 additional impact

  TOTAL SCENARIO IMPACT = -$3,375,000
```

### Worked Example: Fed Hike 75bp on an FX NDF

```
Given:
  Book:     ftb-em-fx-hk (desk=EM FX, lob=FICC, country=HK)
  Trade:    3M EUR/USD NDF, EUR 10M notional

Step 1 — Load base measures:
  FXDELTA on EURUSD:  measure.ya = 8,500,000    measure.mkt_id → ftmk-eurusd-spot
  DV01 at 3M SOFR:    measure.ya = -4,500/bp    measure.mkt_id → ftmk-sofr-3m
  FXVEGA on EURUSD:   measure.ya = 0            (NDF, no optionality)

Step 2 — Apply shift IR.PARALLEL.USD_SOFR_UP75:
  Matches DV01 at 3M → effective_delta = +75bp
  IR impact = -4,500 × 75 = -$337,500

Step 3 — Apply shift FX.SPOT.EURUSD_DN3PCT:
  Matches FXDELTA on EURUSD → effective_delta = -3%
  FX impact = 8,500,000 × (-0.03) = -$255,000

Step 4 — Apply shift FX.VOL.EURUSD_UP2VOL:
  FXVEGA = 0 (NDF has no optionality) → $0

  TOTAL SCENARIO IMPACT = -$337,500 + (-$255,000) = -$592,500
```

### Second-Order Effects (Gamma, Cross-Gamma)

For large shifts, linear approximation (greek × delta) can be insufficient.
The engine supports optional second-order terms:

```
P&L_impact = (greek × Δ) + ½ × (gamma × Δ²)

Where:
  gamma = measure.metric=GAMMA, same (ta,tb,tc) coords
  Δ = effective shift magnitude
```

Cross-gamma (e.g., FX cross-gamma between EURUSD and GBPUSD) uses the 2D coords:

```
Cross_PNL = cross_gamma × Δ_pair1 × Δ_pair2

Where:
  measure.metric = CROSS_GAMMA
  measure.coords = { ccy_pair_1: EURUSD, ccy_pair_2: GBPUSD }
  Δ_pair1 = EURUSD shift, Δ_pair2 = GBPUSD shift
```

---

## 1. Shift Blocks (Atoms)

Each shift block targets a slice of `mkt.yaml` data via the `ta.tb.tc` filter convention.
The `metric_map` field declares which greek(s) from `measure.yaml` are used to compute
P&L impact. This is the link between the market data shift and the risk sensitivity.

### Interest Rate Shifts

```yaml
- shift_id: ftss-ir-par-usd-up75
  shift_key: IR.PARALLEL.USD_SOFR_UP75
  name: "USD SOFR +75bp Parallel"
  asset_class: IR
  shift_type: PARALLEL
  ta_filter: USD            # ccy = USD
  tb_filter: SOFR_*         # all SOFR instruments (SOFR_DEPO, SOFR_SWAP, SOFR_FRA...)
  tc_filter: "*"            # all tenors
  delta_bps: 75             # +75bp across entire curve
  metric_map:               # which greeks this shift impacts
    - metric: DV01          # primary: IR sensitivity per bp
      measure_ta: USD       # measure axis match (same as shift ta)
      measure_tb: SOFR      # measure curve name (maps from mkt tb=SOFR_SWAP)
      formula: "ya × delta_bps"  # DV01/bp × 75bp = P&L
    - metric: GAMMA         # optional 2nd order
      formula: "0.5 × ya × delta_bps²"

- shift_id: ftss-ir-par-usd-dn50
  shift_key: IR.PARALLEL.USD_SOFR_DN50
  name: "USD SOFR -50bp Parallel"
  asset_class: IR
  shift_type: PARALLEL
  ta_filter: USD
  tb_filter: SOFR_*
  tc_filter: "*"
  delta_bps: -50
  metric_map:
    - metric: DV01
      measure_ta: USD
      measure_tb: SOFR
      formula: "ya × delta_bps"

- shift_id: ftss-ir-steep-usd-2s10s-25
  shift_key: IR.STEEPENER.USD_2s10s_25
  name: "USD 2s10s Steepener +25bp"
  asset_class: IR
  shift_type: STEEPENER
  ta_filter: USD
  tb_filter: SOFR_SWAP
  tc_filter: "*"
  na_min: 0               # from front end
  na_max: 360             # to 30Y
  delta_bps: 50           # total magnitude
  weight_at_min: -0.5     # short end: -25bp
  weight_at_max: +0.5     # long end: +25bp
                           # belly (5Y = 60m): ~-8bp (linear interp)
  metric_map:
    - metric: DV01
      measure_ta: USD
      measure_tb: SOFR
      formula: "ya × effective_delta_bps(na)"  # delta varies by tenor via weights

- shift_id: ftss-ir-flat-usd-5s30s-20
  shift_key: IR.FLATTENER.USD_5s30s_20
  name: "USD 5s30s Flattener -20bp"
  asset_class: IR
  shift_type: FLATTENER
  ta_filter: USD
  tb_filter: SOFR_SWAP
  tc_filter: "*"
  na_min: 60              # from 5Y
  na_max: 360             # to 30Y
  delta_bps: 40
  weight_at_min: +0.5     # 5Y: +20bp
  weight_at_max: -0.5     # 30Y: -20bp
  metric_map:
    - metric: DV01
      measure_ta: USD
      measure_tb: SOFR
      formula: "ya × effective_delta_bps(na)"
```

### FX Shifts

```yaml
- shift_id: ftss-fx-spot-eurusd-dn3
  shift_key: FX.SPOT.EURUSD_DN3PCT
  name: "EUR/USD Spot -3%"
  asset_class: FX
  shift_type: SPOT
  ta_filter: EURUSD
  tb_filter: FX_SPOT
  tc_filter: SPOT
  delta_pct: -3.0          # multiplicative: spot * 0.97
  metric_map:
    - metric: FXDELTA       # primary: FX delta exposure
      measure_ta: EURUSD
      formula: "ya × (delta_pct / 100)"  # delta × -0.03
    - metric: GAMMA         # optional 2nd order (FX gamma)
      formula: "0.5 × ya × (delta_pct / 100)²"

- shift_id: ftss-fx-spot-usdjpy-up5
  shift_key: FX.SPOT.USDJPY_UP5PCT
  name: "USD/JPY Spot +5%"
  asset_class: FX
  shift_type: SPOT
  ta_filter: USDJPY
  tb_filter: FX_SPOT
  tc_filter: SPOT
  delta_pct: 5.0
  metric_map:
    - metric: FXDELTA
      measure_ta: USDJPY
      formula: "ya × (delta_pct / 100)"

- shift_id: ftss-fx-vol-eurusd-up2
  shift_key: FX.VOL.EURUSD_UP2VOL
  name: "EUR/USD Vol Surface +2 vol pts"
  asset_class: FX
  shift_type: VOL
  ta_filter: EURUSD
  tb_filter: FX_VOL
  tc_filter: "*"           # all expiry/delta/side combos
  delta_abs: 2.0           # +2 absolute vol points
  metric_map:
    - metric: FXVEGA        # FX vega per vol point
      measure_ta: EURUSD
      formula: "ya × delta_abs"  # vega × 2 vol pts
```

### Credit Shifts

```yaml
- shift_id: ftss-cr-spread-ig-widen50
  shift_key: CREDIT.SPREAD.IG_WIDEN50
  name: "IG Credit Spreads +50bp"
  asset_class: CREDIT
  shift_type: SPREAD
  ta_filter: "*"
  tb_filter: CDS_*
  tc_filter: "*"
  delta_bps: 50
  tags: [ig, spread, stress]
  metric_map:
    - metric: CS01           # credit spread sensitivity (like DV01 for credit)
      formula: "ya × delta_bps"

- shift_id: ftss-cr-spread-hy-widen200
  shift_key: CREDIT.SPREAD.HY_WIDEN200
  name: "HY Credit Spreads +200bp"
  asset_class: CREDIT
  shift_type: SPREAD
  ta_filter: "*"
  tb_filter: CDS_HY_*
  tc_filter: "*"
  delta_bps: 200
  tags: [hy, spread, stress]
  metric_map:
    - metric: CS01
      formula: "ya × delta_bps"
```

### Correlation Shifts

```yaml
- shift_id: ftss-corr-eurusd-usdjpy-dn10
  shift_key: CORR.LEVEL.EURUSD_USDJPY_DN10
  name: "EUR/USD vs USD/JPY Corr -10%"
  asset_class: CORR
  shift_type: LEVEL
  ta_filter: EURUSD_USDJPY
  tb_filter: CORR
  tc_filter: "*"
  delta_abs: -0.10         # correlation drop by 0.10
  metric_map:
    - metric: CORR           # correlation sensitivity
      measure_ta: EURUSD
      measure_tb: USDJPY
      formula: "ya × delta_abs"
```

### IR Swaption Vol

```yaml
- shift_id: ftss-irvol-usd-up5nvol
  shift_key: IR_VOL.SURFACE.USD_UP5NVOL
  name: "USD Swaption NVol +5bp"
  asset_class: IR_VOL
  shift_type: SURFACE
  ta_filter: USD
  tb_filter: IR_SWPNVOL
  tc_filter: "*"
  delta_bps: 5             # +5bp normal vol
  metric_map:
    - metric: VEGA           # IR vega (swaption sensitivity to vol)
      measure_ta: USD
      formula: "ya × delta_bps"
```

---

## 2. Scenarios (Compose Shift Blocks)

### Macro Scenarios

```yaml
- scenario_id: ftsc-fed-hike-75
  scenario_key: MACRO.FED_HIKE_75
  name: "Fed Hike 75bp"
  category: MONETARY_POLICY
  severity: STRESS
  description: "Aggressive Fed tightening: +75bp rates, USD strengthens, IG spreads widen"
  tags: [fed, tightening, regulatory, ccar]

  components:
    - shift_id: ftss-ir-par-usd-up75       # USD SOFR +75bp
    - shift_id: ftss-fx-spot-eurusd-dn3    # EUR/USD -3%
    - shift_id: ftss-fx-spot-usdjpy-up5    # USD/JPY +5% (USD strength)
    - shift_id: ftss-cr-spread-ig-widen50   # IG spreads +50bp
    - shift_id: ftss-fx-vol-eurusd-up2      # FX vol up

- scenario_id: ftsc-soft-landing
  scenario_key: MACRO.SOFT_LANDING
  name: "Soft Landing"
  category: MONETARY_POLICY
  severity: MODERATE
  description: "Goldilocks: rates ease, risk-on, spreads tighten, vol compresses"
  tags: [fed, easing, benign]

  components:
    - shift_id: ftss-ir-par-usd-dn50       # USD SOFR -50bp
    - shift_id: ftss-fx-spot-eurusd-dn3    # EUR still weakens (divergence)
      override:
        delta_pct: +2.0                     # OVERRIDE: EUR strengthens in soft landing
    - shift_id: ftss-cr-spread-ig-widen50
      override:
        delta_bps: -25                      # OVERRIDE: spreads TIGHTEN 25bp
    - shift_id: ftss-fx-vol-eurusd-up2
      override:
        delta_abs: -1.5                     # OVERRIDE: vol compresses

- scenario_id: ftsc-stagflation
  scenario_key: MACRO.STAGFLATION
  name: "Stagflation"
  category: MACRO
  severity: SEVERE
  description: "Worst case: rates up, growth down, spreads blow out, FX vol spikes"
  tags: [stress, severe, ccar]

  components:
    - shift_id: ftss-ir-par-usd-up75
      override:
        delta_bps: 150                      # more aggressive: +150bp
    - shift_id: ftss-ir-steep-usd-2s10s-25  # curve steepens (growth fears)
      override:
        delta_bps: 80                       # steeper: 80bp magnitude
    - shift_id: ftss-fx-spot-eurusd-dn3
      override:
        delta_pct: -8.0                     # EUR crashes -8%
    - shift_id: ftss-cr-spread-ig-widen50
      override:
        delta_bps: 150                      # IG blows out +150bp
    - shift_id: ftss-cr-spread-hy-widen200  # HY +200bp on top
    - shift_id: ftss-fx-vol-eurusd-up2
      override:
        delta_abs: 8.0                      # vol spikes +8 pts
    - shift_id: ftss-irvol-usd-up5nvol
      override:
        delta_bps: 20                       # swaption vol +20bp nvol
    - shift_id: ftss-corr-eurusd-usdjpy-dn10  # correlations break down

- scenario_id: ftsc-em-crisis
  scenario_key: MACRO.EM_CRISIS
  name: "EM Crisis (Asia)"
  category: GEOPOLITICAL
  severity: SEVERE
  description: "Asia EM crisis: CNY deval, HKD peg pressure, JPY safe haven bid"
  tags: [em, asia, crisis]

  components:
    - shift_id: ftss-fx-spot-usdjpy-up5
      override:
        delta_pct: -8.0                     # JPY strengthens (safe haven)
    - shift_id: ftss-fx-vol-eurusd-up2
      override:
        ta_filter: "*"                      # all FX vols spike
        delta_abs: 5.0
    - shift_id: ftss-cr-spread-hy-widen200
      override:
        delta_bps: 400                      # EM HY blows out +400bp

- scenario_id: ftsc-basis-blowout
  scenario_key: RATES.BASIS_BLOWOUT
  name: "XCCY Basis Blowout"
  category: LIQUIDITY
  severity: STRESS
  description: "Dollar funding stress: xccy basis widens, tenor basis dislocates"
  tags: [basis, funding, liquidity]

  components:
    - shift_id: ftss-ir-par-usd-up75
      override:
        delta_bps: 25                       # mild rate move
    - inline_shift:
        name: "EUR/USD XCCY Basis -40bp"
        asset_class: FX
        shift_type: BASIS
        ta_filter: EURUSD
        tb_filter: XCCY_SWAP
        tc_filter: "*"
        delta_bps: -40
```

### Regulatory Scenarios (FRTB, CCAR Prescribed)

```yaml
- scenario_id: ftsc-frtb-ir-up
  scenario_key: REG.FRTB_IR_UP
  name: "FRTB IR Shock Up"
  category: REGULATORY
  severity: PRESCRIBED
  description: "FRTB SA prescribed interest rate shock — parallel up"
  regulatory_ref: "BCBS d457, MAR21.3"
  tags: [frtb, regulatory, prescribed]

  components:
    - shift_id: ftss-ir-par-usd-up75
      override:
        delta_bps: 100                      # FRTB prescribed: +100bp

- scenario_id: ftsc-frtb-ir-steep
  scenario_key: REG.FRTB_IR_STEEP
  name: "FRTB IR Steepener"
  category: REGULATORY
  severity: PRESCRIBED
  regulatory_ref: "BCBS d457, MAR21.3"
  tags: [frtb, regulatory, prescribed]

  components:
    - shift_id: ftss-ir-steep-usd-2s10s-25
      override:
        delta_bps: 65                       # FRTB prescribed steepener
```

### Historical Scenarios (Replay Actual Market Moves)

```yaml
- scenario_id: ftsc-covid-mar2020
  scenario_key: HIST.COVID_MAR2020
  name: "COVID March 2020"
  category: HISTORICAL
  severity: SEVERE
  description: "Replay March 2020: rates crash, spreads explode, FX vol spikes, correlations break"
  reference_period: { start: "2020-02-20", end: "2020-03-23" }
  tags: [historical, covid, pandemic]

  components:
    - shift_id: ftss-ir-par-usd-dn50
      override:
        delta_bps: -150                     # rates crashed ~150bp
    - shift_id: ftss-cr-spread-ig-widen50
      override:
        delta_bps: 300                      # IG from 50bp to 350bp
    - shift_id: ftss-cr-spread-hy-widen200
      override:
        delta_bps: 600                      # HY from 400bp to 1000bp+
    - shift_id: ftss-fx-vol-eurusd-up2
      override:
        ta_filter: "*"
        delta_abs: 12.0                     # vol doubled
    - shift_id: ftss-corr-eurusd-usdjpy-dn10
      override:
        ta_filter: "*"                      # all correlations
        delta_abs: -0.30                    # correlations broke down
```

---

## 3. Book Metadata (Enriched for Slicing)

New fields added to `book.yaml` for scenario P&L slicing:

```yaml
- book_id: ftb-rates-flow-ny
  name: "Rates Flow NY"
  entity_id: fte-mybank-us
  desk: "Rates Flow"
  sub_desk: "SOFR Swaps"           # NEW
  lob: FICC                        # NEW
  country: US                       # NEW
  region: US
  trader_id: fte-trader-jsmith      # NEW — book owner
  strategy: "Market Making"
  book_type: TRADING
  ccy: USD
  cost_center: "CC-4201"            # NEW

- book_id: ftb-credit-ig-ldn
  name: "Credit IG London"
  entity_id: fte-mybank-uk
  desk: "Credit Trading"
  sub_desk: "IG Flow"
  lob: FICC
  country: GB
  region: EU
  trader_id: fte-trader-agarcia
  strategy: "Relative Value"
  book_type: TRADING
  ccy: USD
  cost_center: "CC-5102"

- book_id: ftb-em-fx-hk
  name: "EM FX Hong Kong"
  entity_id: fte-mybank-hk
  desk: "EM FX"
  sub_desk: "Asia NDF"
  lob: FICC
  country: HK
  region: APAC
  trader_id: fte-trader-kwong
  strategy: "Flow"
  book_type: TRADING
  ccy: USD
  cost_center: "CC-6301"
```

---

## 4. MCP Tool Contracts

### `xds_scenario_define` — Create/Update Scenarios

```yaml
xds_scenario_define:
  description: "Create or update a scenario from shift block components"
  params:
    scenario_id:    { type: str, required: false, description: "Omit for create, provide for update" }
    name:           { type: str, required: true }
    category:       { type: str, required: true, enum: [MONETARY_POLICY, MACRO, GEOPOLITICAL, LIQUIDITY, REGULATORY, HISTORICAL, CUSTOM] }
    severity:       { type: str, required: true, enum: [MILD, MODERATE, STRESS, SEVERE, PRESCRIBED] }
    components:
      type: list
      required: true
      min_items: 1
      items:
        type: dict
        items:
          shift_id:     { type: str, ref: scenario_shifts.shift_id, description: "Reference to reusable shift block" }
          override:     { type: dict, description: "Override any field on the shift block for this scenario" }
          inline_shift: { type: dict, description: "One-off shift defined inline (when no reusable block exists)" }
    tags:           { type: list[str] }
```

### `xds_scenario_run` — Execute Scenario Against Portfolio Slice

```yaml
xds_scenario_run:
  description: "Run a scenario against a portfolio slice. Returns P&L impact."
  params:
    # -- WHAT to run --
    scenario_id:    { type: str, required: true, ref: scenarios.scenario_id }

    # -- WHERE to run (slice) -- at least one dimension required
    slice:
      type: dict
      min_properties: 1
      items:
        book_id:      { type: list[str], ref: books.book_id }
        desk:         { type: list[str], enum: $enums.ENUM_DESK }
        sub_desk:     { type: list[str] }
        lob:          { type: list[str], enum: $enums.ENUM_LOB }
        country:      { type: list[str], enum: $enums.ENUM_COUNTRY }
        region:       { type: list[str], enum: $enums.ENUM_REGION }
        trader_id:    { type: list[str], ref: entities.entity_id }
        product_type: { type: list[str], enum: $enums.ENUM_PRODUCT_TYPE }

    # -- HOW to compute --
    base_snap:      { type: str, enum: [SOD, LIVE, EOD], default: EOD }
    as_of_date:     { type: date, default: TODAY }

    # -- WHAT to return --
    metrics:        { type: list[str], enum: $enums.ENUM_METRIC, default: [PNL, DV01, MTM] }
    group_by:       { type: list[str], enum: [BOOK, DESK, SUB_DESK, LOB, COUNTRY, REGION, TRADER, PRODUCT_TYPE, TENOR, CURVE, CCY], default: [BOOK] }
    include_details: { type: bool, default: false }
```

### `xds_scenario_compare` — Side-by-Side Multiple Scenarios

```yaml
xds_scenario_compare:
  description: "Compare P&L impact of multiple scenarios on the same slice"
  params:
    scenario_ids:   { type: list[str], required: true, min_items: 2, ref: scenarios.scenario_id }
    slice:                              # same structure as xds_scenario_run
      type: dict
      min_properties: 1
      items:
        book_id:      { type: list[str], ref: books.book_id }
        desk:         { type: list[str], enum: $enums.ENUM_DESK }
        sub_desk:     { type: list[str] }
        lob:          { type: list[str], enum: $enums.ENUM_LOB }
        country:      { type: list[str], enum: $enums.ENUM_COUNTRY }
        region:       { type: list[str], enum: $enums.ENUM_REGION }
        trader_id:    { type: list[str], ref: entities.entity_id }
        product_type: { type: list[str], enum: $enums.ENUM_PRODUCT_TYPE }
    metrics:        { type: list[str], default: [PNL] }
    group_by:       { type: list[str], default: [BOOK] }
```

### `xds_risk_slice` — Pull Current Risk by Dimensions (No Scenario)

```yaml
xds_risk_slice:
  description: "Pull current risk measures sliced by book hierarchy dimensions"
  params:
    slice:                              # same filter structure
      type: dict
      min_properties: 1
      items:
        book_id:      { type: list[str], ref: books.book_id }
        desk:         { type: list[str], enum: $enums.ENUM_DESK }
        sub_desk:     { type: list[str] }
        lob:          { type: list[str], enum: $enums.ENUM_LOB }
        country:      { type: list[str], enum: $enums.ENUM_COUNTRY }
        region:       { type: list[str], enum: $enums.ENUM_REGION }
        trader_id:    { type: list[str], ref: entities.entity_id }
        product_type: { type: list[str], enum: $enums.ENUM_PRODUCT_TYPE }
    metrics:        { type: list[str], enum: $enums.ENUM_METRIC, required: true }
    group_by:       { type: list[str], required: true }
    snap:           { type: str, enum: [SOD, LIVE, EOD], default: LIVE }
    as_of_date:     { type: date, default: TODAY }
```

---

## 5. Example MCP Calls + Results

### Call 1: "Fed Hike impact on FICC APAC"

```json
{
  "tool": "xds_scenario_run",
  "params": {
    "scenario_id": "ftsc-fed-hike-75",
    "slice": { "lob": ["FICC"], "region": ["APAC"] },
    "metrics": ["PNL", "DV01", "FXDELTA"],
    "group_by": ["DESK", "PRODUCT_TYPE"]
  }
}
```

**Result** (shows greek × shift decomposition):

```json
{
  "scenario": "Fed Hike 75bp",
  "as_of": "2026-03-19",
  "base_snap": "EOD",
  "results": [
    {
      "desk": "EM FX",
      "product_type": "FX_NDF",
      "PNL": {
        "impact": -592500,
        "ccy": "USD",
        "breakdown": [
          {
            "shift": "IR.PARALLEL.USD_SOFR_UP75",
            "greek": "DV01",
            "greek_value": -4500,
            "greek_unit": "PER_BP",
            "shift_delta": 75,
            "shift_unit": "bps",
            "impact": -337500,
            "formula": "DV01 × Δbps = -4,500 × 75",
            "mkt_ref": { "mkt_id": "ftmk-sofr-3m", "mkt_key": "USD.SOFR_SWAP.3M", "base_ya": 4.85 }
          },
          {
            "shift": "FX.SPOT.EURUSD_DN3PCT",
            "greek": "FXDELTA",
            "greek_value": 8500000,
            "greek_unit": "ABSOLUTE",
            "shift_delta": -0.03,
            "shift_unit": "pct",
            "impact": -255000,
            "formula": "FXDELTA × Δpct = 8,500,000 × -0.03",
            "mkt_ref": { "mkt_id": "ftmk-eurusd-spot", "mkt_key": "EURUSD.FX_SPOT.SPOT", "base_ya": 1.0842 }
          }
        ]
      },
      "DV01":    { "base": -4500 },
      "FXDELTA": { "base": 8500000 }
    },
    {
      "desk": "Rates Flow",
      "product_type": "IRS",
      "PNL": {
        "impact": -3375000,
        "ccy": "USD",
        "breakdown": [
          {
            "shift": "IR.PARALLEL.USD_SOFR_UP75",
            "greek": "DV01",
            "greek_value": -45000,
            "greek_unit": "PER_BP",
            "shift_delta": 75,
            "shift_unit": "bps",
            "impact": -3375000,
            "formula": "DV01 × Δbps = -45,000 × 75",
            "mkt_ref": { "mkt_id": "ftmk-sofr-5y", "mkt_key": "USD.SOFR_SWAP.5Y", "base_ya": 4.25 }
          },
          {
            "shift": "FX.SPOT.EURUSD_DN3PCT",
            "greek": "FXDELTA",
            "greek_value": 0,
            "shift_delta": -0.03,
            "impact": 0,
            "formula": "FXDELTA × Δpct = 0 × -0.03 (no FX exposure)"
          }
        ]
      },
      "DV01":    { "base": -45000 },
      "FXDELTA": { "base": 0 }
    }
  ],
  "totals": {
    "PNL": { "impact": -3967500 },
    "by_shift": {
      "IR.PARALLEL.USD_SOFR_UP75":  { "impact": -3712500 },
      "FX.SPOT.EURUSD_DN3PCT":      { "impact": -255000 },
      "FX.VOL.EURUSD_UP2VOL":       { "impact": 0 },
      "CREDIT.SPREAD.IG_WIDEN50":    { "impact": 0 }
    },
    "by_greek": {
      "DV01":    { "total_impact": -3712500 },
      "FXDELTA": { "total_impact": -255000 },
      "FXVEGA":  { "total_impact": 0 },
      "CS01":    { "total_impact": 0 }
    }
  }
}
```

### Call 2: "Compare Fed Hike vs Soft Landing across all desks"

```json
{
  "tool": "xds_scenario_compare",
  "params": {
    "scenario_ids": ["ftsc-fed-hike-75", "ftsc-soft-landing"],
    "slice": { "lob": ["FICC"] },
    "metrics": ["PNL"],
    "group_by": ["DESK", "COUNTRY"]
  }
}
```

**Result:**

```json
{
  "comparison": ["Fed Hike 75bp", "Soft Landing"],
  "results": [
    {
      "desk": "Rates Flow", "country": "US",
      "Fed Hike 75bp": {
        "PNL_impact": -3375000,
        "dominant_greek": "DV01",
        "dominant_shift": "IR.PARALLEL.USD_SOFR_UP75",
        "greek_value": -45000,
        "shift_delta": 75
      },
      "Soft Landing": {
        "PNL_impact": 2250000,
        "dominant_greek": "DV01",
        "dominant_shift": "IR.PARALLEL.USD_SOFR_DN50",
        "greek_value": -45000,
        "shift_delta": -50
      }
    },
    {
      "desk": "Credit IG", "country": "GB",
      "Fed Hike 75bp": {
        "PNL_impact": -1800000,
        "dominant_greek": "CS01",
        "dominant_shift": "CREDIT.SPREAD.IG_WIDEN50",
        "greek_value": -36000,
        "shift_delta": 50
      },
      "Soft Landing": {
        "PNL_impact": 900000,
        "dominant_greek": "CS01",
        "dominant_shift": "CREDIT.SPREAD.IG_WIDEN50 (override: -25bp)",
        "greek_value": -36000,
        "shift_delta": -25
      }
    },
    {
      "desk": "EM FX", "country": "HK",
      "Fed Hike 75bp": {
        "PNL_impact": -592500,
        "dominant_greek": "DV01",
        "by_greek": { "DV01": -337500, "FXDELTA": -255000 }
      },
      "Soft Landing": {
        "PNL_impact": 395000,
        "dominant_greek": "FXDELTA",
        "by_greek": { "DV01": 225000, "FXDELTA": 170000 }
      }
    }
  ]
}
```

### Call 3: "Current DV01 risk by LOB and tenor"

```json
{
  "tool": "xds_risk_slice",
  "params": {
    "slice": { "region": ["US"] },
    "metrics": ["DV01"],
    "group_by": ["LOB", "TENOR"],
    "snap": "LIVE"
  }
}
```

**Result:**

```json
{
  "results": [
    { "lob": "FICC", "tenor": "1Y",  "DV01": -12000 },
    { "lob": "FICC", "tenor": "2Y",  "DV01": -28000 },
    { "lob": "FICC", "tenor": "5Y",  "DV01": -45000 },
    { "lob": "FICC", "tenor": "10Y", "DV01": -32000 },
    { "lob": "FICC", "tenor": "30Y", "DV01": -8000 }
  ]
}
```

---

## 6. Shift Block Schema Reference

The `scenario_shift.yaml` schema follows the axis convention:

| Field           | Type  | Purpose                                                                                                         |
| --------------- | ----- | --------------------------------------------------------------------------------------------------------------- |
| `shift_id`      | str   | UUID primary key (qualifier: `ftss-`)                                                                           |
| `shift_key`     | str   | Natural key: `{asset_class}.{shift_type}.{label}`                                                               |
| `name`          | str   | Human-readable name                                                                                             |
| `asset_class`   | enum  | `IR`, `FX`, `CREDIT`, `CORR`, `IR_VOL`, `EQUITY`, `COMMODITY`                                                   |
| `shift_type`    | enum  | `PARALLEL`, `STEEPENER`, `FLATTENER`, `TWIST`, `BUTTERFLY`, `SPOT`, `VOL`, `SPREAD`, `LEVEL`, `BASIS`, `CUSTOM` |
| `ta_filter`     | str   | Currency/pair filter (supports `*` wildcard)                                                                    |
| `tb_filter`     | str   | Curve/instrument filter (supports `*` wildcard)                                                                 |
| `tc_filter`     | str   | Point/tenor filter (supports `*` wildcard)                                                                      |
| `na_min`        | float | Min months (tenor range filter, inclusive)                                                                      |
| `na_max`        | float | Max months (tenor range filter, inclusive)                                                                      |
| `delta_abs`     | float | Absolute delta added to `ya`                                                                                    |
| `delta_bps`     | float | Basis points added to `ya` (auto-converts: `ya += delta_bps / 10000`)                                           |
| `delta_pct`     | float | Percentage change to `ya` (multiplicative: `ya *= (1 + delta_pct/100)`)                                         |
| `weight_at_min` | float | Weight multiplier at `na_min` (default: 1.0)                                                                    |
| `weight_at_max` | float | Weight multiplier at `na_max` (default: 1.0)                                                                    |
| `metric_map`    | list  | **Links shift to greeks in `measure.yaml`** — declares which sensitivities compute P&L impact (see below)       |

**Perturbation rule:** Exactly ONE of `delta_abs`, `delta_bps`, `delta_pct` must be set per shift block.

**Interpolation:** When `na_min`/`na_max` are set with different `weight_at_min`/`weight_at_max`, the effective shift interpolates linearly across the tenor range. This enables steepeners, flatteners, and butterfly twists from a single shift block.

### `metric_map` — The Shift-to-Greek Link

The `metric_map` is the critical bridge between market data shifts and risk measures.
It declares: "when this shift is applied, use THESE greeks from `measure.yaml` to compute P&L."

```yaml
metric_map:
  - metric: DV01              # measure.metric value to match
    measure_ta: USD            # optional: override ta match for measure lookup
    measure_tb: SOFR           # optional: override tb match (mkt tb=SOFR_SWAP → measure tb=SOFR)
    formula: "ya × delta_bps"  # P&L = measure.ya × shift magnitude
    order: 1                   # 1st order (linear). Default.
  - metric: GAMMA             # optional 2nd order correction
    formula: "0.5 × ya × delta_bps²"
    order: 2                   # 2nd order (convexity)
```

| Field        | Type | Purpose                                                                                     |
| ------------ | ---- | ------------------------------------------------------------------------------------------- |
| `metric`     | str  | Which greek to look up in `measure.yaml` (enum: `$enums.ENUM_METRIC`)                       |
| `measure_ta` | str  | Override ta axis for measure lookup (when mkt ta differs from measure ta). Optional.        |
| `measure_tb` | str  | Override tb axis for measure lookup (e.g., mkt `SOFR_SWAP` → measure `SOFR`). Optional.     |
| `formula`    | str  | P&L formula: how to combine `measure.ya` (greek) with shift delta. Human-readable + engine. |
| `order`      | int  | Taylor expansion order: 1 = linear (greek × Δ), 2 = convexity (½ × gamma × Δ²). Default 1.  |

**Why `measure_ta`/`measure_tb` overrides?**

Market data and measures use the same axis convention but sometimes with slightly different
naming at the `tb` level:
- `mkt.tb = SOFR_SWAP` (instrument type) vs `measure.tb = SOFR` (curve name)
- `mkt.tb = FX_VOL` (observation type) vs `measure.tb = 3M` (tenor)
- `mkt.tb = CDS_IG_5Y` (instrument) vs `measure.tb = IG` (sector)

The override fields resolve this mapping explicitly rather than relying on string matching.
The `measure.mkt_id` FK provides the ground truth link for audit.

### Audit Chain: Shift → Mkt → Measure

Every P&L impact result can be traced back to source data:

```
Scenario Result
  └─ impact: -3,375,000
     └─ shift: IR.PARALLEL.USD_SOFR_UP75 (delta_bps=75)
        └─ metric_map[0]: metric=DV01
           └─ measure record:
              ├─ measure_id: ftms-dv01-sofr-5y-001
              ├─ metric: DV01
              ├─ ta: USD, tb: SOFR, tc: 5Y
              ├─ ya: -45,000 (sensitivity per bp)
              └─ mkt_id: ftmk-sofr-5y  ──► mkt record:
                                            ├─ mkt_id: ftmk-sofr-5y
                                            ├─ ta: USD, tb: SOFR_SWAP, tc: 5Y
                                            ├─ ya: 4.25 (base rate)
                                            └─ snap: EOD, as_of: 2026-03-19
```

This gives full auditability: scenario result → which greek → which mkt point → what base level.

---

## 7. Scenario Schema Reference

| Field              | Type | Purpose                                                                                       |
| ------------------ | ---- | --------------------------------------------------------------------------------------------- |
| `scenario_id`      | str  | UUID primary key (qualifier: `ftsc-`)                                                         |
| `scenario_key`     | str  | Natural key: `{category}.{label}`                                                             |
| `name`             | str  | Human-readable name                                                                           |
| `category`         | enum | `MONETARY_POLICY`, `MACRO`, `GEOPOLITICAL`, `LIQUIDITY`, `REGULATORY`, `HISTORICAL`, `CUSTOM` |
| `severity`         | enum | `MILD`, `MODERATE`, `STRESS`, `SEVERE`, `PRESCRIBED`                                          |
| `description`      | str  | Narrative description                                                                         |
| `regulatory_ref`   | str  | Regulatory reference (BCBS, FRTB section)                                                     |
| `reference_period` | dict | `{start, end}` for historical scenarios                                                       |
| `tags`             | list | Categorization tags                                                                           |
| `components`       | list | Shift block references with optional overrides                                                |

**Component structure:**

```yaml
components:
  - shift_id: ftss-xxx         # FK to scenario_shifts — reusable block
    override:                   # optional: override any shift field for this scenario
      delta_bps: 150            # e.g., change magnitude
      ta_filter: "*"            # e.g., broaden scope
  - inline_shift:               # alternative: one-off shift (no reusable block)
      name: "..."
      asset_class: FX
      shift_type: BASIS
      ta_filter: EURUSD
      tb_filter: XCCY_SWAP
      tc_filter: "*"
      delta_bps: -40
```

---

## 8. Slice + Group By Semantics

**Slice** (WHERE): All dimensions AND together, values within a dimension OR together.

```
slice: { lob: [FICC], country: [US, HK] }
→ books WHERE lob = FICC AND (country = US OR country = HK)
```

**Group By** (aggregation): Controls how results are rolled up.

```
group_by: [DESK, PRODUCT_TYPE]
→ one result row per unique (desk, product_type) combination
```

**Available dimensions:**

| Dimension      | Source           | Description                    |
| -------------- | ---------------- | ------------------------------ |
| `BOOK`         | book.book_id     | Individual book                |
| `DESK`         | book.desk        | Trading desk                   |
| `SUB_DESK`     | book.sub_desk    | Desk subdivision               |
| `LOB`          | book.lob         | Line of business               |
| `COUNTRY`      | book.country     | Booking entity country         |
| `REGION`       | book.region      | Geographic region              |
| `TRADER`       | book.trader_id   | Book owner                     |
| `PRODUCT_TYPE` | txn.product_type | Instrument type                |
| `TENOR`        | measure.tc       | Tenor bucket from measure axis |
| `CURVE`        | measure.tb       | Curve from measure axis        |
| `CCY`          | measure.ta       | Currency from measure axis     |
