# The God Prompt — FICC Trading Ontology + Event-Driven Architecture

> A single prompt to generate the complete data ontology, event-driven matching engine, server-side components, and data store for a sell-side FICC trading platform.

---

## THE PROMPT

Design and implement a **complete YAML-based data ontology and event-driven server architecture** for a sell-side Fixed Income, Currencies & Commodities (FICC) trading platform. The system must cover the **full trade lifecycle** — from pre-trade price discovery (axes, RFQs, streaming quotes) through execution, booking, matching, clearing, settlement, risk computation, and regulatory reporting — across rates, FX, credit, repos, bonds, equities, MBS, and listed futures/options.

---

### PART 1: DESIGN PHILOSOPHY

The entire architecture is built on ONE core principle: **Events, Not Tables.**

Every business action — a sales booking, a broker fill, an amendment, a risk measure, a settlement instruction — is a variant of a single polymorphic `Event` record. There are NO separate trade, match, allocation, or amendment tables. A "trade" is what emerges when correlated events converge.

**Key architectural constraints:**

1. **Single polymorphic event collection** — all event types in one collection, discriminated by `event_type`. Eliminates N-table joins for trade lifecycle queries, enables unified audit trail and real-time streaming.
2. **Three-layer payload model** — every event carries: `raw{}` (source-native message, immutable after capture), `payload{}` (canonical normalized transform — the ONLY layer the matching engine reads), `enriched{}` (post-match additions: risk flags, regulatory IDs, settlement instructions, compliance checks, pricing markup). Flow: `source → raw{} → transformer → payload{} → matching engine → enriched{}`.
3. **Five matching primitives** — the engine is data-agnostic. It knows nothing about trading — it pairs abstract events using: **Correlation** (1:1 key match + tolerance), **Reconciliation** (1:1 field-by-field diff with priority rules), **Allocation** (1:N split where SUM(children)==parent), **Aggregation** (N:1 or N:M combine/compress/net), **Override** (1:0 force-resolve with audit trail + approval).
4. **9-axis pattern for time-series stores** — market data (`mkt`), risk measures (`measure`), and trade schedules (`diary`) all share the same physical axis layout: `[KEY] ta, tb, tc` (text identity), `[DIM] na, nb` (numeric dimensions for sorting), `[VALUE] ya, yb, yc` (observed/computed values), `[META] td, da, db` (denomination, dates). A separate axis definitions config declares what each axis MEANS per record type/subtype — no hardcoded axis semantics anywhere.
5. **Append-only event sourcing** — events are immutable once captured. State changes are recorded as `transitions[]` (append-only log). Streaming is append-mode at 2s intervals, not upsert. `limit: 100` caps the streaming window.
6. **Event-centric, not trade-centric** — the primary collection is `events`. Normalized store schemas (`txn`, `leg`, `party`, `book`, `instrument`, `mkt`, `measure`, `diary`) are materialized projections created by the matching engine when events converge. The `journal` is a denormalized flat projection for blotter queries.

---

### PART 2: CORE SCHEMAS (12 schemas)

Each schema is a YAML blueprint with: `blueprint: schema`, `kind:`, `qualifier:` (ID prefix), `xid:` (external ID pattern), `xns: [id, xid]`, `description:`, `icon:`, `sections:[]`, `views:[]`, `model: { fields: {} }`.

Each field declaration: `{ type, key, rank, facet, fuzzy, grid, group, card, col, enum, ref, widget, default, placeholder, description, collapsed, items }`.

#### 2.1 `event.yaml` — Universal Event Record

The ONE schema. All 23+ event types in one collection.

**Identity:** `event_id` (key, qualifier `ftv-`), `event_type` (facet, `ENUM_EVENT_TYPE` — 40+ values covering pre-trade through post-trade), `status` (`ENUM_EVENT_STATUS` — ACTIVE, PENDING, MATCHED, CONFIRMED, CLEARED, SETTLED, CANCELLED, REJECTED, EXPIRED, FAILED, TRADED_AWAY, STREAMING), `version` (int, default 1).

**Source:** `source` (facet, `ENUM_SOURCE_TYPE` — BLOOMBERG, TRADEWEB, MARKITWIRE, DTCC, LCH, CME, ICE, BROKER, STP_PIPELINE, CLIENT, MANUAL, BLOOMBERG_CHAT, SYMPHONY, MATCHING_ENG, NETTING_ENG, CFETS, SHCH, CMU), `source_ref`, `protocol` (facet, `ENUM_PROTOCOL` — FIX, FPML, SWIFT_MT, SWIFT_MX, REST, JSON, CSV, INTERNAL), `actor`, `desk`, `thread_id` (chat thread for BBG IB/Symphony originated trades).

**Layer 1 — raw{}:** `format` (`ENUM_RAW_FORMAT`), `version` (protocol version e.g. "FIX 4.4", "FpML 5.12", "MT300"), `content` (dict — parsed source-native), `raw_text` (original wire bytes), `received_at`, `checksum` (SHA-256 for tamper detection), `source_msg_id`.

**Layer 2 — payload{}:** Structure determined by `event_type`. Each type has its own payload schema in `_event_payloads/*.yaml`. The canonical transform is produced by a transformer keyed on `(source, protocol, event_type, product_type)`. The matching engine reads ONLY this layer.

**Layer 3 — enriched{}:** Post-match additions, never present at capture time. Contains: `risk_flags[]` (LARGE_NOTIONAL, CONCENTRATION_RISK, NEW_COUNTERPARTY, LIMIT_BREACH, WASH_TRADE, UNUSUAL_TENOR, OFF_MARKET_PRICE, SANCTIONS_HIT), `regulatory{}` (uti, usi, lei, jurisdiction[], reporting_status, reported_at), `settlement{}` (ssi_id, nostro, value_date, settlement_status), `pricing{}` (mid_price, spread, markup_bps, benchmark), `compliance{}` (approved_by, limit_check, wash_trade_flag, best_execution), `enriched_at`, `enriched_by`.

**Economics (denormalized for blotter):** `product_type`, `notional`, `ccy`, `cpty_id` (ref: entities), `direction`, `ccy_pair`, `rate`, `tenor`, `index`, `spread_bps`, `reference_entity`, `issuer`, `security_desc`, `option_type`. Populated by a `_denormalize_economics` factory function that extracts from payload.

**Linking:** `links[]` — each entry: `{ event_id, rel (ENUM_LINK_TYPE — 17 types: CORRELATES_WITH, RESPONDS_TO, ORIGINATES_FROM, COMPETES_WITH, TRIGGERED_BY, PARENT_OF, CHILD_OF, CREATED_FROM, AMENDS, SUPERSEDES, CANCELS, SETTLES, NETS_WITH, MEASURES, SCHEDULES, PRICED_FROM), role }`.

**Correlation / Matching:** `correlation{}` — `chain_id` (shared UUID linking all events in a scenario chain), `match_type` (ENUM_MATCH_TYPE — NEGOTIATION, CORRELATION, RECONCILIATION, ALLOCATION, AGGREGATION, OVERRIDE), `scenario` (ENUM_MATCH_SCENARIO — 50+ real-world scenarios, see Part 6), `match_status` (ENUM_MATCH_STATUS — OPEN, QUOTED, ACCEPTED, UNMATCHED, PARTIAL, MATCHED, FORCED, STREAMING), `cardinality` (ONE_TO_ONE, ONE_TO_MANY, MANY_TO_ONE, MANY_TO_MANY), `direction` (LHS, RHS, PARENT, CHILD), `actor_role` (CLIENT, SALES, TRADING, BROKER, CCP, OPS, SYSTEM), `breaks[]` (field-level: field, lhs, rhs, tolerance), `resolution{}` (action, service, params, executed_at), `matched_at`, `matched_by`.

