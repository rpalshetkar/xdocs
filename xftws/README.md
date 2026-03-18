---
_pulse:
  generated_at: '2026-03-17T02:25:50+00:00'
  sources:
  - glob: domains/*/schemas/*.yaml
    hash: 5d9c3458
  - glob: domains/*/assembly.yaml
    hash: 0edd546e
  - glob: domains/*/ontology.yaml
    hash: 7bef2011
  - glob: domains/*/server/mock_data.py
    hash: 2d3f4cba
  commit: 7ae9077
---

# xftws — Fixed Income, Currencies & Commodities Trading

> Event-centric matching engine — unified event log with three-layer payloads (raw/payload/enriched), 30 matching scenarios, 5 foundation primitives, and full trade lifecycle tracking.

## What It Does

Full sell-side fixed income trading workflow built on a **unified event architecture**. All business actions (bookings, fills, amendments, risk measures, settlements) flow through a single polymorphic `events` collection. The matching engine correlates events using 5 matching primitives (correlation, reconciliation, allocation, aggregation, override) across 30 business scenarios.

Three-layer payload model: `raw{}` (source-native wire message, immutable) → `payload{}` (canonical transform for matching) → `enriched{}` (post-match risk, regulatory, settlement additions).

Reference data (entities, books, FpML templates) remains as separate datasets.

## Foundation Primitives

XDS engine features this domain configures. Only differentiating primitives listed — universal features (connectors, mock data, ontology, XNS, caching) are standard across all domains. **xftws uses all 6 foundation primitives — the full XDS feature set.**

| Primitive       | XDS Engine Provides                                              | xftws Configures                                                                                                                                                                                                                                                                                                                                                 |
| --------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workflow**    | Schema-driven state machine with SLA timers and transition rules | 19-state event lifecycle: Pre-trade (PENDING → QUOTED → ACCEPTED / REJECTED / EXPIRED), Execution (OPEN → PARTIAL_FILL → FILLED), Matching (UNMATCHED → PARTIAL / MATCHED / FORCED → DISPUTED → RESOLVED), Trade lifecycle (CONFIRMED → CLEARED → SETTLED). Universal: any → PENDING, any → CANCELLED. Revision control via `transitions[]` append-only diff log |
| **Streaming**   | Real-time push with configurable interval, op, and key           | `events` (2s append by event_id, limit: 100) — real-time event feed for matching engine, risk dashboards, and trade blotters                                                                                                                                                                                                                                     |
| **Encryption**  | Field-level DEK via KMS with key vault                           | 3 DEKs: `xftws_trade_economics_dek` (notional, price, spread, premium), `xftws_counterparty_pii_dek` (contact info, SSIs, bank details), `xftws_risk_measures_dek` (Greeks, VaR, exposure values)                                                                                                                                                                |
| **RBAC**        | Role-based dataset permissions with scoped read/write/delete     | 6 roles: `sales` (create bookings), `trading` (execute trades), `operations` (settlement, clearing), `risk` (ro), `compliance` (ro + regulatory), `admin`. Per-dataset ACL across 5 datasets + view. RLS: event dataset scoped by actor to `$ctx.identity` for actor-filtered event visibility                                                                   |
| **Views**       | Virtual computed datasets with joins                             | `trade_blotter`: events + entities + books → enriched blotter with entity context and desk/strategy from books                                                                                                                                                                                                                                                   |
| **Auth Policy** | Policy-based API auth with ordered rule evaluation               | 4 policies: dev-bypass (localhost admin), health-public (system/meta read), user-auth (JWT bearer), default-deny                                                                                                                                                                                                                                                 |

## Domain Adaptations

xftws's business logic is the most architecturally complex — a unified event architecture with polymorphic payloads, 5 matching primitives, 30 scenarios, and a complete trade lifecycle. The foundation primitives provide the infrastructure; the domain adaptations below define the business rules.

### Event-Centric Architecture

**One schema, many types**: The `event_type` discriminator field drives polymorphic `payload{}` structure. All 10 former datasets (trade, leg, schedule, match, allocation, amendment, measure) absorbed into the single `events` collection.

### Three-Layer Payload Model

```
Layer 1: raw{}  — immutable source-native wire message
├─ format: FIX | FPML | SWIFT_MT | SWIFT_MX | JSON | CSV | INTERNAL
├─ version: protocol version string
├─ content: parsed dict
├─ raw_text: original wire bytes
├─ checksum: SHA-256 for tamper detection
└─ source_msg_id: external system reference

Layer 2: payload{}  — canonical transform (MATCHING ENGINE READS ONLY THIS)
├─ Event-type-specific fields per _event_payloads/*.yaml
├─ Transformer: raw.content → payload (keyed by source × protocol × event_type × product_type)
└─ Examples:
   ├─ SALES_BOOKING: trade_economics{}, parties[], legs[], book_id, strategy
   ├─ AMENDMENT: target_event_id, amendment_type, changes[], approvals[]
   └─ SETTLEMENT_INSTR: payment_direction, amount, currency, value_date, ssi_id

Layer 3: enriched{}  — post-match additions
├─ risk_flags: [LARGE_NOTIONAL, CONCENTRATION_RISK, NEW_COUNTERPARTY, LIMIT_BREACH, ...]
├─ regulatory: {uti, usi, lei, jurisdiction[], reporting_status, reported_at}
├─ settlement: {ssi_id, nostro, value_date, settlement_status}
├─ pricing: {mid_price, spread, markup_bps, benchmark}
└─ compliance: {approved_by, limit_check, wash_trade_flag, best_execution}
```