**Lifecycle Trail:** `transitions[]` — append-only: `{ from_status, to_status, at, by, reason, diff{} }`.

**Timestamps:** `created_at`, `updated_at`, `sla_deadline`, `priority` (LOW, NORMAL, HIGH, URGENT, CRITICAL).

**RLS (Row-Level Security):** Sales/trading users see own events only (field: `actor`, match: `$ctx.identity`). Operations/admin bypass RLS.

**Chain Workflow (RFQ negotiation state machine):**
```
field: chain_state
IDLE:        → OPEN         on RFQ                                    (UNMATCHED)
OPEN:        → QUOTED       on QUOTE  guard payload.status=INDICATIVE (PARTIAL)
QUOTED:      → NEGOTIATING  on RFQ    guard negotiation_status=REVISED (PARTIAL)
             → TRADED_AWAY  on RFQ    guard negotiation_status=TRADED_AWAY (UNMATCHED)
NEGOTIATING: → QUOTED_FIRM  on QUOTE  guard payload.status=FIRM       (PARTIAL)
QUOTED_FIRM: → ACCEPTED     on RFQ    guard negotiation_status=ACCEPTED (MATCHED)
             → TRADED_AWAY  on RFQ    guard negotiation_status=TRADED_AWAY (UNMATCHED)
ACCEPTED:    → TRADED       on TRADE                                  (MATCHED)
scenarios: HIT → [IDLE..TRADED], MISS → [IDLE..TRADED_AWAY]
```

#### 2.2 `txn.yaml` — Product-Agnostic Transaction

The normalized trade header. Knows WHO traded WHAT and WHEN, but NOT the economics — those live in legs. Orders and trades are the same construct, distinguished by `txn_type`.

**Identity:** `txn_id` (key, qualifier `fttx-`), `txn_type` (ENUM_TXN_TYPE — ORDER, TRADE, ALLOCATION, NOVATION, COMPRESSION), `product_type`, `trade_date`, `value_date`, `status` (ENUM_TXN_STATUS — PENDING, CONFIRMED, MATCHED, SETTLED, MATURED, CANCELLED), `source`, `venue` (ENUM_VENUE — TRADEWEB, MARKETAXESS, BLOOMBERG_RFQ, BONDPOINT, TRUMID, DIRECTPOOL, ICE_BONDS, BILATERAL, VOICE, CHAT, INTERNAL, BOND_CONNECT, SWAP_CONNECT).

**Parties:** `book_id` (ref: books), `party_id` (ref: entities — our entity), `cpty_id` (ref: entities — counterparty).

**Identifiers (golden):** `ids{}` — `uti` (ISO 23897), `usi` (CFTC), `upi` (ISO 4914), `xid` (external platform ref).

**Cross-references:** `xrefs[]` — `{ id_type (UTI, USI, TRADE_ID, ORDER_ID, CLEARING_REF), value, source (OMS, MUREX, LCH, CME, DTCC...) }`.

**Event lineage:** `event_refs[]` — `{ event_id, event_type, link_type, chain_id }`. Links back to the raw event chain: RFQ → QUOTE → BOOKING → TRADE.

#### 2.3 `leg.yaml` — Instrument-Specific Leg Detail

Each txn has 1..N legs carrying the economics. Fields are merged/minimized: each product uses a subset of the same ~25 field pool.

**Product mapping:**
- FX: 1 leg (spot) or 2 (swap: near+far), `ccy_pair`, `fwd_points`
- NDF: 1 leg, `ccy_pair`, `fixing_date`, `is_ndf=true`
- IRS: 2 legs (fixed+float), `rate`, `benchmark`, `spread_bps`, `day_count`
- XCCY: 2 legs (each in diff ccy), `rate`, `benchmark`
- FX Option: 1 leg + `underlying_id`, `strike`, `exercise_style`, `fixing_date`
- TRS: 2 legs (return+funding), `underlying_id`, `benchmark`
- CDS: 2 legs (protection+premium), `underlying_id`, `spread_bps`
- Bond: 1 leg, `rate` (coupon), `day_count`, `security_id`
- Bond Future: 1 leg, `contract`, `price`, `security_id`

**Fields:** `leg_id` (key, qualifier `ftlg-`), `txn_id` (ref), `leg_type` (ENUM_LEG_TYPE — 20+ types grouped by product for depends_on cascade), `direction` (PAY/RECEIVE), `status` (ACTIVE, INACTIVE, CANCELLED, EXERCISED), `security_id` (ref: instruments), `underlying_id` (ref: instruments). Economics: `notional`, `quantity`, `ccy`, `rate`, `benchmark`, `spread_bps`, `price`, `yield_val`. FX: `ccy_pair`, `fwd_points`. Dates: `effective_date`, `maturity_date`, `fixing_date`, `day_count` (ACT360, ACT365, 30360, ACT_ACT), `frequency`. Option: `strike`, `exercise_style` (EUROPEAN, AMERICAN, BERMUDAN), `call_schedule[]`. Delivery: `is_ndf`, `is_cleared`, `ccp`, `contract`.

#### 2.4 `mkt.yaml` — Market Data Observations (9-axis pattern)

Curves, prices, fixings, vol surfaces, correlations, SABR parameters. A curve is built from heterogeneous instruments in one dataset.

**Two IDs:** `mkt_id` (UUID, FK target for measure.mkt_id), `mkt_key` = `{ta}.{tb}.{tc}` (natural composite key, human-readable). **Unique constraint:** `(mkt_key, snap, as_of_date)`.

**mkt_key examples:**
```
USD.SOFR_DEPO.ON          — SOFR overnight deposit
USD.SOFR_SWAP.5Y          — 5Y SOFR swap rate
USD.SOFR_FRA.1Mx3M        — 1M×3M SOFR forward
USD.SOFR_IMM.M6           — Jun26 SOFR IMM future
EURUSD.FX_SPOT.SPOT       — EUR/USD spot
EURUSD.FX_FWD.3M          — EUR/USD 3M forward
EURUSD.FX_SWAP.1Mx3M      — EUR/USD 1M×3M FX swap
EURUSD.XCCY_SWAP.5Y       — EUR/USD 5Y xccy basis
USD.SOFR_3M6M_BASIS.5Y    — SOFR 3M/6M tenor basis 5Y
USD.BOND_PRICE.UST4536_MID — UST 4.5% 02/36 mid price
EURUSD.FX_VOL.3M_25D_P    — 3M 25-delta put vol
USD.IR_SWPNVOL.5Yx10Y_ATM — 5Y×10Y ATM swaption normal vol
USD.IR_SABR.5Yx10Y_ALPHA  — SABR alpha for 5Y×10Y
EURUSD_USDJPY.CORR.1Y     — 1Y rolling correlation
```

**Fields:** `mkt_id` (key, qualifier `ftmk-`), `mkt_key`, `observation_type` (ENUM_OBSERVATION_TYPE — PRICE, RATE_FIX, CURVE_POINT, FRA, IMM_FUT, SPREAD, VOL_SURFACE, INDEX), `snap` (ENUM_SNAP — SOD, LIVE, FLASH, FLASH3PM, EOD), `as_of_date`, `source`. Axes: `ta` (ccy/pair), `tb` (curve+instrument), `tc` (point label), `na` (months sort), `nb` (secondary sort), `ya` (primary value), `yb` (secondary), `yc` (tertiary), `td` (denomination — ABS, BPS, PCT), `da` (end/maturity date), `db` (start date — null for spot instruments).

#### 2.5 `measure.yaml` — Risk Metrics, P&L, Schedules (9-axis pattern)

Same axis convention as mkt. Metric type determines axis semantics. **Unique constraint:** `(measure_key, snap, as_of_date, txn_id, leg_id)`.

**FK References:** `txn_id` (null for book-level), `leg_id` (null for txn-level), `mkt_id` (market data point used — audit trail linking greek to its market input).

**Metrics (ENUM_METRIC):** Greeks: DV01, TBO1 (tenor basis 01), FXDELTA, FXVEGA, MTM, NAV, PNL, THETA, GAMMA, RHO, CORR. Schedule-derived (sparse — next/prev/milestone/monitor): NEXT_COUPON, NEXT_RESET, NEXT_EXERCISE, NEXT_CALL, NEXT_PRINCIPAL, NEXT_FIXING, NEXT_ROLL, NEXT_PAYMENT, PREV_COUPON, PREV_RESET, PREV_FIXING, MATURITY, EFFECTIVE, FIRST_CALL, BARRIER_KI, BARRIER_KO, TRIGGER, ACCRUED.

**P&L Computation Model:** `P&L_impact = Σ (sensitivity_i × shift_i)` where sensitivity comes from measure (the greek) and shift comes from a scenario's shift block (perturbation to mkt data). The join key is shared `(ta, tb, tc)` axis coordinates. `measure.mkt_id` FK provides the audit trail.

#### 2.6 `diary.yaml` — Trade Cashflow Diary (9-axis pattern)

Full cashflow schedule: coupons, resets, fixings, barriers, exercises. Unlike mkt/measure: no snap/as_of_date. Diary rows have a lifecycle (status updates in place as events occur). **Unique constraint:** `(schedule_key, txn_id, leg_id)`.

**Lifecycle per schedule_type:**
```
COUPON:    SCHEDULED → PAID
RESET:     PENDING → FIXED → PAID           (mkt_id wired on FIXED)
PRINCIPAL: SCHEDULED → PAID
EXERCISE:  OPEN → EXERCISED / EXPIRED
BARRIER:   MONITORING → BREACHED / EXPIRED  (mkt_id wired on BREACHED)
FIXING:    PENDING → FIXED → SETTLED        (mkt_id wired on FIXED)
```

#### 2.7 `party.yaml` — Universal Party

Replaces the entity/counterparty split with a single party concept. Every participant in a trade is a party with a type.

**Fields:** `party_id` (key, qualifier `ftp-`), `name`, `short_name`, `party_type` (ENUM_PARTY_TYPE — LEGAL_ENTITY, TRADING_DESK, BRANCH, CCP, BROKER, CLIENT, PRIME_BROKER, CUSTODIAN), `status`, `lei`, `bic`, `duns`, `desk`, `region` (US/EU/APAC). Settlement: `funding_ccy`, `default_ssi_id`. Legal: `is_netting_eligible`, `is_csa_agreement`, `jurisdiction`. Hierarchy: `parent_party_id`, `subsidiaries[]`.

#### 2.8 `entity.yaml` — Legal Entity (Extended)

Extended entity with contacts, addresses, and settlement capabilities. Includes shared partials from `_party.yaml`, `_contact.yaml`, `_identifiers.yaml`, `_address.yaml`.

**Contacts:** list of `{ contact_type (OPS, LEGAL, TRADING, SETTLEMENT, COMPLIANCE, PRIMARY), name, email, phone (E.164), primary (bool) }`.

**Addresses:** list of `{ address_type (REGISTERED, BRANCH, MAILING, BILLING), line1, line2, city, state, postal_code, country (ISO 3166-1) }`.

**Identifiers:** `{ lei (ISO 17442), bic (ISO 9362), duns }`.

**Settlement:** `funding_ccy`, `settlement_ccys[]`, `default_ssi_id`. **Hierarchy:** `parent_entity_id`, `subsidiaries[]`. **Extended:** `xmeta{}` (ratings, netting, CSA details).

#### 2.9 `book.yaml` — Trading Book/Portfolio

Golden `book_id` + operational metadata + cross-system references. A book can exist in multiple systems (OMS, RISK, MUREX, CALYPSO) with different codes.

**Fields:** `book_id` (key, qualifier `ftb-`), `entity_id` (ref), `name`, `short_name`, `status` (ACTIVE, INACTIVE, CLOSED), `ccy`. Classification: `desk`, `region`, `strategy`, `book_type` (TRADING, BANKING, HEDGE, WAREHOUSE), `regulatory_class` (FRTB classification). Limits: `risk_limit` (max exposure, section restricted to operations/risk/admin roles). Cross-system: `systems[]`, `xrefs[]` — `{ system (OMS, RISK, MUREX, CALYPSO), book_code, status (ACTIVE, MAPPED, STALE) }`.

#### 2.10 `instrument.yaml` — Instrument Master

Static instrument reference data with two-tier identifier system. Product-specific terms via overlays.

**Tier 1 — Golden canonical IDs:** `ids{}` — `isin` (ISO 6166), `cusip`, `sedol`, `figi` (OpenFIGI 12-char), `ticker`, `cfi_code` (ISO 10962), `mic` (ISO 10383), `ric`.

**Tier 2 — Cross-references:** `xrefs[]` — `{ id_type (ISIN, CUSIP, SEDOL, FIGI, TICKER, RIC, WKN, LEI, UTI, USI, UPI, RED, CLIP, INTERNAL, CUSTOM), value, source (BLOOMBERG, REFINITIV, ICE, MARKIT, CME, EUREX, OPENFIGI, EXCHANGE, INTERNAL, MANUAL), source_system, venue_mic, is_golden, priority (int — higher = more trusted), status (ACTIVE, STALE, SUPERSEDED, DISPUTED), effective_from, effective_to }`.

**Terms:** `ccy`, `issue_date`, `maturity_date`, `issuer_id` (ref: entities), `country`, `sector`.

#### 2.11 `journal.yaml` — Denormalized Event (Flat Projection)

Flat, query-friendly projection of events for blotter views. Uses a 9-axis pattern with different naming: `x/y/z` (numeric), `tx/ty/tz` (text), `dx/dy/dz` (date). Links back to `txn_id`, `leg_id`. Includes: `actor`, `actor_role`, `desk`, `source`, `chain_id`, `link_type`, `parent_event_id`.

#### 2.12 `fpml.yaml` — ISDA FpML Product Templates

Product template catalog mapping product_type to FpML structure. Fields: `fpml_id` (key, qualifier `ftf-`), `product_type`, `description`, `leg_types[]`, `required_fields{}` (per leg type), `validation_rules[]`, `template{}` (default values for trade capture).

---

### PART 3: REUSABLE PARTIALS (10 schemas)