### Event Lifecycle (19-State)

```
Universal (from any state):
  * → PENDING, * → CANCELLED

Pre-trade:       PENDING → QUOTED → ACCEPTED / REJECTED / EXPIRED
Execution:       PENDING → OPEN → PARTIAL_FILL → FILLED
Matching:        PENDING → UNMATCHED → PARTIAL / MATCHED / FORCED
                 UNMATCHED → MATCHED
                 MATCHED → DISPUTED → RESOLVED
Trade lifecycle: MATCHED → CONFIRMED → CLEARED → SETTLED
                 CONFIRMED → SETTLED (direct)
```

**Revision control**: `transitions[]` append-only log on every event captures `{from_status, to_status, at, by, reason, diff}` — field-level diffs for full audit trail. This is now schema-driven via the `workflow:` key, with the XDS engine enforcing valid transitions and SLA timers.

### Event Types (29)

| Category         | Types                                                                                                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pre-trade**    | RFQ, QUOTE, ORDER, CLIENT_RFQ                                                                                                                                                |
| **Booking**      | SALES_BOOKING, TRADING_BOOKING, OBO_TICKET, STP_MESSAGE, TRADING_ACCEPT                                                                                                      |
| **External**     | BROKER_FILL, CLEARING_MSG, AFFIRM_MSG, GIVEUP_NOTICE, GIVEUP_ACCEPT                                                                                                          |
| **Matching**     | MATCH, UNMATCH                                                                                                                                                               |
| **Lifecycle**    | ALLOC_SPLIT, SETTLEMENT_INSTR, MARGIN_CALL, NET_SETTLEMENT, AMENDMENT, CANCEL_REQUEST, CANCEL_CONFIRM, NOVATION_REQUEST, NOVATION_ACCEPT, EXERCISE_NOTICE, INTERNAL_TRANSFER |
| **Materialized** | TRADE, RISK_MEASURE, SCHEDULE_EVENT, POSITION_SNAPSHOT                                                                                                                       |

### Event Linking

`links[]` array with typed relationships (CORRELATES_WITH, PARENT_OF, AMENDS, SETTLES, MEASURES, etc.) forming directed event graphs.

### 5 Matching Primitives

| Primitive          | Cardinality | Logic                                               | Scenarios                                                                                  |
| ------------------ | ----------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Correlation**    | 1:1         | Key match + tolerance field comparison              | #1 Sales→Trader, #2 Trader→Sales, #3 Simultaneous, #6 Clearing, #8 OBO, #9 Affirm, #11 B2B |
| **Reconciliation** | 1:1         | Field-by-field diff with tolerance + priority       | #13 Amendment, #14 EOD Recon, #20 Settlement, #22 Margin, #23 Regulatory                   |
| **Allocation**     | 1:N         | SUM(children) == parent, remainder tracking         | #4 Block→Client splits, #18 Order→Fills                                                    |
| **Aggregation**    | N:1 / N:M   | Group-by key + aggregate function                   | #12 Partial Fills→Order, #15 Netting, #16 Compression                                      |
| **Override**       | 1:0         | Force-resolve with no counterpart, audit + approval | #5 Force Match, #24 Dispute Resolution                                                     |

### Matching Scenarios (30)

| Group                | Scenarios                                                           |
| -------------------- | ------------------------------------------------------------------- |
| **Price Discovery**  | RFQ Hit, RFQ Miss                                                   |
| **Execution**        | Back-to-Back, STP Auto-book, Broker Exec, OBO Client                |
| **Booking**          | Sales Direct, Trader First                                          |
| **Prime Brokerage**  | Give-Up                                                             |
| **Matching/Breaks**  | Unmatched, Partial Match, Failed STP, Force Match, Rematch, Dispute |
| **Product-Specific** | FX Compensation, IRS Clearing, Bond Broker Exec, FX Option Hedge    |
| **Post-Trade**       | Allocation, Trade Confirm                                           |
| **Lifecycle**        | Cancel, Novation, Roll, Exercise                                    |
| **Compression**      | Compression                                                         |
| **Recon**            | EOD Position, Settlement, Margin, Regulatory                        |

### Scenario Complexity Matrix

| Complexity             | Scenarios                                                                  | Required Service                     |
| ---------------------- | -------------------------------------------------------------------------- | ------------------------------------ |
| **Pure Config**        | #1, #2, #3, #5, #13                                                        | Key matching only (foundation)       |
| **Config + Transform** | #6, #7, #8, #9, #10, #12, #14, #15, #16, #17, #18, #19, #20, #22, #23, #24 | Domain-specific service per scenario |