All blueprint `partial`. Composed into event payloads and core schemas via `$ref`.

#### 3.1 `_partials/identifiers.yaml`
Two-tier identifier system. Golden canonical IDs: ISIN, CUSIP, SEDOL, FIGI, LEI, ticker, name. Cross-references list with: source/venue tracking, priority, status (ACTIVE, STALE, SUPERSEDED), effective lifecycle dates.

#### 3.2 `_partials/parties.yaml`
Trade parties with typed roles: PRINCIPAL, COUNTERPARTY, BROKER, CLEARING_HOUSE, CUSTODIAN, AGENT, OBO_AGENT, EXECUTION_BROKER, PRIME_BROKER. Each with: entity_id, LEI, BIC, trader info, desk assignment, sales coverage.

#### 3.3 `_partials/economics.yaml`
Trade economics: direction (PAY/RECEIVE/BUY/SELL), notional, currency, price/yield/spread. Fees: commission, brokerage, exchange, clearing, settlement, regulatory. Uniform `legs[]` structure for multi-leg products: each leg with leg_type, direction, notional, ccy, rate, fixed_rate, index, spread_bps, day_count, frequency, compounding_method, RFR-specific (lookback_days, lockout_days, observation_shift), FX-specific (ccy_pair, spot_rate, fwd_points), option-specific (strike, premium, exercise_style).

#### 3.4 `_partials/execution.yaml`
Execution metadata: venue (FXGO, TRADEWEB, MARKETAXESS, BLOOMBERG, EBS, REUTERS_MATCHING, VOICE, INTERNAL), execution_method (VOICE, ELECTRONIC, RFQ, ALGO, STREAMING, AUCTION, DIRECT), broker capacity (AGENCY, PRINCIPAL, RISKLESS_PRINCIPAL), fills list, execution_broker. TCA metrics: arrival_price, implementation_shortfall, market_impact_bps, spread_cost_bps, dark_pool_pct.

#### 3.5 `_partials/settlement.yaml`
Settlement instructions: value_date, settlement_date, status (PENDING, INSTRUCTED, MATCHED, SETTLED, FAILED), settlement_location (DTC, EUROCLEAR, CLEARSTREAM, FEDWIRE, CLS, TARGET2, CHIPS, CHATS, BOJ_NET, CMU, RTGS), SSI details (nostro_agent, nostro_account, cpty_agent, cpty_account), SWIFT message types (MT300, MT304, MT306, MT320, MT340, MT360, MT380, MT502, MT515, MT518), confirmation_method/status, failure tracking (fail_reason, fail_date, fail_count).

#### 3.6 `_partials/regulatory.yaml`
Multi-regime regulatory reporting:
- **EMIR:** action_type, event_type, clearing_obligation, valuation (mtm, method), margin (IM, VM)
- **MiFID II:** transaction_reporting, trading_venue, venue_type, capacity, short_selling_flag, commodity_derivative_flag, waiver_flag, algorithm_id
- **Dodd-Frank:** USI, SEF_indicator, clearing_exemption, block_trade_indicator
- **TRACE:** execution_time, contra_party_type, special_price_flag, reported_price
- **SFTR:** repo/securities lending type, haircut, reuse_flag, collateral_composition

#### 3.7 `_partials/collateral.yaml`
Collateral & margin: CSA/ISDA master agreement, thresholds (MTA, rounding), eligible collateral types/currencies, initial_margin, variation_margin, margin_model (SIMM, SPAN, GRID, SCHEDULE), rehypothecation_flag, concentration_limits. XVA metrics: CVA, DVA, FVA, MVA, KVA, PFE, SA-CCR (EAD, alpha, replacement_cost, PFE_addon).

#### 3.8 `_partials/lifecycle.yaml`
Trade lifecycle: current_state (NEW, PENDING, CONFIRMED, AFFIRMED, CLEARED, SETTLED, MATURED, DEFAULTED, TERMINATED, NOVATED, COMPRESSED, CANCELLED), state_transitions[] (append-only audit: from_state, to_state, timestamp, actor, reason). Amendments: amendment_type, amendment_version, changed_fields[]. Novations: old_cpty, new_cpty, novation_date, remaining_notional. Early terminations: termination_date, termination_value, payment_amount. Compressions: cycle_id, compression_service, compressed_trade_ids[], replacement_trade_id.

#### 3.9 `_partials/schedules.yaml`
Normalized date-based schedules. Schedule entry types: COUPON, PRINCIPAL, AMORTIZATION, CALL, PUT, RESET, NDF_FIXING, BARRIER_CHECK, EXERCISE, MATURITY, DIVIDEND, FUNDING. Each entry: date, status (SCHEDULED, PENDING, FIXED, PAID, EXERCISED, BREACHED, EXPIRED, CANCELLED), amounts, rates, fixing details (source, rate, date), exercise info (style, strike, window_start, window_end), barrier observation data (level, spot_at_observation, breached).

#### 3.10 `_partials/measures.yaml`
Financial metrics with dimensional coordinates: metric identity (type, name), value (with up_shift, down_shift), denomination/kind (ABSOLUTE, RATIO, PCT, PER_BP, PER_VOL_POINT, NORMALIZED), currency, market context snapshot (rate, price, yield, spread, spot, vol, curve_reference), multi-dimensional coordinates (tenor, curve, term_1/term_2, entity, strike, scenario, portfolio, book).

---

### PART 4: PRODUCT OVERLAYS (9 asset-class overlays)

All blueprint `partial`. Applied by product_type discriminator onto instrument/leg schemas.

#### 4.1 `_overlays/fx.yaml`
Currency pair, base/quote currencies, spot_date/rate, forward_points, tenor, NDF indicator, fixing_date/source/rate, NDF settlement_ccy/amount, CLS eligibility.

#### 4.2 `_overlays/irs.yaml`
Swap type (VANILLA, BASIS, OIS, CROSS_CURRENCY, AMORTIZING), clearing status/CCP, client clearing type (HOUSE, CLIENT, AFFILIATE), cross-currency parameters (fx_rate, principal_exchange — NONE, INITIAL, FINAL, BOTH), swaption (exercise_style, expiry_date, straddle), compression eligibility.

#### 4.3 `_overlays/cds.yaml`
Reference entity/ID/obligation, seniority (SENIOR_UNSECURED, SUBORDINATED, SENIOR_SECURED), restructuring clause (CR, MR, MMR, XR — Old Restructuring, Modified, Modified-Modified, No Restructuring), premium_bps, upfront_fee, recovery_rate, credit_events[] list, settlement type (PHYSICAL, CASH, AUCTION). Index CDS: index_name, series, version, on_the_run (bool), factor, tranche (attachment_point, detachment_point).

#### 4.4 `_overlays/option.yaml`
Call/put, strike, expiry_date, exercise_style (EUROPEAN, AMERICAN, BERMUDAN), contract_size, settlement type (CASH, PHYSICAL, DELIVERABLE), underlying_ref, premium/premium_ccy/premium_date. Barriers: barrier_type (UP_IN, UP_OUT, DOWN_IN, DOWN_OUT), barrier_level, observation_frequency (CONTINUOUS, DAILY, WEEKLY). Digital: payout_amount, payout_ccy. Strategy: strategy_type (STRADDLE, STRANGLE, RISK_REVERSAL, COLLAR, BUTTERFLY, CONDOR, SEAGULL, CALENDAR_SPREAD). FX-specific: cut_time (NY_CUT, TOKYO_CUT, ECB_FIX), delivery_date.

#### 4.5 `_overlays/fixed_income.yaml`
Coupon (rate, frequency, type — FIXED, FLOATING, ZERO, STEP_UP, PIK), day_count, face_value, amount_outstanding, seniority, ratings (S&P, Moody's, Fitch, composite), callable/putable/convertible flags, call_schedule[], float_index/spread, amortization_schedule.

#### 4.6 `_overlays/equity.yaml`
Shares outstanding, float shares, float_pct, market_cap, beta, short_interest, GICS sector/industry/sub_industry.

#### 4.7 `_overlays/mbs.yaml`
Pool number, pool_factor, agency (GNMA, FNMA, FHLMC), collateral_type, original_face, current_face, WAC, WAM, WALA, prepayment metrics (CPR_1M, CPR_life, PSA_1M, SMM, CDR), credit metrics (avg_fico, avg_ltv, delinquency_pct), tranche_type, subordination_pct.

#### 4.8 `_overlays/repo.yaml`
Rate, repo_type (CLASSIC, SELL_BUY_BACK, TRI_PARTY), term_type (OPEN, TERM, OVERNIGHT), direction (REPO, REVERSE_REPO), purchase_price, repurchase_price, collateral details (ISIN, type, face_value, market_value, GC vs specific), haircut/margin_ratio, tri_party_agent, floating rate (index, spread), master_agreement_type (GMRA, MRA, GMSLA).

#### 4.9 `_overlays/futures.yaml`
Contract size, value per point, tick size/value, contract month, first_trading_date, last_trading_date, first_notice_date, first_delivery_date, delivery_type (CASH, PHYSICAL), delivery_grade, delivery_location, initial_margin, maint_margin, roll_date, generic_ticker. Bond futures CTD: ctd_ticker, conversion_factor, implied_repo_rate.

---

### PART 5: EVENT PAYLOADS (23 payload schemas)

All blueprint `partial` in `_event_payloads/`. Each defines the canonical `payload{}` structure for one event_type.

#### Pre-Trade
1. **`axe.yaml`** — Indication of Interest. Direction, product_type, ticker, notional, indicative_price, spread, min/max_size, axe_type (NATURAL, INVENTORY, FACILITATION), axe_status (LIVE, UPDATED, WITHDRAWN, FILLED, EXPIRED), visibility (PUBLIC, TIERED, PRIVATE), valid_from/until, rfq_count. Lifecycle: LIVE → UPDATED → FILLED | WITHDRAWN | EXPIRED.
2. **`rfq.yaml`** — Request for Quote. Direction, product_type, notional, ccy, tenor, limit_price, valid_until, client_entity_id, num_dealers, dealer_entity_ids[]. RFQ modes: SINGLE or COMPETITIVE (ALLQ). Revision tracking: revision (int), negotiation_status (OPEN, REVISED, ACCEPTED, TRADED_AWAY, COVER), revision_reason. Venue routing: venue, target_entity_ids[]. Sender context: rfq_direction (OUTBOUND/INBOUND), initiator_desk, venue_rfq_id. Spread products: benchmark, spread_bps, fixing_date, fixing_status, all_in_price.
3. **`quote.yaml`** — Quote Response. rfq_event_id, price, spread, valid_until, quoted_by, status (PENDING, INDICATIVE, FIRM, ACCEPTED, REJECTED, EXPIRED, TRADED_AWAY). Competitive: dealer_entity_id, dealer_rank, is_winner. Two-way pricing: bid_price, ask_price, bid/ask_spread, bid/ask_size. Spread product: benchmark, benchmark_rate, fixing_status, all_in_rate. Quote mode: ONE_WAY, TWO_WAY, STREAM. Streaming: stream_id, venue, venue_quote_id.
4. **`order.yaml`** — Order with Fills. order_type (LIMIT, MARKET, IOI), direction, product_type, notional, fills[] (qty, price, venue, timestamp), vwap, filled_qty, remaining_qty.
5. **`auction_bid.yaml`** — Bond Auction Bid. Primary dealer bids. auction_id, issuer, security_desc, bid_type (COMPETITIVE, NON_COMPETITIVE), bid_yield, bid_price, bid_amount. Auction metadata: auction_type (NEW_ISSUE, REOPENING, TAP), auction_status (ANNOUNCED → OPEN → CLOSED → AWARDED → SETTLED). Results: awarded_amount, stop_yield, allotment_pct.

#### Booking
6. **`sales_booking.yaml`** — Sales-side booking (LHS of correlation). trade_economics (product_type, trade_date, direction, notional, ccy, rate, spread), book_id, portfolio, strategy, parties[] (role, entity_id, trader, sales), legs[] (leg_type, direction, notional, ccy, rate, start/end_date, day_count, index, spread_bps).
7. **`trading_booking.yaml`** — Trading-side booking (RHS of correlation). Same structure as sales_booking — the matching engine compares economics field-by-field.
8. **`obo_ticket.yaml`** — On-Behalf-Of client ticket. client_entity_id, on_behalf_of, ticket_ref, trade_economics.
9. **`stp_message.yaml`** — STP auto-booked from FIX/FpML/SWIFT. parsed_economics, sender, receiver, stp_status (PARSED, VALIDATED, BOOKED, FAILED), error.

#### External
10. **`broker_fill.yaml`** — Execution report (FIX 35=8). broker_entity_id, exec_id, price, qty, venue, commission, commission_bps, exec_type (NEW, PARTIAL, FILL, CANCEL, REPLACE).
11. **`clearing_msg.yaml`** — CCP clearing/novation. ccp, clearing_id, original_cpty, novated_cpty, economics, margin_required, clearing_fee.
12. **`clearing_submission.yaml`** — Direct CCP clearing submission. ccp, submission_ref, trade_event_id, middleware, product details, clearing_account, clearing_category (HOUSE, CLIENT, AFFILIATE), netting_set, submission_status (PENDING → SUBMITTED → PENDING_CPTY → ACCEPTED | REJECTED | EXPIRED), cpty_status.
13. **`affirm_msg.yaml`** — Affirmation (MarkitWire/DTCC). platform, affirm_id, counterparty, affirmed_economics.
14. **`giveup_notice.yaml`** — Give-up/take-up. executing_broker, prime_broker, giveup_ref, trade_economics.

#### Lifecycle
15. **`amendment.yaml`** — Versioned changes with approval. target_event_id, amendment_type (ECONOMIC, NED, CANCEL, REBOOK), changes[] (field, old_value, new_value), approvals[] (role, approver, status), amendment_status (PENDING, APPROVED, REJECTED, APPLIED).
16. **`alloc_split.yaml`** — Block allocation split. block_event_id, account, entity_id, quantity, book_id, split_num, price, fees.
17. **`settlement_instr.yaml`** — Payment instruction. payment_direction, amount, ccy, value_date, ssi_id, nostro, cpty_ssi, cpty_entity_id, settlement_method (RTGS, NETTING, CLS, PVP).
18. **`margin_call.yaml`** — VM/IA margin call. vm_amount, ia_amount, ccy, calculation_date, margin_type, collateral_type, deadline.
19. **`net_settlement.yaml`** — Netted settlement. trade_event_ids[], net_amount, ccy, value_date, cpty_entity_id, gross_pay, gross_receive, trade_count.

#### Materialized
20. **`trade.yaml`** — Golden trade record (created by matching engine when booking events converge). trade_id, fpml_type, trade_date, parties[] (roles, entity_id, trader, sales), ned{} (non-economic: book_id, portfolio, strategy, clearing), legs[] (comprehensive leg-level economics), uti, usi.
21. **`risk_measure.yaml`** — Daily risk calculation. trade_event_id, leg_event_id, metric (ENUM_METRIC), value, denomination, tenor_bucket, curve, as_of_date, scenario.
22. **`schedule_event.yaml`** — Cashflow schedule event. trade_event_id, leg_id, event_subtype (PAYMENT, RESET, FIXING, COUPON, MATURITY), date, amount, ccy, index, fixing_rate, fixing_source, schedule_status.
23. **`position_snapshot.yaml`** — EOD position snapshot. book_id, as_of_date, source (OUR_BOOK, CPTY_STATEMENT), positions[] (product_type, ccy, net_notional, mtm, trade_count), total_mtm.

---

### PART 6: MATCHING ENGINE — 30 BUSINESS SCENARIOS

The five foundation primitives compose to handle 30 real-world scenarios. Each scenario specifies: foundation primitive, product type, event count, event flow, and resolution action.

#### Price Discovery (2)
1. **RFQ Hit** — Correlation. FX_SPOT. ~6 events. RFQ → QUOTE (indicative) → counter-RFQ (revised) → QUOTE (firm) → accept → TRADE. Chain state machine: IDLE → OPEN → QUOTED → NEGOTIATING → QUOTED_FIRM → ACCEPTED → TRADED.
2. **RFQ Miss** — Correlation. FX_FORWARD. ~5 events. Same chain but client trades away: → TRADED_AWAY.

#### Execution (4)
3. **Back-to-Back** — Correlation. IRS. 4-5 events. Client trade → internal transfer → street hedges. Creates mirror trade in hedge book (opposite direction).
4. **STP Auto-Book** — Correlation + Transform. BOND. 2 events. Inbound FIX/FpML/SWIFT → parse+validate → auto-create trade. Resolution: AUTO_BOOK.
5. **Broker Exec** — Allocation. FX_OPTION. 3-5 events. ORDER → individual BROKER_FILL events → VWAP calculation → CREATE_TRADE.
6. **OBO Client** — Correlation. CDS. 3 events. Sales OBO ticket → trader booking → trade.

#### Booking (2)
7. **Sales Direct** — Correlation. FRA. 3 events. SALES_BOOKING → TRADING_ACCEPT → TRADE. Direction: LHS_FIRST.
8. **Trader First** — Correlation. REPO. 4 events. TRADING_BOOKING → SALES_BOOKING → MATCH → TRADE. Direction: LHS_FIRST.

#### Prime Brokerage (1)
9. **Give-Up** — Correlation. BOND. 3 events. TRADE → GIVEUP_NOTICE → GIVEUP_ACCEPT. Resolution: TRANSFER_BOOKING.

#### Matching / Breaks (6)
10. **Unmatched** — Correlation. FX_NDF. 1 event. Single booking, no counterpart. SLA timer starts.
11. **Partial Match** — Correlation. XCCY_SWAP. 2 events. Two bookings with tolerance breaks. Breaks logged field-by-field.
12. **Failed STP** — Correlation + Transform. BOND_FUTURE. 1 event. Inbound message fails STP validation rules.
13. **Force Match** — Override. FX_SWAP. ~6 events. Force match → correct booking → UNMATCH → MATCH. Requires approval + reason.
14. **Rematch** — Override. IRS. 5 events. SALES_BOOKING → UNMATCH → corrected TRADING → MATCH.
15. **Dispute** — Override + Reconciliation. EQUITY. 2 events. Matched pair flagged with tolerance breaks. Resolution: ACCEPT_LHS, ACCEPT_RHS, or SPLIT_DIFFERENCE.

#### Product-Specific (4)
16. **FX Compensation** — Aggregation. FX_SPOT. 15-20 events. Multiple facility draws → bilateral netting → single net settlement.
17. **IRS Clearing** — Correlation. IRS. 6 events. Trade → CCP clearing submission → novation (cpty: BARC → LCH).
18. **Bond Broker Exec** — Allocation. BOND. 4 events. Broker order → fills → trade.
19. **FX Option Hedge** — Correlation. FX_OPTION. 5 events. Client option → delta hedge → risk allocation.

#### Post-Trade (3)
20. **Allocation** — Allocation. TRS. 5-6 events. Block TRADE (50M) → 2-4 ALLOC_SPLIT events. SUM(children)==parent, remainder tracking.
21. **Trade Confirm** — Correlation. SWAPTION. 2 events. Booking → counterparty affirmation (MarkitWire/DTCC).

#### Lifecycle (4)
22. **Cancel** — Lifecycle. FX_SPOT. 3 events. TRADE → CANCEL_REQUEST → CANCEL_CONFIRM.
23. **Novation** — Lifecycle. XCCY_SWAP. 4 events. TRADE → NOVATION_REQUEST → NOVATION_ACCEPT → new TRADE.
24. **Roll** — Lifecycle. FX_FORWARD. 3 events. Close near leg → open far leg (linked as ROLL).
25. **Exercise** — Lifecycle. SWAPTION. 3 events. Option TRADE → EXERCISE_NOTICE → underlying IRS TRADE.

#### Compression (1)
26. **Compression** — Aggregation. IRS. 3+ events. N offsetting trades → compressed replacement.

#### Recon (4)
27. **EOD Position** — Reconciliation. All products. 2 events. Position snapshot vs computed positions.
28. **Settlement Recon** — Reconciliation. All products. 2 events. Settlement instruction vs cleared trades. SSI matching.
29. **Margin Recon** — Reconciliation. All products. 2 events. Margin call vs computed exposure. VM diff thresholds.
30. **Regulatory Recon** — Reconciliation. All products. 2 events. Regulatory snapshot vs internal records.

---

### PART 7: ENUMS (60+ enumerations)

All enums in one file: `_enums.yaml` with `blueprint: enum`, `kind: XFTWSEnums`. Each enum entry can have: `{ value, label, icon, color, group, description }`.

**Convention:** Value keys CAPS, labels Capitalized. Enum reference: `enum: $enums.ENUM_NAME`.

Full enum list with exact values specified above in Parts 2-6. Key enums:
- `ENUM_EVENT_TYPE` — 40+ values (AXE, RFQ, QUOTE, ORDER, AUCTION_BID, SALES_BOOKING, TRADING_BOOKING, TRADING_ACCEPT, OBO_TICKET, STP_MESSAGE, BROKER_FILL, CLEARING_MSG, CLEARING_SUBMISSION, AFFIRM_MSG, GIVEUP_NOTICE, GIVEUP_ACCEPT, MATCH, UNMATCH, ALLOC_SPLIT, SETTLEMENT_INSTR, MARGIN_CALL, NET_SETTLEMENT, AMENDMENT, CANCEL_REQUEST, CANCEL_CONFIRM, NOVATION_REQUEST, NOVATION_ACCEPT, EXERCISE_NOTICE, INTERNAL_TRANSFER, TRADE, RISK_MEASURE, SCHEDULE_EVENT, POSITION_SNAPSHOT)
- `ENUM_MATCH_SCENARIO` — 50+ values covering all 30 business scenarios + sub-variants (AXE_TO_RFQ, AXE_WITHDRAW, RFQ_HIT, RFQ_MISS, COMPETITIVE_RFQ, VENUE_RFQ, CLIENT_RFQ, OUTBOUND_RFQ_HIT/MISS, STREAMING_QUOTE, STREAM_TO_TRADE, STREAM_TO_RFQ, SPREAD_RFQ, IMM_FIXING_RFQ, DIRECT_CLEARING, CLEARING_REJECTED, BOND_AUCTION_FULL/PARTIAL/MISS, BOND_CONNECT_BUY/SELL, SWAP_CONNECT, BACK_TO_BACK, STP_AUTO, BROKER_EXEC, OBO_CLIENT, SALES_DIRECT, TRADER_FIRST, GIVEUP, UNMATCHED_BOOKING, PARTIAL_MATCH, FAILED_STP, FORCE_MATCH, REMATCH, DISPUTE, FX_COMPENSATION, IRS_CLEARING, BOND_BROKER_EXEC, FX_OPTION_HEDGE, ALLOCATION, TRADE_CONFIRM, CANCEL, NOVATION, ROLL, EXERCISE, COMPRESSION, SETTLEMENT_RECON, EOD_POSITION, MARGIN_RECON, REGULATORY_RECON, MARKET_ABUSE_SPOOFING, MANUAL_LINK)
- `ENUM_PRODUCT_TYPE` — 15 types (FX_SPOT, FX_FORWARD, FX_SWAP, FX_NDF, FX_OPTION, IRS, XCCY_SWAP, SWAPTION, FRA, BOND, BOND_FUTURE, REPO, CDS, TRS, EQUITY)

---

### PART 8: AXIS DEFINITIONS (`_axis_defs.yaml`)

Golden source for axis semantics per record type. All store schemas share the same physical axes. This config declares what each axis MEANS for each type/subtype. Code, UI, and validation read this — no hardcoded axis semantics anywhere.

**Format:** Keyed by `schema → discriminator_value → axis → { role, label?, format?, example?, note? }`.

**Display rules:**
- `label` — column header (auto-derived from role if absent: snake_case → Title Case)
- `format` — value formatter: `num0` ("95"), `num2` ("98.25"), `num4` ("4.1200"), `num6` ("1.084200"), `pct2` ("4.12%"), `pct4` ("4.1200%"), `bps0` ("125bp"), `bps2` ("12.50bp"), `ccy` ("$1,250,000"), `date` ("2026-03-20"), `text` (as-is)

**mkt section** (keyed by observation_type + tb):
- Rates curve instruments: SOFR_DEPO, SOFR_IMM, SOFR_FRA, SOFR_SWAP (with YAML anchors for shared patterns)
- Basis/cross-currency: XCCY_SWAP, TENOR_BASIS
- FX: FX_SPOT, FX_FWD, FX_SWAP
- Bond: BOND_PRICE (clean/accrued/dirty)
- Volatility: FX_VOL, IR_SWPNVOL
- Model params: IR_SABR
- Correlation: CORR

**measure section** (keyed by metric):
- Risk greeks: DV01, TBO1, FXDELTA, FXVEGA, MTM, NAV, PNL, CORR, THETA, GAMMA, RHO
- Schedule-derived (29 types): NEXT_COUPON, NEXT_RESET, NEXT_EXERCISE, NEXT_CALL, NEXT_PRINCIPAL, NEXT_FIXING, NEXT_ROLL, NEXT_PAYMENT, PREV_COUPON, PREV_RESET, PREV_FIXING, MATURITY, EFFECTIVE, FIRST_CALL, BARRIER_KI, BARRIER_KO, TRIGGER, ACCRUED

**diary section** (keyed by schedule_type):
- COUPON, RESET, PRINCIPAL, EXERCISE, BARRIER, FIXING

---

### PART 9: BLOOMBERG FIELD MAPPING (`_bloomberg_map.yaml`)

Mnemonic → canonical field path mapping for ingest pipeline normalization. Single source of truth.

**Sections with complete field mappings:**
- **Identifiers** (14 fields): ID_ISIN→ids.isin, ID_CUSIP→ids.cusip, ID_SEDOL1→ids.sedol, ID_BB_GLOBAL→ids.figi, etc.
- **Pricing** (21 fields): PX_BID→quote.bid, PX_ASK→quote.ask, PX_MID→quote.mid, PX_LAST→quote.last, PX_DIRTY_BID/ASK/MID, VWAP, volume, turnover, etc.
- **Yields** (10 fields): YLD_YTM_BID/ASK/MID, YTW, YTC, YTP, current, discount, real, breakeven
- **Spreads** (8 fields): OAS, Z-spread, I-spread, G-spread, ASW, benchmark, CDS basis
- **Duration** (12 fields): modified, macaulay, effective, spread dur, convexity, DV01, PV01, WAL
- **Greeks** (5 fields): delta, gamma, vega, theta, rho
- **Volatility** (8 fields): implied (bid/ask/mid), realized (10d/30d/90d), risk reversal, butterfly, beta
- **Risk** (7 fields): VaR 95/99, Sharpe, Sortino, information ratio, tracking error, max drawdown
- **Fundamentals** (16 fields): PE, PB, PS, EV/EBITDA, market cap, revenue, EBITDA, EPS, ROE, ROA, margins, dividend yield
- **ESG** (8 fields): disclosure, environmental, social, governance scores, carbon emissions scope 1/2/3, employees, board diversity
- **Per-asset overlays:** equity (5 fields), fixed income (10 fields), futures (12 fields), options (5 fields), MBS (11 fields), FX (4 fields)

---

### PART 10: SERVER-SIDE EVENT-DRIVEN ARCHITECTURE

#### 10.1 Event Processing Pipeline

```
Source Systems                  Ingestion Gateway              Event Store
(Bloomberg, Tradeweb,    →    (parse, validate,         →    (append-only,
 FIX, FpML, SWIFT,             transform, enrich)             immutable events)
 REST, Chat)                                        │
                                      ▼              
                              Transformer Registry   
                              key: (source, protocol,
                                    event_type, product_type)
                              produces: canonical payload{}
                                                    │
                                      ▼              
                              ┌─────────────────────┐
                              │  MATCHING ENGINE    │
                              │                     │
                              │  5 Primitives:      │
                              │  • Correlation (1:1)│
                              │  • Reconciliation   │
                              │  • Allocation (1:N) │
                              │  • Aggregation (N:1)│
                              │  • Override (1:0)   │
                              │                     │
                              │  Status Machine:    │
                              │  UNMATCHED → PARTIAL│
                              │  → MATCHED → FORCED │
                              │  → DISPUTED → RESOLVED│
                              └──────────┬──────────┘
                                                    │
              ┌──────────────┬───────────┼───────────┬──────────────┐
              ▼              ▼           ▼           ▼              ▼
        Enrichment     Materialization  Notification  Risk         Regulatory
        Pipeline       Pipeline         Pipeline     Pipeline      Pipeline
        (risk flags,   (txn, leg,       (WebSocket,  (DV01, FX∆,  (UTI, USI,
         compliance,    party, book,     SSE push,    MTM, PnL,    EMIR, MiFID,
         pricing)       instrument)      SLA alerts)  scenarios)   Dodd-Frank)
```

#### 10.2 Seven Event-Driven Pipelines

Each pipeline is triggered by an event arriving in the store:

1. **`on_booking_received`** — Sales or trading booking arrives. Look up matching rules for scenario. Create or update correlation chain. Compare economics field-by-field if counterpart exists. Set match_status (UNMATCHED, PARTIAL, MATCHED). Start SLA timer if UNMATCHED. If auto-match rules pass, create materialized TRADE event.

2. **`on_external_message`** — External message arrives (STP, affirm, clearing, broker fill). Parse raw → canonical payload via transformer. Correlate with existing booking events by key fields. Run STP rules (if applicable). Auto-book if all rules pass (stp_status=BOOKED), else flag as FAILED.

3. **`on_allocation_requested`** — Block trade needs splitting. Validate: SUM(child_notionals) == parent_notional. Track remainder. Status: PARTIAL until SUM == parent, then MATCHED. Each ALLOC_SPLIT creates a child TRADE event.

4. **`on_settlement_due`** — Value date approaching. Generate SETTLEMENT_INSTR events. Match SSI details with counterparty. Run netting engine for same (cpty, ccy, value_date) group. Create NET_SETTLEMENT events. Track settlement status through to SETTLED/FAILED.

5. **`on_amendment_filed`** — Amendment event arrives. Validate amendment_type. For ECONOMIC: requires approval chain (role-based). For NED: auto-approve. Version bump on target event. Record changes[] with old/new values. Create new event version.

6. **`on_position_snapshot`** — EOD position capture. Compare POSITION_SNAPSHOT with computed positions from materialized trades. Run reconciliation primitive (field-by-field diff). Flag breaks for ops resolution.

7. **`on_override_action`** — Manual override (force match, rematch, dispute resolution). Validate authorization (operations/admin role). Record audit trail (who, when, why, resolution action). Apply resolution: ACCEPT_LHS, ACCEPT_RHS, SPLIT_DIFFERENCE, FORCE_MATCH, AUTO_BOOK.

#### 10.3 Workflow Engine (19 states)

Schema-driven state machine with:
- **Role guards** — which roles can trigger which transitions
- **Required fields** — fields that must be populated before transition
- **Auto-set timestamps** — `created_at`, `updated_at`, `matched_at`, `enriched_at`
- **SLA deadlines** — e.g., UNMATCHED must resolve within 24h, PENDING settlement must instruct within T+1
- **Transition log** — every state change recorded in `transitions[]`

States: ACTIVE, PENDING, UNMATCHED, PARTIAL, MATCHED, CONFIRMED, AFFIRMED, CLEARED, SETTLED, CANCELLED, REJECTED, EXPIRED, FAILED, TRADED_AWAY, FORCED, DISPUTED, RESOLVED, NOVATED, COMPRESSED.

#### 10.4 Data Store Design

**Primary store:** Event collection (append-only, immutable). Indexed on: `event_id`, `event_type`, `status`, `chain_id`, `correlation.scenario`, `product_type`, `cpty_id`, `desk`, `created_at`.

**Materialized stores** (projections created by matching engine):
- `txn` — trade headers, indexed on `txn_id`, `product_type`, `status`, `book_id`
- `leg` — trade legs, indexed on `leg_id`, `txn_id`, `leg_type`
- `party` — parties, indexed on `party_id`, `party_type`, `lei`
- `entity` — entities (extended), indexed on `entity_id`, `entity_type`
- `book` — books, indexed on `book_id`, `desk`, `region`
- `instrument` — instruments, indexed on `security_id`, `ids.isin`, `ids.figi`, `security_type`
- `mkt` — market data, indexed on `mkt_key`, `snap`, `as_of_date`, `observation_type`, `ta`, `tb`
- `measure` — risk measures, indexed on `measure_key`, `metric`, `snap`, `as_of_date`, `txn_id`
- `diary` — schedules, indexed on `schedule_key`, `txn_id`, `schedule_type`, `status`
- `journal` — blotter (denormalized), indexed on `event_id`, `event_type`, `txn_id`, `chain_id`

**Streaming:** Append-mode at 2s intervals. `limit: 100` caps window. WebSocket/SSE for real-time UI push.

**Encryption:** Three separate DEKs:
1. Trade economics (notional, rate, price)
2. Counterparty PII (names, contacts, addresses)
3. Risk measures (DV01, MTM, PnL)

**RBAC:** Six roles: `sales` (own desk events), `trading` (own desk events), `operations` (all events, write), `risk` (all events, read-only), `compliance` (all events, read-only + audit), `admin` (all access).

#### 10.5 Scenario Analysis Engine

Composable shift blocks + scenario definitions for P&L impact analysis:

**Core equation:** `P&L_impact = Σ (sensitivity_i × shift_i)`

- Shift blocks target valid `mkt_key` patterns (ta/tb/tc axis convention)
- Each shift declares a `metric_map` — which greek(s) in `measure.yaml` it impacts
- Engine joins shift → mkt → measure via shared (ta, tb, tc) coordinates
- `measure.mkt_id` FK provides the audit trail: which mkt point produced this greek
- Results always show: `greek` (base) → `shift` (delta) → `impact` (greek × shift)
- Book metadata (desk, lob, country, trader_id) drives slicing dimensions

**Greek-to-Shift mapping:**
| Shift asset_class | mkt.tb targets       | measure.metric | P&L formula                  |
| ----------------- | -------------------- | -------------- | ---------------------------- |
| IR                | SOFR_SWAP, SOFR_DEPO | DV01           | DV01.ya × delta_bps          |
| IR                | SOFR_3M6M_BASIS      | TBO1           | TBO1.ya × delta_bps          |
| FX (SPOT)         | FX_SPOT              | FXDELTA        | FXDELTA.ya × (delta_pct/100) |
| FX (VOL)          | FX_VOL               | FXVEGA         | FXVEGA.ya × delta_vol_pts    |
| IR (VOL)          | IR_SWPNVOL           | VEGA           | VEGA.ya × delta_normal_vol   |

---

### PART 11: SYSTEM FIELDS & CONVENTIONS

**`_system.yaml`** — auto-injected system fields: `xorigin` (USER, API, SEED, SYNC, SYSTEM, MIGRATION, IMPORT, ADMIN), `workflow` (DRAFT, ACTIVE, SUSPENDED, ARCHIVED).

**ID qualifiers:** event=`ftv-`, txn=`fttx-`, leg=`ftlg-`, mkt=`ftmk-`, measure=`ftms-`, diary=`ftsc-`, party=`ftp-`, entity=`fte-`, book=`ftb-`, instrument=`ftsc-`, journal=`ftev-`, fpml=`ftf-`.

**Timezone:** America/New_York (FICC trading follows NYC business hours).

**Column ordering convention:** `col` property for table view. Values: `"1<"` (first, left-pinned), `"2<"` (second, left-pinned), `3`, `4` (ordinal position). Event: event_type=`"1<"`, event_id=`"2<"`, status=3, source=4.

**UI views per schema:** Each schema declares `views[]` with: table (default), card (title/subtitle/badge), kanban (group_by), bar chart (x/y), pie chart (x/y). Grid widths via `grid: "3"` (out of 12).

**Sections:** Each schema declares `sections[]` grouping fields for form layout. Section properties: name, label, icon, roles (optional access restriction).