### Correlation Metadata

Each matched event carries `correlation{}` with: match_type, scenario, match_status (UNMATCHED/PARTIAL/MATCHED/FORCED), cardinality, direction (LHS/RHS/PARENT/CHILD), breaks (field-level diffs with tolerance), resolution, matched_at/by.

### Encrypted Fields

| DEK                          | Encrypted Fields                                       | Purpose                                             |
| ---------------------------- | ------------------------------------------------------ | --------------------------------------------------- |
| `xftws_trade_economics_dek`  | notional, price, spread, premium, markup_bps           | Trade valuation — visible to trading + risk + admin |
| `xftws_counterparty_pii_dek` | contact_name, contact_email, ssi_details, bank_account | Counterparty PII — visible to operations + admin    |
| `xftws_risk_measures_dek`    | mtm, dv01, vega, gamma, var_95                         | Risk sensitivities — visible to risk + admin        |

### Product Economics

FpML-driven leg structures for 15 product types: FX (Spot, Forward, Swap, NDF, Option), Rates (IRS, XCCY Swap, Swaption, FRA), Credit (CDS, TRS), Fixed Income (Bond, Bond Future, Repo), Equity. Each product defines PAY/RECEIVE legs with product-specific economics. Risk metrics: MTM, DV01, Greeks across tenor buckets (1M–30Y).

### Trade Materialization

TRADE events are **created by the matching engine** (not by users) when correlated booking events converge. Denormalized from LHS + RHS bookings.

### Extension Points

| Hook                    | Current                           | Plugin Opportunity                                                                                                                       |
| ----------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Source transformers** | Internal format only              | FIX, FpML, SWIFT MT/MX, MarkitWire, DTCC, Bloomberg, Tradeweb, LCH, CME, ICE adapters                                                    |
| **Enrichment services** | None (enriched{} structure ready) | Risk engine (flags, pricing), regulatory gateway (UTI/USI/LEI), settlement service (SSI routing), compliance service (approvals, limits) |
| **Matching plugins**    | Pure config (key matching)        | Per-scenario services: clearing/novation, affirm gateway, give-up service, fill aggregator, netting engine, compression service          |
| **Break tolerance**     | Fixed field comparison            | Configurable tolerance per field (%, pips, bps) with auto-resolution rules                                                               |
| **Payload schemas**     | 29 event types                    | New event types by adding `_event_payloads/{type}.yaml` + enum entry                                                                     |

## Datasets

| Dataset         | Records | Key       | Mode                               | Features                                                |
| --------------- | ------- | --------- | ---------------------------------- | ------------------------------------------------------- |
| `entities`      | 20      | entity_id | Standard (cached)                  | Legal entities, CCPs, brokers with LEI                  |
| `books`         | 30      | book_id   | Standard (cached)                  | Trading books/portfolios per entity                     |
| `fpmls`         | 15      | fpml_id   | Standard (cached)                  | ISDA FpML product templates                             |
| `events`        | ~200    | event_id  | Streaming (2s, append, limit: 100) | Unified event log — 29 event types, polymorphic payload |
| `trade_blotter` | —       | —         | View (streaming)                   | Events enriched with entity and book context            |

**Active schemas (6):** `_enums.yaml`, `_system.yaml`, `entity.yaml`, `book.yaml`, `fpml.yaml`, `event.yaml`

**Event payload schemas (29):** `_event_payloads/{rfq, quote, order, client_rfq, sales_booking, trading_booking, obo_ticket, stp_message, trading_accept, broker_fill, clearing_msg, affirm_msg, giveup_notice, giveup_accept, match, unmatch, alloc_split, settlement_instr, margin_call, net_settlement, amendment, cancel_request, cancel_confirm, novation_request, novation_accept, exercise_notice, internal_transfer, position_snapshot, trade, risk_measure, schedule_event}.yaml`

## Server

**Factories**: `EntityFactory`, `BookFactory`, `FPMLFactory`, `EventFactory` (polymorphic)
**Generator**: `gen_fixtures()` → FK-wired event chains covering all 30 scenarios

## Config

- **Accent**: Emerald | **Icon**: Trending-up | **Timezone**: America/New_York
- **Deploy group**: main (Railway)
- **Caching**: Qwik multi-layer. Reference data (entities, books, fpmls) cached; events exclude cache
- **Features**: qwik_cache, redis_pubsub, websockets, audit_logging, field_encryption
- **Schema features**: `col:` property pins event_type, event_id, status, source in table view; UI consumes shared @xdsui components (RecordDetail, RecordEditForm)

## See Also

- [ontology.yaml](ontology.yaml) — Machine-readable entity definitions and relationships
- [PRD.md](PRD.md) — Full product requirements (30 scenarios, UI specs, build tree)
- [UIX.md](UIX.md) — UIX architecture (component specs, workspace layouts, data flow)
- [FEATURES.md](../../FEATURES.md) — Platform-wide feature summary
