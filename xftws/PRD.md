# Fixed Income Matching & Correlation Engine — PRD

> Specification for a generalized event-correlation engine supporting all fixed income trading desk matching, reconciliation, allocation, and STP workflows.

---

## 1. Problem Statement

The current matching schema models a narrow use case: "internal sales view vs external counterparty view" with a fixed 1:1 LHS/RHS structure. Real-world fixed income desks require **30 distinct matching scenarios** spanning correlation, reconciliation, allocation, aggregation, STP, and override — each with different cardinalities, event sources, resolution actions, and lifecycle states.

The solution: a **data-agnostic matching foundation** (5 primitives) that domain-specific **business scenarios configure** without writing new engines.

---

## 2. Foundation Layer (Data-Agnostic Engine)

Five generic, reusable primitives. They know nothing about fixed income trading — they pair abstract events.

### 2.1 Foundation Primitives

| Primitive          | What It Does                                                       | Cardinality | Core Logic                                             |
| ------------------ | ------------------------------------------------------------------ | ----------- | ------------------------------------------------------ |
| **Correlation**    | Pair two independent events representing the same economic reality | 1:1         | Key match + tolerance-based field comparison           |
| **Reconciliation** | Compare two views of the same record, find breaks                  | 1:1         | Field-by-field diff with tolerance + priority rules    |
| **Allocation**     | Split one record into N child records, validate completeness       | 1:N         | SUM(children) == parent, remainder tracking            |
| **Aggregation**    | Combine N records into 1 or M (inverse of allocation)              | N:1 / N:M   | Group-by key + aggregate function (sum, net, compress) |
| **Override**       | Force-resolve with no counterpart, audit trail                     | 1:0         | Manual action + approval + reason                      |

### 2.2 Shared Primitives (all foundations use)

```
- LHS / RHS as generic event containers (source, event_type, payload, timestamp)
- Break detection engine (field-level diff + configurable tolerance per field)
- Status machine: UNMATCHED → PARTIAL → MATCHED → FORCED → DISPUTED → RESOLVED
- Match rules: configurable per scenario (key fields, tolerance, auto-match threshold)
- Cardinality tracking: expected vs actual counts on each side
- Audit trail: who, when, why, resolution action taken
- Direction: which side initiated (LHS_FIRST / RHS_FIRST / SIMULTANEOUS)
```

### 2.3 Foundation Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  MATCHING ENGINE (foundation)                   │
│                                                                 │
│  ┌──────────────┐ ┌───────────────┐ ┌────────────────────────┐  │
│  │ Correlation  │ │ Reconciliation│ │ Allocation             │  │
│  │              │ │               │ │                        │  │
│  │ 1:1 pair     │ │ 1:1 diff      │ │ 1:N split + validate   │  │
│  │ Key match    │ │ Break detect  │ │ SUM == parent          │  │
│  │ Tolerance    │ │ Priority rules│ │ Remainder tracking     │  │
│  └──────────────┘ └───────────────┘ └────────────────────────┘  │
│                                                                 │
│  ┌──────────────┐ ┌───────────────┐                             │
│  │ Aggregation  │ │ Override      │                             │
│  │              │ │               │                             │
│  │ N:1 combine  │ │ 1:0 force     │                             │
│  │ N:M compress │ │ Audit trail   │                             │
│  └──────────────┘ └───────────────┘                             │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ SHARED: events, breaks, status machine, rules, audit      │  │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Business Scenarios (Complete Map)

### 3.1 Summary Table (30 Scenarios)

| #   | Scenario                    | Foundation                | Product     | Events | Description                                            |
| --- | --------------------------- | ------------------------- | ----------- | ------ | ------------------------------------------------------ |
|     | **── Price Discovery ──**   |                           |             |        |                                                        |
| 1   | RFQ Hit                     | Correlation               | FX_SPOT     | ~6     | Bilateral negotiation rounds → trade                   |
| 2   | RFQ Miss                    | Correlation               | FX_FORWARD  | ~5     | Negotiation → client trades away (TRADED_AWAY)         |
|     | **── Execution ──**         |                           |             |        |                                                        |
| 3   | Back-to-Back                | Correlation               | IRS         | 4-5    | Client trade → internal transfer → street hedges       |
| 4   | STP Auto-book               | Correlation + Transform   | BOND        | 2      | Inbound STP → auto-generated booking                   |
| 5   | Broker Exec                 | Allocation                | FX_OPTION   | 3-5    | ORDER → individual BROKER_FILL events                  |
| 6   | OBO Client                  | Correlation               | CDS         | 3      | Sales OBO ticket → trader booking → trade              |
|     | **── Booking ──**           |                           |             |        |                                                        |
| 7   | Sales Direct                | Correlation               | FRA         | 3      | SALES_BOOKING → TRADING_ACCEPT → TRADE                 |
| 8   | Trader First                | Correlation               | REPO        | 4      | TRADING_BOOKING → SALES_BOOKING → MATCH → TRADE        |
|     | **── Prime Brokerage ──**   |                           |             |        |                                                        |
| 9   | Give-Up                     | Correlation               | BOND        | 3      | TRADE → GIVEUP_NOTICE → GIVEUP_ACCEPT                  |
|     | **── Matching / Breaks ──** |                           |             |        |                                                        |
| 10  | Unmatched                   | Correlation               | FX_NDF      | 1      | Single booking, no match                               |
| 11  | Partial Match               | Correlation               | XCCY_SWAP   | 2      | Two bookings with tolerance breaks                     |
| 12  | Failed STP                  | Correlation + Transform   | BOND_FUTURE | 1      | Inbound message fails STP rules                        |
| 13  | Force Match                 | Override                  | FX_SWAP     | ~6     | Force match → correct booking → UNMATCH → MATCH        |
| 14  | Rematch                     | Override                  | IRS         | 5      | SALES_BOOKING → UNMATCH → corrected TRADING → MATCH    |
| 15  | Dispute                     | Override + Reconciliation | EQUITY      | 2      | Matched pair flagged with tolerance breaks             |
|     | **── Product-Specific ──**  |                           |             |        |                                                        |
| 16  | FX Compensation             | Aggregation               | FX_SPOT     | 15-20  | Facility draws → bilateral netting                     |
| 17  | IRS Clearing                | Correlation               | IRS         | 6      | Trade → CCP clearing → novation                        |
| 18  | Bond Broker Exec            | Allocation                | BOND        | 4      | Broker order → fills → trade                           |
| 19  | FX Option Hedge             | Correlation               | FX_OPTION   | 5      | Client option → delta hedge → risk allocation          |
|     | **── Post-Trade ──**        |                           |             |        |                                                        |
| 20  | Allocation                  | Allocation                | TRS         | 5-6    | Block TRADE → 2-4 ALLOC_SPLIT events                   |
| 21  | Trade Confirm               | Correlation               | SWAPTION    | 2      | Booking → counterparty affirmation                     |
|     | **── Lifecycle ──**         |                           |             |        |                                                        |
| 22  | Cancel                      | Lifecycle                 | FX_SPOT     | 3      | TRADE → CANCEL_REQUEST → CANCEL_CONFIRM                |
| 23  | Novation                    | Lifecycle                 | XCCY_SWAP   | 4      | TRADE → NOVATION_REQUEST → NOVATION_ACCEPT → new TRADE |
| 24  | Roll                        | Lifecycle                 | FX_FORWARD  | 3      | Close near leg → open far leg (linked as ROLL)         |
| 25  | Exercise                    | Lifecycle                 | SWAPTION    | 3      | Option TRADE → EXERCISE_NOTICE → underlying IRS TRADE  |
|     | **── Compression ──**       |                           |             |        |                                                        |
| 26  | Compression                 | Aggregation               | IRS         | 3+     | N offsetting trades → compressed replacement           |
|     | **── Recon ──**             |                           |             |        |                                                        |
| 27  | EOD Position                | Reconciliation            | —           | 2      | Position snapshot vs computed positions                |
| 28  | Settlement Recon            | Reconciliation            | —           | 2      | Settlement instruction vs cleared trades               |
| 29  | Margin Recon                | Reconciliation            | —           | 2      | Margin call vs computed exposure                       |
| 30  | Regulatory Recon            | Reconciliation            | —           | 2      | Regulatory snapshot vs internal records                |

### 3.2 Module Classification (30 Scenarios)

```
┌─────────────────────────────────────────────────────────────────┐
│                    MATCHING ENGINE                              │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌───────────────────┐   │
│  │ PRICE DISC.   │  │ EXECUTION      │  │ BOOKING           │   │
│  │               │  │                │  │                   │   │
│  │ #1 RFQ Hit    │  │ #3 Back2Back   │  │ #7 Sales Direct   │   │
│  │ #2 RFQ Miss   │  │ #4 STP Auto    │  │ #8 Trader First   │   │
│  │               │  │ #5 Broker Exec │  │                   │   │
│  │               │  │ #6 OBO Client  │  │                   │   │
│  └───────────────┘  └────────────────┘  └───────────────────┘   │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌───────────────────┐   │
│  │ MATCH/BREAKS  │  │ PRODUCT-SPEC   │  │ LIFECYCLE         │   │
│  │               │  │                │  │                   │   │
│  │ #10 Unmatched │  │ #16 FX Comp    │  │ #22 Cancel        │   │
│  │ #11 Partial   │  │ #17 IRS Clear  │  │ #23 Novation      │   │
│  │ #12 Failed STP│  │ #18 Bond Exec  │  │ #24 Roll          │   │
│  │ #13 Force     │  │ #19 FX Opt Hdg │  │ #25 Exercise      │   │
│  │ #14 Rematch   │  │                │  │                   │   │
│  │ #15 Dispute   │  │                │  │                   │   │
│  └───────────────┘  └────────────────┘  └───────────────────┘   │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌───────────────────┐   │
│  │ POST-TRADE    │  │ RECON          │  │ OPS               │   │
│  │               │  │                │  │                   │   │
│  │ #9 Give-Up    │  │ #27 EOD Pos    │  │ #26 Compression   │   │
│  │ #20 Allocation│  │ #28 Settlement │  │                   │   │
│  │ #21 Confirm   │  │ #29 Margin     │  │                   │   │
│  │               │  │ #30 Regulatory │  │                   │   │
│  └───────────────┘  └────────────────┘  └───────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Product Coverage (15 Product Types)

Each scenario is wired to a specific product type, ensuring all 15 products appear in generated fixtures:

| Product     | Scenarios                                     |
| ----------- | --------------------------------------------- |
| FX_SPOT     | RFQ Hit, FX Compensation, Cancel              |
| FX_FORWARD  | RFQ Miss, Roll                                |
| FX_SWAP     | Force Match                                   |
| FX_NDF      | Unmatched                                     |
| FX_OPTION   | Broker Exec, FX Option Hedge                  |
| IRS         | Back-to-Back, Rematch, IRS Clearing, Compress |
| XCCY_SWAP   | Partial Match, Novation                       |
| SWAPTION    | Trade Confirm, Exercise                       |
| FRA         | Sales Direct                                  |
| BOND        | STP Auto, Give-Up, Bond Broker Exec           |
| BOND_FUTURE | Failed STP                                    |
| REPO        | Trader First                                  |
| CDS         | OBO Client                                    |
| TRS         | Allocation                                    |
| EQUITY      | Dispute                                       |

### 3.4 Pure Config vs Service-Required

**Pure Config (foundation only — no service code):**
- #1 RFQ Hit, #2 RFQ Miss
- #7 Sales Direct, #8 Trader First
- #13 Force Match, #14 Rematch
- #22 Cancel, #24 Roll

**Config + Transform Service:**
- Execution: #3 Back-to-Back, #5 Broker Exec, #6 OBO Client
- Post-trade: #9 Give-Up, #17 IRS Clearing, #21 Trade Confirm
- Product-specific: #16 FX Compensation, #18 Bond Broker Exec, #19 FX Option Hedge
- Lifecycle: #23 Novation, #25 Exercise
- Allocation: #20 Allocation
- Recon: #27 EOD, #28 Settlement, #29 Margin, #30 Regulatory
- Recon: #14 EOD positions, #22 Margin, #23 Regulatory
- Aggregation: #12 Fills, #15 Netting, #16 Compression
- Override: #24 Dispute resolution

---

## 4. Workflow Diagrams

### 4.1 Scenario #1 — Sales-First → Trader Confirms

```
SALES DESK                    MATCHING ENGINE                 TRADING DESK
    │                              │                              │
    │  books trade (TRD-001)       │                              │
    ├─────────────────────────────▶│                              │
    │                              │ creates match (MAT-001)      │
    │                              │ LHS = sales booking          │
    │                              │ status = UNMATCHED           │
    │                              │ direction = LHS_FIRST        │
    │                              │                              │
    │                              │  notifies trader             │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │        trader confirms       │
    │                              │◀─────────────────────────────│
    │                              │ RHS = trader booking         │
    │                              │ compare economics            │
    │                              │                              │
    │                              ├── no breaks ──▶ MATCHED      │
    │                              │                              │
    │                              ├── breaks ──▶ PARTIAL         │
    │                              │   (tolerance exceeded)       │
    │                              │                              │
    │   break notification         │                              │
    │◀─────────────────────────────│                              │
```

### 4.2 Scenario #2 — Trader-First → Sales Books

```
TRADING DESK                  MATCHING ENGINE                 SALES DESK
    │                              │                              │
    │  books risk trade            │                              │
    ├─────────────────────────────▶│                              │
    │                              │ creates match (MAT-002)      │
    │                              │ LHS = trader booking         │
    │                              │ status = UNMATCHED           │
    │                              │ direction = LHS_FIRST        │
    │                              │                              │
    │                              │  notifies sales              │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │        sales books           │
    │                              │◀─────────────────────────────│
    │                              │ RHS = sales booking          │
    │                              │ compare economics            │
    │                              │ ──▶ MATCHED / PARTIAL        │
```

### 4.3 Scenario #3 — Simultaneous Booking

```
SALES DESK                    MATCHING ENGINE                 TRADING DESK
    │                              │                              │
    │  books trade                 │          books trade         │
    ├─────────────────────────────▶│◀─────────────────────────────┤
    │                              │                              │
    │                              │ both arrive within window    │
    │                              │ auto-correlate on key fields │
    │                              │ LHS = first received         │
    │                              │ RHS = second received        │
    │                              │ direction = SIMULTANEOUS     │
    │                              │                              │
    │                              │ economics match?             │
    │                              ├── yes ──▶ AUTO-MATCHED       │
    │                              ├── no  ──▶ PARTIAL (breaks)   │
```

### 4.4 Scenario #4 — Block Trade → Allocations

```
SALES DESK                    MATCHING ENGINE                 ALLOC ENGINE
    │                              │                              │
    │  books block (50M)           │                              │
    ├─────────────────────────────▶│                              │
    │                              │ creates match (MAT-004)      │
    │                              │ LHS = block trade            │
    │                              │ match_type = ALLOCATION      │
    │                              │ cardinality = ONE_MANY       │
    │                              │ status = UNMATCHED           │
    │                              │                              │
    │                              │  allocation request          │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │        split 1: ACC-001 20M  │
    │                              │◀─────────────────────────────│
    │                              │ RHS[0] = alloc 1             │
    │                              │ remaining = 30M              │
    │                              │ status = PARTIAL             │
    │                              │                              │
    │                              │        split 2: ACC-002 15M  │
    │                              │◀─────────────────────────────│
    │                              │ RHS[1] = alloc 2             │
    │                              │ remaining = 15M              │
    │                              │                              │
    │                              │        split 3: ACC-003 15M  │
    │                              │◀─────────────────────────────│
    │                              │ RHS[2] = alloc 3             │
    │                              │ remaining = 0                │
    │                              │ status = MATCHED             │
    │                              │                              │
    │  allocation complete (3/3)   │                              │
    │◀─────────────────────────────│                              │
```

### 4.5 Scenario #5 — Force Match

```
OPERATIONS                    MATCHING ENGINE
    │                              │
    │  force match (MAT-005)       │
    ├─────────────────────────────▶│
    │                              │
    │  │ RHS = null (no counterpart)
    │              │ status = FORCED
    │         │ forced_by = ops user
    │                              │ force_reason = "No cpty booking expected"
    │                              │ approval required? (based on rule)
    │                              │
    │  confirm (audit logged)      │
    │◀─────────────────────────────│
```

### 4.6 Scenario #6 — CCP Clearing / Novation

```
OUR DESK                      MATCHING ENGINE                 CCP / CLEARING
    │                              │                              │
    │  trade booked (cpty=BARC)    │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = our trade              │
    │                              │ status = UNMATCHED           │
    │                              │                              │
    │                              │     clearing msg arrives     │
    │                              │◀─────────────────────────────│
    │                              │ RHS = clearing msg           │
    │                              │ RHS.cpty = LCH (novated)     │
    │                              │                              │
    │                              │ economics match?             │
    │                              ├── yes ──▶ MATCHED            │
    │                              │   resolution: NOVATE_CPTY    │
    │                              │   trade.parties updated      │
    │                              │   cpty: BARC → LCH           │
    │                              │                              │
    │  cpty novated notification   │                              │
    │◀─────────────────────────────│                              │
```

### 4.7 Scenario #7 — STP Auto-Book

```
EXTERNAL SYSTEM               MATCHING ENGINE                 OUR SYSTEM
    │                              │                              │
    │  inbound message             │                              │
    │  (FIX / FpML / SWIFT)        │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = inbound msg            │
    │                              │ parse + validate             │
    │                              │ match_type = STP             │
    │                              │                              │
    │                              │  auto-create trade           │
    │                              │─────────────────────────────▶│
    │                              │          │ TRD-STP-001 created
    │                              │ RHS = auto-created trade     │
    │                              │ status = MATCHED             │
    │                              │ resolution: AUTO_BOOK        │
    │                              │                              │
    │                              │  ack sent back               │
    │◀─────────────────────────────│                              │
```

### 4.8 Scenario #8 — On-Behalf-Of (OBO) Client Ticket

```
SALES DESK                    MATCHING ENGINE                 CLIENT
    │                              │                              │
    │  enters trade as OBO         │                              │
    │  (on behalf of client)       │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = sales-entered ticket   │
    │                              │ LHS.party.role = OBO_AGENT   │
    │                              │ status = UNMATCHED           │
    │                              │                              │
    │                              │  client ticket sent          │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │        client affirms        │
    │                              │◀─────────────────────────────│
    │                              │ RHS = client affirmation     │
    │                              │ status = MATCHED             │
    │                              │                              │
    │                              │  OR: client rejects          │
    │                              │◀─────────────────────────────│
    │                              │ RHS = rejection              │
    │                              │ status = DISPUTED            │
    │                              │ break: client disagrees      │
```

### 4.9 Scenario #9 — Counterparty Affirmation (MarkitWire / DTCC)

```
OUR SYSTEM                    MATCHING ENGINE                 MARKITWIRE/DTCC
    │                              │                              │
    │  trade submitted             │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = our trade view         │
    │                              │ status = UNMATCHED           │
    │                              │                              │
    │                              │      affirm msg arrives      │
    │                              │◀─────────────────────────────│
    │                              │ RHS = cpty affirmation       │
    │                              │ compare all economics        │
    │                              │                              │
    │                              ├── match ──▶ CONFIRMED        │
    │                              ├── break ──▶ PARTIAL          │
    │                              │   (notional off by 0.01%)    │
```

### 4.10 Scenario #10 — Give-Up / Take-Up

```
EXECUTING BROKER              MATCHING ENGINE                 PRIME BROKER
    │                              │                              │
    │  gives up trade              │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = exec broker trade      │
    │                              │ status = UNMATCHED           │
    │                              │ scenario = GIVEUP            │
    │                              │                              │
    │                              │  give-up notice to PB        │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │        PB accepts/rejects    │
    │                              │◀─────────────────────────────│
    │                              │ RHS = PB acceptance          │
    │                              │ resolution: TRANSFER_BOOKING │
    │                              │ trade ownership transferred  │
    │                              │ status = MATCHED             │
```

### 4.11 Scenario #11 — Back-to-Back

```
CLIENT-FACING BOOK            MATCHING ENGINE                 RISK/HEDGE BOOK
    │                              │                             │
    │  client trade booked         │                             │
    ├─────────────────────────────▶│                             │
    │                              │ LHS = client-facing trade   │
    │                              │ scenario = BACK_TO_BACK     │
    │                              │                             │
    │                              │  create mirror trade        │
    │                              │─────────────────────────────▶│
    │                              │         │ hedge trade created
    │                              │ RHS = hedge trade            │ (opposite direction)
    │                              │ status = MATCHED            │
    │                              │ linked: TRD-C001 ↔ TRD-H001 │
```

### 4.12 Scenario #17 — RFQ → Quote → Accept

```
CLIENT                        MATCHING ENGINE                 PRICING DESK
    │                              │                             │
    │  RFQ: buy 50M 5Y IRS        │                              │
    ├─────────────────────────────▶│                             │
    │                              │ LHS = client RFQ            │
    │                              │ match_type = RFQ            │
    │                              │ status = RFQ_OPEN           │
    │                              │                             │
    │                              │  RFQ forwarded              │
    │                              │─────────────────────────────▶│
    │                              │                             │
    │                              │        quote: 4.25%         │
    │                              │◀─────────────────────────────│
    │                              │ RHS = quote response        │
    │                              │ status = QUOTED             │
    │                              │ valid_until = +30s          │
    │                              │                             │
    │  quote sent to client        │                             │
    │◀─────────────────────────────│                             │
    │                              │                             │
    │  client accepts              │                             │
    ├─────────────────────────────▶│                             │
    │                              │ status = ACCEPTED           │
    │                              │ resolution: CREATE_TRADE    │
    │                              │ TRD-RFQ-001 created         │
    │                              │                             │
    │                              │  OR: expired (30s elapsed)  │
    │                              │ status = EXPIRED            │
```

### 4.13 Scenario #18 — Order → Partial Fills

```
OUR DESK                      MATCHING ENGINE                 VENUE / EXCHANGE
    │                              │                             │
    │  order: buy 50M EURUSD       │                             │
    │  limit 1.0900                │                             │
    ├─────────────────────────────▶│                             │
    │                              │ LHS = order                 │
    │                              │ match_type = ALLOCATION     │
    │                              │ cardinality = ONE_MANY      │
    │                              │ status = OPEN               │
    │                              │                             │
    │                              │     fill 1: 10M @ 1.0850    │
    │                              │◀─────────────────────────────│
    │                              │ RHS[0] = fill 1             │
    │                              │ filled: 10/50M              │
    │                              │ status = PARTIAL            │
    │                              │                             │
    │                              │     fill 2: 15M @ 1.0860    │
    │                              │◀─────────────────────────────│
    │                              │ filled: 25/50M              │
    │                              │                             │
    │                              │     fill 3: 25M @ 1.0840    │
    │                              │◀─────────────────────────────│
    │                              │ filled: 50/50M              │
    │                              │ status = FILLED             │
    │                              │ VWAP = 1.08492              │
    │                              │ resolution: CREATE_TRADE    │
    │                              │                             │
    │  order filled notification   │                             │
    │◀─────────────────────────────│                             │
```

### 4.14 Scenario #19 — Broker Executes On Our Behalf

```
OUR DESK                      MATCHING ENGINE                 BROKER (ICAP/TP)
    │                              │                             │
    │  order to broker:            │                             │
    │  "buy 50M EURUSD ≤1.09"     │                              │
    ├─────────────────────────────▶│                             │
    │                              │ LHS = our order instruction │
    │                              │ match_type = CORRELATION    │
    │                              │ scenario = BROKER_EXEC      │
    │                              │ status = UNMATCHED          │
    │                              │                             │
    │                              │     broker fill arrives     │
    │                              │◀─────────────────────────────│
    │                              │ RHS = broker fill msg       │
    │                              │                             │
    │                              │ RECON:                      │
    │                              │   price within limit? ✓     │
    │                              │   qty matches? ✓            │
    │                              │   commission correct? ✓     │
    │                              │   venue = EBS ✓             │
    │                              │                             │
    │                              ├── all pass ──▶ RECONCILED   │
    │                              │   resolution: AUTO_BOOK     │
    │                              ├── break ──▶ BREAK           │
    │                              │   (best execution concern)  │
    │                              │                             │
    │  trade booked / break alert  │                             │
    │◀─────────────────────────────│                             │
```

### 4.15 Scenario #15 — Netting

```
NETTING ENGINE                MATCHING ENGINE
    │                              │
    │  group trades:               │
    │  TRD-001: pay 10M USD→EUR    │
    │  TRD-002: pay 5M USD→EUR     │
    │  TRD-003: rcv 8M USD→EUR     │
    ├─────────────────────────────▶│
    │                              │
    │                              │ LHS = [TRD-001, TRD-002, TRD-003]
    │     │ match_type = AGGREGATION
    │       │ cardinality = MANY_ONE
    │                              │
    │          │ net: pay 7M USD→EUR
    │       │ RHS = 1 net settlement
    │             │ status = MATCHED
    │                              │ resolution: CREATE_NET_SETTLEMENT
```

### 4.16 Scenario #20 — Settlement Matching

```
OUR OPS                       MATCHING ENGINE                 CPTY OPS
    │                              │                              │
    │  payment instruction:        │                              │
    │  pay 10M USD to BARC         │                              │
    │  value date: 2026-03-10      │                              │
    ├─────────────────────────────▶│                              │
    │                              │ LHS = our SSI                │
    │                              │ status = UNMATCHED           │
    │                              │                              │
    │                              │     cpty payment instr       │
    │                              │◀─────────────────────────────│
    │                              │ RHS = cpty SSI               │
    │                              │                              │
    │                              │ RECON:                       │
    │                              │   amount matches? ✓          │
    │                              │   value date? ✓              │
    │                              │   SSI details? ✓             │
    │                              │   currency? ✓                │
    │                              │                              │
    │                              ├── match ──▶ MATCHED          │
    │                              │   ready for settlement       │
    │                              ├── break ──▶ SSI BREAK        │
```

### 4.17 Scenario #22 — Margin / Collateral Reconciliation

```
OUR MARGIN DESK               MATCHING ENGINE                 CPTY / CCP
    │                              │                             │
    │  our margin call:            │                             │
    │  VM = $2.3M, IA = $500K     │                              │
    ├─────────────────────────────▶│                             │
    │                              │ LHS = our margin calc       │
    │                              │                             │
    │                              │     cpty margin call        │
    │                              │◀─────────────────────────────│
    │                              │ RHS = cpty margin calc      │
    │                              │ RHS.VM = $2.35M             │
    │                              │                             │
    │                              │ RECON:                      │
    │                              │   VM diff = $50K (>threshold)│
    │                              │   status = BREAK            │
    │                              │   action: DISPUTE           │
```

### 4.18 Scenario #24 — Dispute Resolution

```
OUR DESK                      MATCHING ENGINE                 CPTY
    │                              │                             │
    │  existing match has break    │                             │
    │  MAT-024 status = PARTIAL    │                             │
    │                              │                             │
    │  escalate to DISPUTED        │                             │
    ├─────────────────────────────▶│                             │
    │                              │ status = DISPUTED           │
    │                              │ dispute_reason = "Notional" │
    │                              │                             │
    │                              │  dispute notification       │
    │                              │─────────────────────────────▶│
    │                              │                             │
    │                              │     cpty responds:          │
    │                              │     "agree to our value"    │
    │                              │◀─────────────────────────────│
    │                              │                             │
    │                              │ resolution: ACCEPT_LHS      │
    │                              │ OR: ACCEPT_RHS              │
    │                              │ OR: SPLIT_DIFFERENCE        │
    │                              │ status = RESOLVED           │
    │                              │ amendment created if needed │
```

---

## 5. Data Model — Unified Event Architecture

### 5.0 Design Principle: Events, Not Tables

**Old model** (trade-centric, satellite tables):
```
trades ←── legs ←── schedules
  ↑          ↑
  │          └── measures
  ├── matches (separate table)
  ├── allocations (separate table)
  ├── amendments (separate table)
  └── orders (would be yet another table)
```

**New model** (event-centric, one primary table):
```
┌─────────────────────────────────────────────────────────────────────┐
│                        EVENTS (one table)                           │
│                                                                     │
│  Every business action is an Event record.                          │
│  event_type determines the nested payload structure.                │
│  Events get linked, correlated, enriched, transitioned.             │
│  A "trade" is what emerges when correlated events converge.         │
│                                                                     │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ RFQ     │ │ SALES    │ │ TRADING  │ │ CLEARING │ │ SETTLE   │    │
│  │ event   │ │ BOOKING  │ │ BOOKING  │ │ MSG      │ │ INSTR    │    │
│  │         │ │ event    │ │ event    │ │ event    │ │ event    │    │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘    │
│       │           │            │            │            │          │
│       └─────┬─────┴──────┬─────┘            │            │          │
│             │ CORRELATE  │                  │            │          │
│             ▼            ▼                  ▼            ▼          │
│       ┌──────────────────────────────────────────────────────┐      │
│       │              LINKED EVENT CHAIN                       │     │
│       │  EVT-001 → EVT-002 → EVT-003 → EVT-007 → EVT-012   │        │
│       │  (rfq)    (quote)   (accept)  (clearing) (settled)   │      │
│       └──────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.1 The Event Record

One schema. One dataset. The `event_type` drives the nested `payload` structure.

```yaml
# schemas/event.yaml
blueprint: schema
kind: Event
xid: event_id|event_type
xns: [id, xid]
description: "Universal event record — all business actions flow through here"
icon: zap
extends: _system.yaml
operation: MERGE

model:
  fields:
    # ── Identity ──
    event_id:      { type: str, key: true, rank: hero }
    event_type:    { type: str, required: true, facet: true, enum: $enums.ENUM_EVENT_TYPE }
    status:        { type: str, facet: true, enum: $enums.ENUM_EVENT_STATUS, default: ACTIVE }
    version:       { type: int, default: 1 }

    # ── Source ──
    source:        { type: str, facet: true, enum: $enums.ENUM_SOURCE_TYPE }
    source_ref:    { type: str, description: "External reference ID from source system" }
    protocol:      { type: str, facet: true, enum: $enums.ENUM_PROTOCOL, description: "Wire protocol (FIX, FpML, SWIFT, REST, INTERNAL)" }
    actor:         { type: str, description: "Who created this event (user, system, service)" }
    desk:          { type: str, facet: true, description: "Trading desk / function" }

    # ══════════════════════════════════════════════════════════════
    # THREE-LAYER PAYLOAD MODEL
    # ══════════════════════════════════════════════════════════════
    #
    # Layer 1: raw{}      — source-native message, immutable after capture
    # Layer 2: payload{}  — canonical transform, what the matching engine reads
    # Layer 3: enriched{} — post-match additions (risk, regulatory, settlement)
    #
    # Flow: source → raw{} → transformer → payload{} → engine → enriched{}
    # ══════════════════════════════════════════════════════════════

    # ── Layer 1: Raw (source-native, immutable) ──
    raw:
      type: dict
      description: "Original message as received — never mutated after capture"
      items:
        format:      { type: str, enum: $enums.ENUM_RAW_FORMAT, description: "FIX, FPML, SWIFT_MT, SWIFT_MX, JSON, CSV, INTERNAL" }
        version:     { type: str, description: "Protocol version (e.g., FIX 4.4, FpML 5.12, MT300)" }
        content:     { type: dict, description: "Parsed source-native payload (or string for unparseable)" }
        raw_text:    { type: str, description: "Original wire text (FIX tags, XML, SWIFT block)" }
        received_at: { type: str, widget: datetime }
        checksum:    { type: str, description: "SHA-256 of raw_text for tamper detection" }
        source_msg_id: { type: str, description: "Message ID from source system" }

    # ── Layer 2: Payload (canonical transform) ──
    # Structure determined by event_type (see 5.2)
    # Transformer per (source, protocol, event_type, product_type) produces this
    payload:
      type: dict
      required: true
      description: "Canonical event-type-specific data — matching engine reads ONLY this"

    # ── Layer 3: Enriched (post-match additions) ──
    enriched:
      type: dict
      description: "Post-processing additions — never present at capture time"
      items:
        risk_flags:     { type: list, description: "Risk alerts (LARGE_NOTIONAL, CONCENTRATION, etc.)" }
        regulatory:     { type: dict, description: "{ uti, usi, lei, reporting_status, jurisdiction }" }
        settlement:     { type: dict, description: "{ ssi_id, nostro, value_date, settlement_status }" }
        pricing:        { type: dict, description: "{ mid_price, spread, markup_bps, benchmark }" }
        compliance:     { type: dict, description: "{ approved_by, limit_check, wash_trade_flag }" }
        enriched_at:    { type: str, widget: datetime }
        enriched_by:    { type: str, description: "Service/user that added enrichment" }

    # ── Economics (denormalized for blotter display) ──
    product_type:  { type: str, facet: true, enum: $enums.ENUM_PRODUCT_TYPE }
    notional:      { type: float }
    currency:      { type: str, enum: $enums.ENUM_CURRENCY }
    cpty_id:       { type: str, fk: entities, fk_label: name }

    # ── Linking ──
    links:
      type: list
      description: "References to related events"
      items:
        type: dict
        items:
          event_id:   { type: str, description: "Linked event ID" }
          rel:        { type: str, enum: $enums.ENUM_LINK_TYPE }
          role:       { type: str, description: "Role in the relationship (LHS, RHS, PARENT, CHILD)" }

    # ── Correlation / Matching ──
    correlation:
      type: dict
      description: "Matching engine metadata (populated when events get correlated)"
      items:
        match_type:   { type: str, enum: $enums.ENUM_MATCH_TYPE }
        scenario:     { type: str, enum: $enums.ENUM_MATCH_SCENARIO }
        match_status: { type: str, enum: $enums.ENUM_MATCH_STATUS }
        cardinality:  { type: str, enum: $enums.ENUM_CARDINALITY }
        direction:    { type: str, enum: $enums.ENUM_MATCH_DIRECTION }
        breaks:       { type: list, description: "Field-level breaks" }
        resolution:   { type: dict, description: "{ action, service, params, executed_at }" }
        matched_at:   { type: str, widget: datetime }
        matched_by:   { type: str }

    # ── Lifecycle Trail ──
    transitions:
      type: list
      description: "Append-only log of every state change"
      items:
        type: dict
        items:
          from_status:  { type: str }
          to_status:    { type: str }
          at:           { type: str, widget: datetime }
          by:           { type: str }
          reason:       { type: str }
          diff:         { type: dict, description: "Fields that changed in this transition" }

    # ── Timestamps ──
    created_at:    { type: str, widget: datetime }
    updated_at:    { type: str, widget: datetime }
    sla_deadline:  { type: str, widget: datetime }
    priority:      { type: str, enum: $enums.ENUM_PRIORITY }
```

### 5.2 Three-Layer Payload Model

Every event carries three payload layers representing its lifecycle:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EVENT PAYLOAD LIFECYCLE                              │
│                                                                         │
│  SOURCE SYSTEM           INGESTION            MATCHING          POST    │
│  (Bloomberg,             GATEWAY              ENGINE            MATCH   │
│   Tradeweb,                                                             │
│   FIX, etc.)                                                            │
│       │                     │                    │                │     │
│       │   wire message      │                    │                │     │
│       ├────────────────────▶│                    │                │     │
│       │                     │                    │                │     │
│       │              ┌──────┴──────┐             │                │     │
│       │              │  LAYER 1    │             │                │     │
│       │              │  raw{}      │             │                │     │
│       │              │  immutable  │             │                │     │
│       │              │  source-    │             │                │     │
│       │              │  native     │             │                │     │
│       │              └──────┬──────┘             │                │     │
│       │                     │ transformer        │                │     │
│       │                     │ (source, protocol,  │                │    │
│       │                     │  event_type,        │                │    │
│       │                     │  product_type)      │                │    │
│       │              ┌──────┴──────┐             │                │     │
│       │              │  LAYER 2    │─────────────▶                │     │
│       │              │  payload{}  │  canonical   │                │    │
│       │              │  canonical  │  fields      │                │    │
│       │              │  normalized │             │                │     │
│       │              └─────────────┘      ┌──────┴──────┐        │      │
│       │                                   │  LAYER 3    │◀───────│      │
│       │                                   │  enriched{} │  risk, │      │
│       │                                   │  post-match │  reg,  │      │
│       │                                   │  additions  │  settle│      │
│       │                                   └─────────────┘        │      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Layer 1: `raw{}` — Source-Native (Immutable)

Captured at ingestion, never mutated. Stores the original message for audit,
replay, and debugging. The `format` + `version` fields identify the schema
used for `content`.

```yaml
raw:
  format:        FIX | FPML | SWIFT_MT | SWIFT_MX | JSON | CSV | INTERNAL
  version:       "4.4" | "5.12" | "MT300" | "2.0"
  content:       { ... }     # Parsed source-native structure
  raw_text:      "8=FIX.4.4|9=..."   # Original wire bytes
  received_at:   "2026-03-08T09:01:00Z"
  checksum:      "sha256:abc..."
  source_msg_id: "MW-20260308-12345"
```

Source format schemas live in `_source_formats/{source}/{message_type}.yaml`:

```
schemas/_source_formats/
├── fix/
│   ├── execution_report.yaml        # Tag 35=8 (fills, broker confirms)
│   ├── new_order_single.yaml        # Tag 35=D (order submission)
│   ├── order_cancel_replace.yaml    # Tag 35=G (order amendment)
│   ├── allocation_instruction.yaml  # Tag 35=J (block alloc)
│   └── trade_capture_report.yaml    # Tag 35=AE (post-trade)
│
├── fpml/
│   ├── fx_single_leg.yaml           # FX spot/forward
│   ├── fx_option.yaml               # FX vanilla option
│   ├── irs.yaml                     # Interest rate swap
│   ├── fra.yaml                     # Forward rate agreement
│   ├── bond.yaml                    # Fixed income bond
│   └── credit_default_swap.yaml     # CDS
│
├── swift/
│   ├── mt300.yaml                   # FX confirmation
│   ├── mt320.yaml                   # Fixed loan/deposit
│   ├── mt340.yaml                   # FRA confirmation
│   ├── mt360.yaml                   # IRS confirmation
│   ├── mt502.yaml                   # Order instruction
│   ├── mt515.yaml                   # Client confirmation
│   ├── mt535.yaml                   # Statement of holdings
│   ├── mt536.yaml                   # Statement of transactions
│   └── mt940.yaml                   # Cash statement
│
├── markitwire/
│   ├── trade_affirm.yaml            # Trade affirmation
│   ├── trade_confirm.yaml           # Trade confirmation
│   └── amendment_notice.yaml        # Amendment notification
│
├── dtcc/
│   ├── tiw_trade.yaml               # TIW trade capture
│   ├── gtr_report.yaml              # GTR regulatory report
│   └── settlement_instr.yaml        # Settlement instruction
│
├── bloomberg/
│   ├── toms_trade.yaml              # TOMS trade entry
│   ├── vcon_confirm.yaml            # VCON confirmation
│   └── fxgo_rfq.yaml               # FXGO RFQ
│
├── tradeweb/
│   ├── rfq.yaml                     # RFQ submission
│   ├── quote.yaml                   # Quote response
│   ├── trade_report.yaml            # Trade report
│   └── compression_proposal.yaml    # Compression cycle
│
├── lch/
│   ├── clearing_confirm.yaml        # Clearing confirmation
│   ├── novation_notice.yaml         # Novation notification
│   └── margin_call.yaml             # Margin/collateral call
│
├── cme/
│   ├── clearing_confirm.yaml        # Clearing confirmation
│   └── margin_call.yaml             # Margin call
│
├── ice/
│   ├── clearing_confirm.yaml        # Clearing confirmation
│   └── margin_call.yaml             # Margin call
│
└── internal/
    ├── manual_booking.yaml          # Manual desk entry
    ├── ops_override.yaml            # Operations override
    └── system_generated.yaml        # Engine-generated events
```

#### Layer 2: `payload{}` — Canonical (Normalized)

The transformer maps `raw.content` → `payload` using the
`(source, protocol, event_type, product_type)` tuple. The matching engine
reads ONLY this layer — it never touches `raw{}`.

```
┌──────────────────────────────────────────────────────────────────────┐
│  event_type          │ canonical payload structure                  │
├──────────────────────┼──────────────────────────────────────────────┤
│                      │                                              │
│  RFQ                 │ { direction, product_type, notional,         │
│                      │   currency, limit_price, valid_until,        │
│                      │   client_entity_id }                         │
│                      │                                              │
│  QUOTE               │ { rfq_event_id, price, spread, valid_until,  │
│                      │   quoted_by }                                │
│                      │                                              │
│  ORDER               │ { order_type (LIMIT/MARKET/IOI), direction,  │
│                      │   product_type, notional, currency,          │
│                      │   limit_price, broker_entity_id,             │
│                      │   fills: [{ qty, price, venue, at }],        │
│                      │   vwap, filled_qty }                         │
│                      │                                              │
│  SALES_BOOKING       │ { trade_economics, book_id, portfolio,       │
│                      │   strategy, parties, legs: [...] }           │
│                      │                                              │
│  TRADING_BOOKING     │ { trade_economics, book_id, portfolio,       │
│                      │   strategy, parties, legs: [...] }           │
│                      │                                              │
│  STP_MESSAGE         │ { parsed_economics, sender, receiver }       │
│                      │                                              │
│  OBO_TICKET          │ { client_entity_id, trade_economics,         │
│                      │   on_behalf_of, ticket_ref }                 │
│                      │                                              │
│  BROKER_FILL         │ { broker_entity_id, exec_id, price, qty,     │
│                      │   venue, commission, commission_bps }        │
│                      │                                              │
│  CLEARING_MSG        │ { ccp, clearing_id, original_cpty,           │
│                      │   novated_cpty, economics }                  │
│                      │                                              │
│  AFFIRM_MSG          │ { platform, affirm_id,                       │
│                      │   affirmed_economics, cpty_entity_id }       │
│                      │                                              │
│  GIVEUP_NOTICE       │ { executing_broker, prime_broker,            │
│                      │   trade_economics, giveup_ref }              │
│                      │                                              │
│  ALLOC_SPLIT         │ { block_event_id, account, entity_id,        │
│                      │   quantity, book_id, split_num, total_splits }│
│                      │                                              │
│  SETTLEMENT_INSTR    │ { payment_direction, amount, currency,       │
│                      │   value_date, ssi_id, nostro, cpty_ssi }     │
│                      │                                              │
│  MARGIN_CALL         │ { vm_amount, ia_amount, currency,            │
│                      │   calculation_date, cpty_entity_id }         │
│                      │                                              │
│  AMENDMENT           │ { target_event_id, amendment_type,           │
│                      │   changes: [{ field, old, new, reason }],    │
│                      │   approvals: [{ role, approver, status }] }  │
│                      │                                              │
│  POSITION_SNAPSHOT   │ { book_id, as_of_date, positions: [...],     │
│                      │   source (OUR_BOOK/CPTY_STATEMENT) }         │
│                      │                                              │
│  NET_SETTLEMENT      │ { trade_event_ids: [...], net_amount,        │
│                      │   currency, value_date, cpty_entity_id }     │
│                      │                                              │
│  TRADE               │ { trade_id, fpml_type, trade_date,           │
│                      │   parties, ned, legs, uti, usi }             │
│                      │   ** MATERIALIZED — created by engine **     │
│                      │                                              │
│  RISK_MEASURE        │ { trade_event_id, leg_event_id, metric,      │
│                      │   value, denomination, tenor_bucket,         │
│                      │   curve, as_of_date }                        │
│                      │                                              │
│  SCHEDULE_EVENT      │ { trade_event_id, leg_id, event_subtype      │
│                      │   (PAYMENT/RESET/FIXING/COUPON/MATURITY),    │
│                      │   date, amount, index, fixing_source }       │
│                      │                                              │
└──────────────────────┴──────────────────────────────────────────────┘
```

#### Layer 3: `enriched{}` — Post-Match Additions

Populated AFTER the matching engine processes the event. Never present at
capture time. Added by downstream services (risk, regulatory, settlement).

```yaml
enriched:
  risk_flags:     [LARGE_NOTIONAL, CONCENTRATION_RISK, NEW_COUNTERPARTY]
  regulatory:
    uti: "UTI202603081234..."
    usi: "USI202603081234..."
    lei: "529900T8BM49AURSDO55"
    jurisdiction: [CFTC, EMIR]
    reporting_status: REPORTED
    reported_at: "2026-03-08T10:00:00Z"
  settlement:
    ssi_id: "SSI-USD-JPMC-001"
    nostro: "JPMC-NY"
    value_date: "2026-03-10"
    settlement_status: PENDING
  pricing:
    mid_price: 1.0852
    spread: 0.0003
    markup_bps: 3.0
    benchmark: "WMR 4PM Fix"
  compliance:
    approved_by: "J.Chen"
    limit_check: PASSED
    wash_trade_flag: false
    best_execution: VERIFIED
  enriched_at: "2026-03-08T09:05:00Z"
  enriched_by: "risk-engine-v2"
```

#### Source × Event Type Transformer Matrix

The transformer registry maps `(source, protocol, event_type)` → transform function.
Each transformer knows how to extract canonical payload fields from source-native formats.

```
┌───────────────┬──────────┬───────────────────┬─────────────────────────────┐
│ Source         │ Protocol │ Event Type        │ Transformer                │
├───────────────┼──────────┼───────────────────┼─────────────────────────────┤
│ BLOOMBERG     │ FIX      │ BROKER_FILL       │ fix_exec_report_to_fill     │
│ BLOOMBERG     │ JSON     │ RFQ               │ fxgo_rfq_to_rfq             │
│ BLOOMBERG     │ JSON     │ QUOTE             │ fxgo_quote_to_quote         │
│ TRADEWEB      │ REST     │ RFQ               │ tw_rfq_to_rfq               │
│ TRADEWEB      │ REST     │ QUOTE             │ tw_quote_to_quote           │
│ TRADEWEB      │ REST     │ TRADE             │ tw_trade_to_trade           │
│ MARKITWIRE    │ FPML     │ AFFIRM_MSG        │ mw_affirm_to_affirm         │
│ MARKITWIRE    │ FPML     │ AMENDMENT         │ mw_amendment_to_amendment   │
│ DTCC          │ FPML     │ AFFIRM_MSG        │ dtcc_affirm_to_affirm       │
│ DTCC          │ JSON     │ SETTLEMENT_INSTR  │ dtcc_settle_to_settle       │
│ LCH           │ FPML     │ CLEARING_MSG      │ lch_clearing_to_clearing    │
│ LCH           │ FPML     │ MARGIN_CALL       │ lch_margin_to_margin        │
│ CME           │ FIX      │ CLEARING_MSG      │ cme_clearing_to_clearing    │
│ CME           │ FIX      │ MARGIN_CALL       │ cme_margin_to_margin        │
│ ICE           │ FIX      │ CLEARING_MSG      │ ice_clearing_to_clearing    │
│ BROKER        │ FIX      │ BROKER_FILL       │ fix_exec_report_to_fill     │
│ BROKER        │ FIX      │ GIVEUP_NOTICE     │ fix_giveup_to_giveup        │
│ STP_PIPELINE  │ FIX      │ STP_MESSAGE       │ fix_trade_capture_to_stp    │
│ STP_PIPELINE  │ FPML     │ STP_MESSAGE       │ fpml_trade_to_stp           │
│ STP_PIPELINE  │ SWIFT_MT │ STP_MESSAGE       │ swift_mt_to_stp             │
│ CLIENT        │ REST     │ RFQ               │ client_rfq_to_rfq           │
│ CLIENT        │ REST     │ OBO_TICKET        │ client_obo_to_obo           │
│ MANUAL        │ INTERNAL │ *                 │ passthrough (no transform)  │
│ MATCHING_ENG  │ INTERNAL │ TRADE             │ passthrough (materialized)  │
│ NETTING_ENG   │ INTERNAL │ NET_SETTLEMENT    │ passthrough (computed)      │
└───────────────┴──────────┴───────────────────┴─────────────────────────────┘
```

#### Product-Specific Format Variations

Within the same `(source, protocol)` pair, the payload structure can vary by
product type. The transformer handles this via sub-mappers:

```python
def fix_exec_report_to_fill(raw):
    if product_type == "FX":
        # FIX: Tag 15=CCY1, 120=CCY2, Tag 31=LastPx (rate)
        return { "price": rate, "qty": notional, "venue": tag_30 }
    elif product_type == "IRS":
        # FIX: custom tags for fixed_rate, float_index, tenor
        return { "price": fixed_rate, "qty": notional, "venue": tag_30 }
    elif product_type == "BOND":
        # FIX: Tag 31=LastPx (clean price), Tag 6=AvgPx, Tag 381=GrossAmt
        return { "price": clean_price, "qty": face_value, "venue": tag_30,
                 "accrued": computed }

def fpml_trade_to_stp(raw):
    if raw["content"]["tag"] == "fxSingleLeg":
        # Map FpML exchangedCurrency1/2 to canonical legs
        ...
    elif raw["content"]["tag"] == "swap":
        # Map FpML swapStream[0]/[1] to canonical fixed/float legs
        ...
```

#### Example: Full Three-Layer Event

```yaml
# FX Forward trade confirmed via MarkitWire affirmation
event_id: EVT-AFFIRM-042
event_type: AFFIRM_MSG
source: MARKITWIRE
protocol: FPML
status: MATCHED

# Layer 1: Raw — MarkitWire FpML as received
raw:
  format: FPML
  version: "5.12"
  content:
    messageId: "MW-20260308-98765"
    header:
      messageType: tradeAffirmation
      sentBy: "MARKITWIRE"
      sendTo: "OURBANK"
      creationTimestamp: "2026-03-08T09:15:00Z"
    trade:
      tradeHeader:
        partyTradeIdentifier:
          - { partyReference: party1, tradeId: "MW-TRD-42" }
          - { partyReference: party2, tradeId: "TRD-FX-042" }
      fxSingleLeg:
        exchangedCurrency1:
          payerPartyReference: party1
          paymentAmount: { currency: USD, amount: 10000000 }
        exchangedCurrency2:
          payerPartyReference: party2
          paymentAmount: { currency: EUR, amount: 9215000 }
        valueDate: "2026-03-10"
        exchangeRate:
          quotedCurrencyPair: { currency1: EUR, currency2: USD, quoteBasis: Currency2PerCurrency1 }
          rate: 1.0852
    party:
      - { id: party1, partyId: "LEI:529900T8BM49AURSDO55", partyName: "HSBC" }
      - { id: party2, partyId: "LEI:OURBANKLEIDENTIFIER00", partyName: "Our Bank" }
  raw_text: "<FpML xmlns='http://www.fpml.org/FpML-5/confirmation'>..."
  received_at: "2026-03-08T09:15:00Z"
  checksum: "sha256:a1b2c3d4..."
  source_msg_id: "MW-20260308-98765"

# Layer 2: Payload — canonical, what the matching engine reads
payload:
  platform: MARKITWIRE
  affirm_id: "MW-TRD-42"
  cpty_entity_id: "ENT-HSBC-001"
  affirmed_economics:
    product_type: FX
    direction: BUY
    ccy_pair: EURUSD
    notional: 10000000
    currency: USD
    rate: 1.0852
    value_date: "2026-03-10"
    far_leg: null

# Layer 3: Enriched — added post-match by downstream services
enriched:
  regulatory:
    uti: "UTI1085220260308HSBC42"
    jurisdiction: [EMIR]
    reporting_status: PENDING
  settlement:
    ssi_id: "SSI-USD-JPMC-001"
    nostro: "JPMC-NY"
    value_date: "2026-03-10"
    settlement_status: PENDING
  compliance:
    limit_check: PASSED
    best_execution: VERIFIED
  enriched_at: "2026-03-08T09:16:00Z"
  enriched_by: "post-trade-enrichment-svc"
```

### 5.3 How Events Link — The Chain Model

Events don't exist in isolation. They form chains via the `links[]` array.
Each link has a `rel` (relationship type) and a `role` (LHS/RHS/PARENT/CHILD).

```
Example: Full lifecycle of an FX Forward trade

EVT-001 (RFQ)
  │ links: []
  │ status: ACCEPTED
  │
  ├── EVT-002 (QUOTE)
  │     links: [{ event_id: EVT-001, rel: RESPONDS_TO, role: RHS }]
  │     status: ACCEPTED
  │
  ├── EVT-003 (SALES_BOOKING)
  │     links: [{ event_id: EVT-001, rel: ORIGINATES_FROM, role: LHS }]
  │     correlation: { scenario: SALES_TRADER, match_status: MATCHED }
  │     status: MATCHED
  │
  ├── EVT-004 (TRADING_BOOKING)
  │     links: [{ event_id: EVT-003, rel: CORRELATES_WITH, role: RHS }]
  │     correlation: { scenario: SALES_TRADER, match_status: MATCHED }
  │     status: MATCHED
  │
  ├── EVT-005 (TRADE)  ← materialized trade record
  │     links: [
  │       { event_id: EVT-003, rel: CREATED_FROM, role: LHS },
  │       { event_id: EVT-004, rel: CREATED_FROM, role: RHS },
  │       { event_id: EVT-001, rel: ORIGINATES_FROM, role: PARENT }
  │     ]
  │     payload: { trade_id: TRD-003, fpml_type: FPML-FX-FWD, ... }
  │     status: CONFIRMED
  │
  ├── EVT-006 (ALLOC_SPLIT)
  │     links: [{ event_id: EVT-005, rel: CHILD_OF, role: CHILD }]
  │     payload: { block_event_id: EVT-005, account: ACC-101, qty: 10M }
  │
  ├── EVT-007 (ALLOC_SPLIT)
  │     links: [{ event_id: EVT-005, rel: CHILD_OF, role: CHILD }]
  │     payload: { block_event_id: EVT-005, account: ACC-205, qty: 15M }
  │
  ├── EVT-008 (CLEARING_MSG)
  │     links: [{ event_id: EVT-005, rel: CORRELATES_WITH, role: RHS }]
  │     payload: { ccp: LCH, original_cpty: HSBC, novated_cpty: LCH }
  │     correlation: { scenario: CLEARING, match_status: MATCHED }
  │
  ├── EVT-009 (AMENDMENT)
  │     links: [{ event_id: EVT-005, rel: AMENDS, role: CHILD }]
  │     payload: { changes: [{ field: book_id, old: BK-01, new: BK-02 }] }
  │
  ├── EVT-010 (SETTLEMENT_INSTR)
  │     links: [{ event_id: EVT-005, rel: SETTLES, role: LHS }]
  │     correlation: { scenario: SETTLEMENT, match_status: MATCHED }
  │
  └── EVT-011 (RISK_MEASURE)
        links: [{ event_id: EVT-005, rel: MEASURES, role: CHILD }]
        payload: { metric: MTM, value: +34200, as_of_date: 2026-03-08 }
```

#### Link Relationship Types

```yaml
ENUM_LINK_TYPE:
  # Correlation
  - CORRELATES_WITH    # LHS ↔ RHS matching
  - RESPONDS_TO        # Quote responds to RFQ
  - ORIGINATES_FROM    # Booking originates from RFQ/order
  # Hierarchy
  - PARENT_OF          # Block trade → allocations
  - CHILD_OF           # Allocation → block trade
  - CREATED_FROM       # Trade created from correlated events
  # Lifecycle
  - AMENDS             # Amendment → target event
  - SUPERSEDES         # New version supersedes old
  - CANCELS            # Cancellation event
  # Settlement
  - SETTLES            # Settlement instruction for trade
  - NETS_WITH          # Netting group member
  # Risk
  - MEASURES           # Risk measure for trade/leg
  - SCHEDULES          # Cashflow schedule for trade/leg
```

### 5.4 Transitions — Built-In Revision Control

Every event carries its own `transitions[]` array — an append-only log of
every state change with a field-level diff. This IS the revision history.
No separate amendment table needed.

```
EVT-005 (TRADE) transitions:                                                                     
┌────┬──────────────┬──────────────┬─────────────────┬──────────┬───────────────────────────────┐
│ #  │ from         │ to           │ at              │ by       │ diff                          │
├────┼──────────────┼──────────────┼─────────────────┼──────────┼───────────────────────────────┤
│ 1  │ —            │ PENDING      │ 09:01           │ M.Jones  │ { initial creation }          │
│ 2  │ PENDING      │ CONFIRMED    │ 09:02           │ engine   │ { match_status: → MATCHED }   │
│ 3  │ CONFIRMED    │ CONFIRMED    │ 09:30           │ alloc    │ { alloc: 3/3 complete }       │
│ 4  │ CONFIRMED    │ CLEARED      │ 10:00           │ LCH      │ { cpty: HSBC→LCH, clearing: + }│
│ 5  │ CLEARED      │ CLEARED      │ 11:00           │ A.Chen   │ { book_id: BK-01→BK-02 }      │
│ 6  │ CLEARED      │ SETTLED      │ Mar-10 14:00    │ ops      │ { settlement confirmed }      │
└────┴──────────────┴──────────────┴─────────────────┴──────────┴───────────────────────────────┘
                                                                                                 
The diff dict at each transition is what powers the Revision Diff View (Section 6.7).            
Click pill → find transition # → render diff.                                                    
```

### 5.5 Revised Dataset Layout

**Before** (12 schemas, 10 datasets):
```
entities, books, fpmls, trades, legs, schedules,
matches, allocations, amendments, measures
+ proposed: orders, match_events (14 total)
```

**After** (unified event + reference data):
```
┌─────────────────────────────────────────────────────────────────────┐
│  DATASETS                                                           │
│                                                                     │
│  REFERENCE DATA (keep as-is — these are static config, not events)  │
│  ├── entities    — legal entities, CCPs, brokers                    │
│  ├── books       — trading books / portfolios                       │
│  └── fpmls       — FpML product templates                           │
│                                                                     │
│  EVENT DATA (one table, polymorphic)                                │
│  └── events      — ALL business actions (see event_type enum)       │
│       event_type drives payload structure:                          │
│       RFQ, QUOTE, ORDER, SALES_BOOKING, TRADING_BOOKING,            │
│       STP_MESSAGE, OBO_TICKET, BROKER_FILL, CLEARING_MSG,           │
│       AFFIRM_MSG, GIVEUP_NOTICE, ALLOC_SPLIT, SETTLEMENT_INSTR,     │
│       MARGIN_CALL, AMENDMENT, POSITION_SNAPSHOT, NET_SETTLEMENT,    │
│       TRADE, RISK_MEASURE, SCHEDULE_EVENT                           │
│                                                                     │
│  Total: 4 datasets (down from 14)                                   │
│  Total event_types: 19 (each with specific payload schema)          │
└─────────────────────────────────────────────────────────────────────┘
```

Why this works:
- **entities, books, fpmls** are reference data — they don't transition, they're config
- **Everything else** (trades, legs, schedules, matches, allocations, amendments, measures, orders) are all events with different payload structures
- A "trade" is just `event_type: TRADE` — the materialized result of correlated events
- A "leg" lives inside a TRADE event's `payload.legs[]` — not a separate table
- A "schedule" is `event_type: SCHEDULE_EVENT` linked to the trade event
- A "measure" is `event_type: RISK_MEASURE` linked to the trade event
- Matching metadata lives in `correlation{}` on the event itself — no separate match table

### 5.6 New Enums (`schemas/_enums.yaml` additions)

```yaml
# ===========================================================================
# EVENT TYPE — the master enum that drives payload structure
# ===========================================================================
ENUM_EVENT_TYPE:
  # Pre-trade
  - { value: RFQ, label: "Request for Quote", icon: message-circle, group: PRE_TRADE, color: blue }
  - { value: QUOTE, icon: tag, group: PRE_TRADE, color: blue }
  - { value: ORDER, icon: shopping-cart, group: PRE_TRADE, color: blue }
  # Booking
  - { value: SALES_BOOKING, label: "Sales Booking", icon: user-check, group: BOOKING, color: emerald }
  - { value: TRADING_BOOKING, label: "Trading Booking", icon: trending-up, group: BOOKING, color: emerald }
  - { value: OBO_TICKET, label: "OBO Client Ticket", icon: user-plus, group: BOOKING, color: emerald }
  # External messages
  - { value: STP_MESSAGE, label: "STP Message", icon: zap, group: EXTERNAL, color: purple }
  - { value: BROKER_FILL, label: "Broker Fill", icon: check-square, group: EXTERNAL, color: purple }
  - { value: CLEARING_MSG, label: "Clearing Message", icon: shield, group: EXTERNAL, color: purple }
  - { value: AFFIRM_MSG, label: "Affirmation", icon: thumbs-up, group: EXTERNAL, color: purple }
  - { value: GIVEUP_NOTICE, label: "Give-Up Notice", icon: arrow-right, group: EXTERNAL, color: purple }
  # Allocation
  - { value: ALLOC_SPLIT, label: "Allocation Split", icon: git-branch, group: ALLOCATION, color: amber }
  # Settlement
  - { value: SETTLEMENT_INSTR, label: "Settlement Instruction", icon: repeat, group: SETTLEMENT, color: teal }
  - { value: MARGIN_CALL, label: "Margin Call", icon: alert-triangle, group: SETTLEMENT, color: teal }
  - { value: NET_SETTLEMENT, label: "Net Settlement", icon: layers, group: SETTLEMENT, color: teal }
  # Lifecycle
  - { value: AMENDMENT, icon: edit, group: LIFECYCLE, color: amber }
  - { value: POSITION_SNAPSHOT, label: "Position Snapshot", icon: camera, group: LIFECYCLE, color: grey }
  # Materialized
  - { value: TRADE, icon: trending-up, group: MATERIALIZED, color: green }
  - { value: RISK_MEASURE, label: "Risk Measure", icon: activity, group: MATERIALIZED, color: red }
  - { value: SCHEDULE_EVENT, label: "Schedule Event", icon: calendar, group: MATERIALIZED, color: blue }

# ===========================================================================
# EVENT STATUS — universal lifecycle states
# ===========================================================================
ENUM_EVENT_STATUS:
  # Universal
  - { value: ACTIVE, color: green }
  - { value: PENDING, color: amber }
  - { value: CANCELLED, color: grey }
  # Matching
  - { value: UNMATCHED, color: red }
  - { value: PARTIAL, color: amber }
  - { value: MATCHED, color: green }
  - { value: FORCED, color: blue }
  - { value: DISPUTED, color: red }
  - { value: RESOLVED, color: green }
  # Pre-trade
  - { value: QUOTED, color: amber }
  - { value: ACCEPTED, color: green }
  - { value: REJECTED, color: red }
  - { value: EXPIRED, color: grey }
  # Execution
  - { value: OPEN, color: blue }
  - { value: PARTIAL_FILL, color: amber }
  - { value: FILLED, color: green }
  # Trade lifecycle
  - { value: CONFIRMED, color: blue }
  - { value: CLEARED, color: green }
  - { value: SETTLED, color: green }

# ===========================================================================
# SOURCE TYPE — where events originate
# ===========================================================================
ENUM_SOURCE_TYPE:
  - { value: SALES_DESK, icon: user, group: INTERNAL }
  - { value: TRADING_DESK, icon: trending-up, group: INTERNAL }
  - { value: ALLOC_ENGINE, icon: git-branch, group: INTERNAL }
  - { value: MATCHING_ENGINE, icon: link, group: INTERNAL }
  - { value: NETTING_ENGINE, icon: layers, group: INTERNAL }
  - { value: ORDER_MGMT, icon: shopping-cart, group: INTERNAL }
  - { value: MANUAL, icon: edit, group: INTERNAL }
  - { value: CLIENT, icon: users, group: EXTERNAL }
  - { value: BROKER, icon: briefcase, group: EXTERNAL }
  - { value: CCP, icon: shield, group: EXTERNAL }
  - { value: EXCHANGE, icon: activity, group: EXTERNAL }
  - { value: MARKITWIRE, icon: globe, group: EXTERNAL }
  - { value: DTCC, icon: globe, group: EXTERNAL }
  - { value: BLOOMBERG, icon: monitor, group: EXTERNAL }
  - { value: STP_PIPELINE, icon: zap, group: EXTERNAL }

# ===========================================================================
# LINK TYPE — how events relate to each other
# ===========================================================================
ENUM_LINK_TYPE:
  # Correlation
  - { value: CORRELATES_WITH, label: "Correlates With", icon: link }
  - { value: RESPONDS_TO, label: "Responds To", icon: corner-down-right }
  - { value: ORIGINATES_FROM, label: "Originates From", icon: corner-up-left }
  # Hierarchy
  - { value: PARENT_OF, label: "Parent Of", icon: arrow-down }
  - { value: CHILD_OF, label: "Child Of", icon: arrow-up }
  - { value: CREATED_FROM, label: "Created From", icon: plus-circle }
  # Lifecycle
  - { value: AMENDS, label: "Amends", icon: edit }
  - { value: SUPERSEDES, label: "Supersedes", icon: refresh-cw }
  - { value: CANCELS, label: "Cancels", icon: x-circle }
  # Settlement / Risk
  - { value: SETTLES, label: "Settles", icon: check }
  - { value: NETS_WITH, label: "Nets With", icon: layers }
  - { value: MEASURES, label: "Measures", icon: activity }
  - { value: SCHEDULES, label: "Schedules", icon: calendar }

# ===========================================================================
# MATCHING ENUMS (same as before — used in correlation{} sub-dict)
# ===========================================================================
ENUM_MATCH_TYPE:
  - { value: CORRELATION, icon: link, color: blue }
  - { value: RECONCILIATION, icon: search, color: purple }
  - { value: ALLOCATION, icon: git-branch, color: amber }
  - { value: AGGREGATION, icon: layers, color: teal }
  - { value: OVERRIDE, icon: shield, color: red }

ENUM_MATCH_SCENARIO:
  - { value: SALES_TRADER, group: CORRELATION }
  - { value: BACK_TO_BACK, group: CORRELATION }
  - { value: RFQ, group: CORRELATION }
  - { value: ORDER_FILL, group: ALLOCATION }
  - { value: BROKER_EXEC, group: CORRELATION }
  - { value: CLEARING, group: CORRELATION }
  - { value: OBO_CLIENT, group: CORRELATION }
  - { value: CPTY_AFFIRM, group: CORRELATION }
  - { value: GIVEUP, group: CORRELATION }
  - { value: TRADE_CONFIRM, group: CORRELATION }
  - { value: BLOCK_ALLOC, group: ALLOCATION }
  - { value: STP_AUTOBOOK, group: CORRELATION }
  - { value: AMENDMENT_RECON, group: RECONCILIATION }
  - { value: EOD_POSITION, group: RECONCILIATION }
  - { value: SETTLEMENT, group: RECONCILIATION }
  - { value: MARGIN_RECON, group: RECONCILIATION }
  - { value: REGULATORY_RECON, group: RECONCILIATION }
  - { value: NETTING, group: AGGREGATION }
  - { value: COMPRESSION, group: AGGREGATION }
  - { value: FORCE_MATCH, group: OVERRIDE }
  - { value: DISPUTE, group: OVERRIDE }

ENUM_MATCH_STATUS:
  - { value: UNMATCHED, color: red, icon: x-circle }
  - { value: PARTIAL, label: "Partial Match", color: amber, icon: alert-triangle }
  - { value: MATCHED, color: green, icon: check-circle }
  - { value: FORCED, label: "Force Matched", color: blue, icon: check-square }
  - { value: DISPUTED, color: red, icon: alert-octagon }
  - { value: RESOLVED, color: green, icon: check-circle-2 }

ENUM_CARDINALITY:
  - { value: ONE_ONE, label: "1:1" }
  - { value: ONE_MANY, label: "1:N" }
  - { value: MANY_ONE, label: "N:1" }
  - { value: MANY_MANY, label: "N:M" }
  - { value: ONE_ZERO, label: "1:0" }

ENUM_MATCH_DIRECTION:
  - { value: LHS_FIRST, label: "LHS Initiated" }
  - { value: RHS_FIRST, label: "RHS Initiated" }
  - { value: SIMULTANEOUS, label: "Simultaneous" }

ENUM_PRIORITY:
  - { value: NORMAL, color: grey }
  - { value: HIGH, color: amber }
  - { value: CRITICAL, color: red }

# ===========================================================================
# PROTOCOL — wire protocol used to deliver the event
# ===========================================================================
ENUM_PROTOCOL:
  - { value: FIX, label: "FIX Protocol", icon: zap, group: ELECTRONIC }
  - { value: FPML, label: "FpML (ISDA)", icon: file-text, group: ELECTRONIC }
  - { value: SWIFT_MT, label: "SWIFT MT", icon: globe, group: ELECTRONIC }
  - { value: SWIFT_MX, label: "SWIFT MX (ISO 20022)", icon: globe, group: ELECTRONIC }
  - { value: REST, label: "REST API", icon: cloud, group: ELECTRONIC }
  - { value: JSON, label: "JSON", icon: code, group: ELECTRONIC }
  - { value: CSV, label: "CSV / Flat File", icon: file, group: FILE }
  - { value: INTERNAL, label: "Internal", icon: home, group: INTERNAL }

# ===========================================================================
# RAW FORMAT — format of the raw.content field
# ===========================================================================
ENUM_RAW_FORMAT:
  - { value: FIX, label: "FIX Tag-Value" }
  - { value: FPML, label: "FpML XML" }
  - { value: SWIFT_MT, label: "SWIFT MT (tag:value blocks)" }
  - { value: SWIFT_MX, label: "SWIFT MX (ISO 20022 XML)" }
  - { value: JSON, label: "JSON" }
  - { value: CSV, label: "CSV / Flat File" }
  - { value: INTERNAL, label: "Internal (no raw — manual entry)" }

# ===========================================================================
# ENRICHMENT FLAGS — risk/compliance alerts in enriched{}
# ===========================================================================
ENUM_RISK_FLAG:
  - { value: LARGE_NOTIONAL, color: amber, icon: alert-triangle }
  - { value: CONCENTRATION_RISK, color: red, icon: alert-octagon }
  - { value: NEW_COUNTERPARTY, color: blue, icon: user-plus }
  - { value: LIMIT_BREACH, color: red, icon: shield-off }
  - { value: WASH_TRADE, color: red, icon: alert-octagon }
  - { value: UNUSUAL_TENOR, color: amber, icon: clock }
  - { value: OFF_MARKET_PRICE, color: red, icon: trending-down }
  - { value: SANCTIONS_HIT, color: red, icon: x-octagon }

ENUM_REPORTING_STATUS:
  - { value: PENDING, color: amber }
  - { value: REPORTED, color: green }
  - { value: REJECTED, color: red }
  - { value: AMENDED, color: blue }
  - { value: EXEMPT, color: grey }

ENUM_SETTLEMENT_STATUS:
  - { value: PENDING, color: amber }
  - { value: INSTRUCTED, color: blue }
  - { value: MATCHED, color: green }
  - { value: SETTLED, color: green }
  - { value: FAILED, color: red }

# Keep existing product/entity/book enums unchanged
```

### 5.7 What This Means for the Current Model Dictionary

The current xdspy model system needs these capabilities to support this:

```
┌────────────────────────────────────────────────────────────────────────┐
│  CAPABILITY GAP ANALYSIS                                               │
│                                                                        │
│  Current xdspy model system:                                           │
│  ✓ BaseObj with computed fields (xid, xslug, xnsid, xchksum)           │
│  ✓ Schema compiler (YAML → Dynamo model)                               │
│  ✓ operation: MERGE (upsert semantics)                                 │
│  ✓ Nested dict fields (payload, ned, parties)                          │
│  ✓ List of dicts (legs, changes, approvals)                            │
│  ✓ FK references (fk: entities, fk_label: name)                        │
│  ✓ Enum support ($enums.ENUM_NAME)                                     │
│  ✓ XNS namespace registry (address any record)                         │
│  ✓ _system.yaml auto-injection                                         │
│                                                                        │
│  MISSING (need to build):                                              │
│                                                                        │
│  1. POLYMORPHIC PAYLOAD                                                │
│     payload dict structure varies by event_type                        │
│     Need: depends_on: event_type for nested schema validation          │
│     Like ENUM_LEG_TYPE depends_on product_type, but for dict shapes    │
│                                                                        │
│  2. TRANSITION LOG                                                     │
│     Append-only list that auto-captures field diffs on save            │
│     Need: pre-save hook that computes diff(old, new) → transitions[]   │
│     Similar to amendment pattern but built into BaseObj                │
│                                                                        │
│  3. EVENT LINKING                                                      │
│     links[] with typed relationships (CORRELATES_WITH, CHILD_OF)       │
│     Need: link resolution (given EVT-005, find all linked events)      │
│     Need: graph traversal (walk the chain from RFQ → settlement)       │
│     XNS can already address records — extend for link traversal        │
│                                                                        │
│  4. CORRELATION ENGINE                                                 │
│     Match two events, detect breaks, update correlation{} on both      │
│     Need: new xds/matching/ module (engine, rules, breaks, status)     │
│     The correlation{} sub-dict is just a nested dict — schema works    │
│                                                                        │
│  5. MATERIALIZATION                                                    │
│     Correlated events → create TRADE event with denormalized payload   │
│     Need: materialization service that reads linked events and         │
│     constructs the trade record                                        │
│                                                                        │
│  6. POLYMORPHIC VIEWS                                                  │
│     Same events dataset needs different table columns per event_type   │
│     Need: view config that adapts columns based on event_type filter   │
│     UIX DataTable already supports column configs — extend for         │
│     polymorphic payload rendering                                      │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.8 Codebase Modification Map

```
xdspy/ (FRAMEWORK)                              domains/xftws/ (DOMAIN)
│                                               │
│ ── EXISTING (modify) ──                        │ ── EXISTING (modify) ──
│                                               │
│ xds/dynamo/base.py                   │ schemas/
│   BaseObj: add transitions[] support           │   _enums.yaml
│   - pre_save_hook() computes diff              │     Add: ENUM_EVENT_TYPE,
│   - appends to transitions[]                   │     ENUM_EVENT_STATUS,
│   - version auto-increment                     │     ENUM_SOURCE_TYPE,
│                           │     ENUM_LINK_TYPE,
│ xds/dynamo/computed_fields.py                  │     ENUM_MATCH_TYPE/SCENARIO/STATUS,
│   Add: transition diff computation             │     ENUM_CARDINALITY/DIRECTION/PRIORITY
│   - _compute_diff(old, new) → dict            │
│   - _append_transition(obj, diff)              │   event.yaml ◀── NEW (the ONE schema)
│                                               │
│ xds/dynamo/schema_compiler.py                  │   (DELETE or keep as legacy aliases):
│   Add: polymorphic payload validation          │   trade.yaml, match.yaml, allocation.yaml,
│   - depends_on for dict structures             │   amendment.yaml, measure.yaml, leg.yaml,
│   - event_type → payload shape mapping         │   schedule.yaml
│   │   (KEEP): entity.yaml, book.yaml, fpml.yaml
│ xds/dynamo/model.py                           │
│   Add: links[] traversal methods│ assembly.yaml
│   - get_linked(rel_type) → list[Event]         │   Replace 10 datasets with: events
│   - get_chain() → ordered event list           │   Keep: entities, books, fpmls
│   - get_parent() / get_children()             │
│                                 │ ontology.yaml
│ xds/core/xns/registry.py                       │   Rewrite for event-centric model
│   Add: link-aware resolution                   │   Remove entity-per-dataset, add Event entity
│   - resolve_chain(event_id) → full chain       │   with event_type sub-classifications
│                                               │
│ xds/enums/                            │ server/
│   matching.py ◀── NEW                          │   mock_data.py ◀── REWRITE
│   Foundation matching enums                    │     EventFactory (one factory, polymorphic)
│      │     gen_fixtures() produces event chains
│ ── NEW ──       │     covering all 30 scenarios
│                                               │
│ xds/matching/ ◀── NEW MODULE                   │   matching/ ◀── NEW
│ ├── __init__.py               │   ├── config.py
│ ├── engine.py                                  │   │   xftws-specific match rules
│ │   MatchEngine:                               │   │   Tolerance configs per product
│ │   - correlate(lhs_event, rhs_event, rules)   │   │
│ │   - reconcile(lhs, rhs, fields) → breaks     │   ├── scenarios.py
│ │   - allocate(parent, children) → status      │   │   Scenario-specific orchestration
│ │   - aggregate(events, group_key) → result    │   │
│ │   - force(event_id, reason) → event          │   └── services/
│ │                       │       ├── novation.py
│ ├── rules.py                 │       ├── stp.py
│ │   MatchRule:               │       ├── rfq.py
│ │   - key_fields, tolerance, auto_threshold    │       ├── broker_recon.py
│ │   - resolution_action  │       ├── netting.py
│ │                         │       └── giveup.py
│ ├── breaks.py                                 │
│ │   BreakDetector:                            │
│ │   - detect(lhs, rhs) → list[Break]          │
│ │   - apply_tolerance(field, v1, v2) → bool   │
│ │                                             │
│ ├── transitions.py                            │
│ │   TransitionManager:                        │
│ │   - record_transition(event, old, new)      │
│ │   - get_diff(transition) → rendered diff    │
│ │   - get_timeline(event) → ordered transitions│
│ │                                             │
│ ├── links.py                                  │
│ │   LinkResolver:                             │
│ │   - resolve(event_id) → linked events       │
│ │   - walk_chain(event_id) → full lifecycle   │
│ │   - find_root(event_id) → originating event │
│ │                                             │
│ └── materializer.py                           │
│     TradeMaterializer:                        │
│     - materialize(correlated_events) → TRADE  │
│     - denormalize(trade_event) → blotter row  │
│                                               │
│ xds/api/routers/                              │
│   events.py ◀── NEW                           │
│   - GET  /events                              │
│   - GET  /events/{id}                         │
│   - GET  /events/{id}/chain                   │
│   - GET  /events/{id}/transitions             │
│   - POST /events/{id}/correlate               │
│   - POST /events/{id}/transition              │
│   - GET  /events/blotter?event_type=TRADE     │
│                                               │
│ xds/api/routers/matching.py ◀── NEW           │
│   - POST /matching/correlate                  │
│   - POST /matching/force                      │
│   - GET  /matching/rules                      │
│   - GET  /matching/breaks/{id}                │
│                                               │
│ ── UIX (xdsuix) ──                            │
│                                               │
│ packages/components/src/                      │
│   WorkflowPills.tsx ◀── NEW                   │
│     Horizontal pill pipeline component        │
│     Props: stages[], current, onClick         │
│                                               │
│   RevisionDiff.tsx ◀── NEW                    │
│     Git-style field diff renderer             │
│     Props: transition, fields                 │
│                                               │
│   EventTimeline.tsx ◀── NEW                   │
│     Vertical timeline of transitions          │
│     Props: transitions[], expandable          │
│                                               │
│   LinkGraph.tsx ◀── NEW                       │
│     Event chain visualization                 │
│     Props: events[], links[]                  │
│                                               │
│   (REUSE existing):                           │
│   DataTable — blotter grid                    │
│   Badge/StatusBadge — status indicators       │
│   Kanban — workflow board                     │
│   FilterBar — filter dropdowns                │
│   DetailPanel — slide-in detail view          │
│   ProgressBar — allocation progress           │
```

### 5.9 What Can Be Reused (Existing Codebase)

| Existing Component         | Location                        | Reuse For                                                       |
| -------------------------- | ------------------------------- | --------------------------------------------------------------- |
| **BaseObj**                | `xds/dynamo/base.py`            | Event base — extend with transitions[]                          |
| **Schema compiler**        | `xds/dynamo/schema_compiler.py` | Compile event.yaml — extend for polymorphic payload             |
| **Computed fields**        | `xds/dynamo/computed_fields.py` | xid, xslug, xnsid still work on events                          |
| **XNS registry**           | `xds/core/xns/registry.py`      | Address events by namespace — extend for chain resolution       |
| **Connector layer**        | `xds/connectors/`               | MongoDB storage works as-is — events are just documents         |
| **Repo layer**             | `xds/repos/`                    | save_many, get_many work — events are just records              |
| **API router pattern**     | `xds/api/routers/`              | Follow existing pattern for events.py, matching.py              |
| **_system.yaml**           | `xds/dynamo/`                   | Auto-inject id, timestamp, operation on events                  |
| **depends_on cascade**     | `xds/enums/`                    | Already have group-based cascading — extend for payload schemas |
| **Factory pattern**        | `domains/*/server/mock_data.py` | Same factory-boy approach for EventFactory                      |
| **StaticFixtureGenerator** | `xds/tools/static_fixtures.py`  | Generate event fixtures same way                                |
| **DataTable**              | `xdsuix packages`               | Blotter rendering — add polymorphic column config               |
| **Badge/StatusBadge**      | `xdsuix packages`               | Status pills — extend for workflow pill variant                 |
| **Kanban**                 | `xdsuix packages`               | Match status board — works as-is with events                    |
| **FilterBar**              | `xdsuix packages`               | Filter by event_type, status, source — extend for saved views   |
| **DetailPanel**            | `xdsuix packages`               | Event detail — extend for lifecycle tracker layout              |

---

## 6. Screen / View Specifications

> **Note**: The screen architecture described here is realized as the xFTWS Trading Workstation
> (`apps/xftws/`), driven by `domains/xftws/workstation.yaml`. See `UIX.md` for the full
> component inventory, composition tree, and workspace layouts.
>
> **Key architectural decisions** (since original PRD):
> - **StatusFilters** (clickable count buttons) replace the per-row workflow pills as primary navigation
> - Grid rows use **simple status badges** (colored dots), NOT per-row workflow pills
> - **WorkflowPills** appear in the **detail sidebar only** (per-event lifecycle view)
> - **workstation.yaml** is the golden source for UI config, paralleling assembly.yaml for backend
> - All workspaces share a common `AppShell` with header, status filters, filter bar, content + sidebar

### 6.1 Screen Map — How All Views Connect

```
┌─────────────────────────────────────────────────────────────────────┐
│  xFTWS — Fixed Income Trading Workstation                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ AppShell (persistent across all workspaces)                     ││
│  │  AppHeader: [Trading][Matching][Analytics][Chain][RFQ]          ││
│  │  StatusFilters: [●47 Unm][◐12 Part][●283 Match][▲8 Frc][✕3]    │ │
│  │  FilterBar: SmartFilter + presets + summary                    │ │
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  ┌──── WORKSPACE CONTENT + DETAIL SIDEBAR ────────────────────────┐ │
│  │                                                                 ││
│  │  Trading    → BlotterView + EventDetail (mode: lifecycle)      │ │
│  │  Matching   → BlotterView + EventDetail (mode: comparison)     │ │
│  │  Analytics  → ChartControl × N (full-width, no sidebar)        │ │
│  │  Chain      → EventTimeline + LinkGraph + RevisionDiff         │ │
│  │  RFQ        → BlotterView + EventDetail (mode: lifecycle)      │ │
│  │                                                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  Config source: domains/xftws/workstation.yaml                      │
│  Component source: @xdsui/components (standalone, no SpacesApp)     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Trade Blotter (primary — trader + sales shared view)

The main blotter. Each row is a trade. The **workflow pills** on each row show
where that trade sits across the full lifecycle pipeline at a glance.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Trade Blotter                    [Trader ▾] [FX ▾] [Today ▾]    [⚙ Views] [⟳]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Quick Filters:                                                                  │
│  [My Trades] [My Desk] [Unmatched] [Pending Alloc] [Amended] [STP]  [All]        │
│                                                                                  │
│  Saved Views:  [FX Spot Daily ★] [IRS Pipeline] [Block Trades] [+ New View]      │
│                                                                                  │
│  ┌────────┬────────┬────┬──────────┬──────────────────────────────────┬──────────┐│
│  │Trade   │Product │Ntl │Cpty      │ Workflow Pills                   │Actions   ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-001 │FX SPOT │10M │BARC      │ [●Booked][●Matched][○Alloc][○Clr][○Sttl]   │ [⋯]  ││
│  │        │USD/EUR │    │          │  sales    auto      —      —     —          ││
│  │        │        │    │          │  09:14    09:15                              ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-002 │IRS 5Y  │50M │GSI       │ [●Booked][◐Partial][○Alloc][○Clr][○Sttl]   │ [⋯]  ││
│  │        │USD     │    │          │  trader   2 breaks   —      —     —          ││
│  │        │        │    │          │  08:30    09:45                              ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-003 │FX FWD  │25M │HSBC      │ [●Booked][●Matched][●Alloc][●Clr][○Sttl]   │ [⋯]  ││
│  │        │GBP/USD │    │→LCH      │  sales    auto      3/3    LCH    pending   ││
│  │        │        │    │(novated) │  07:00    07:01     07:30  08:00             ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-004 │FX NDF  │15M │BNPP      │ [●STP   ][●Matched][○Alloc][○Clr][○Sttl]   │ [⋯]  ││
│  │        │USD/CNY │    │          │  pipeline  auto      —      —     —          ││
│  │        │        │    │          │  10:22     10:22                             ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-005 │FX SPOT │80M │JPM       │ [●Booked][○Match  ][◐Alloc][○Clr][○Sttl]   │ [⋯]  ││
│  │        │EUR/USD │    │          │  sales    waiting   2/5    —     —          ││
│  │        │(block) │    │          │  08:45              09:10                    ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-006 │IRS 10Y │30M │CITI      │ [●Booked][▲Forced ][○Alloc][○Clr][○Sttl]   │ [⋯]  ││
│  │        │USD     │    │          │  trader   M.Jones   —      —     —          ││
│  │        │        │    │          │  11:00    11:30                              ││
│  ├────────┼────────┼────┼──────────┼──────────────────────────────────┼──────────┤│
│  │TRD-007 │FX OPT  │20M │MSI       │ [●RFQ   ][●Quoted ][●Accept][●Booked][○Clr] │ [⋯]  ││
│  │        │EUR/USD │    │          │  client   4.25%    client  auto    —          ││
│  │        │        │    │          │  09:00    09:01    09:02   09:02              ││
│  └────────┴────────┴────┴──────────┴──────────────────────────────────┴──────────┘│
│                                                                                  │
│  Summary: 147 trades │ 12 unmatched │ 3 partial │ 2 pending alloc │ 1 disputed   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### Workflow Pill Legend

```
Pill States:                                                      
  ● Solid green  = complete (matched, allocated, cleared, settled)
  ◐ Half amber   = partial (breaks, incomplete allocation)        
  ○ Empty grey   = not yet reached / not applicable               
  ▲ Blue         = forced / override                              
  ✕ Red          = failed / disputed / rejected                   
                                                                  
Pill Labels (adapt per scenario):                                 
  ┌──────────────────────────────────────────────────────────────┐
  │ Standard:  [Booked] [Matched] [Alloc] [Cleared] [Settled]    │
  │ STP:       [STP   ] [Matched] [Alloc] [Cleared] [Settled]    │
  │ RFQ:       [RFQ   ] [Quoted ] [Accept] [Booked] [Cleared]    │
  │ Broker:    [Order ] [Fill   ] [Recon ] [Booked] [Settled]    │
  │ OBO:       [Ticket] [Affirm ] [Booked] [Matched] [Settled]   │
  │ Give-up:   [Exec  ] [GiveUp ] [Accept] [Booked] [Cleared]    │
  │ B2B:       [Client] [Hedge  ] [Linked] [Matched] [Settled]   │
  └──────────────────────────────────────────────────────────────┘
                                                                  
Sub-label (below pill):                                           
  Line 1: who/what (sales, trader, auto, pipeline, client, LCH)   
  Line 2: timestamp (HH:MM)                                       
```

#### Pill Click Behavior

Clicking any pill opens the **Revision Diff View** (section 6.7) showing
what changed at that stage transition.

### 6.3 Sales Blotter (sales-specific view)

Same structure as Trade Blotter but filtered and augmented for sales desk:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Sales Blotter                  [M. Jones ▾] [All Clients ▾]     [⚙ Views] [⟳]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Quick Filters:                                                                  │
│  [My Clients] [Pending Affirm] [OBO Tickets] [Block Allocs] [Unmatched]  [All]   │
│                                                                                  │
│  ┌────────┬────────┬────┬──────────┬────────┬────────────────────────┬───────────┐│
│  │Trade   │Client  │Ntl │Product   │Sales   │ Workflow               │P&L       ││
│  ├────────┼────────┼────┼──────────┼────────┼────────────────────────┼───────────┤│
│  │TRD-001 │BARC    │10M │FX SPOT   │M.Jones │ [●Bk][●Mt][○Al][○Cl]  │ +$12,400 │ │
│  │TRD-008 │SCP     │5M  │FX FWD    │M.Jones │ [●Tk][○Af][○Bk][○Mt]  │ pending  │ │
│  │        │(OBO)   │    │          │        │  OBO   awaiting        │          ││
│  │TRD-005 │JPM     │80M │FX SPOT   │M.Jones │ [●Bk][○Mt][◐Al][○Cl]  │ +$45,200 │ │
│  │        │(block) │    │          │        │        wait  2/5       │          ││
│  └────────┴────────┴────┴──────────┴────────┴────────────────────────┴───────────┘│
│                                                                                  │
│  My Day: 14 trades │ $185M notional │ +$127K P&L │ 3 pending actions             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 RFQ / Order Blotter

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  RFQ & Orders                        [Active ▾] [FX ▾]           [⚙ Views] [⟳]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Quick Filters:                                                                  │
│  [Open RFQs] [Quoted] [Pending Fill] [Broker Orders] [Expired]  [All]            │
│                                                                                  │
│  ┌────────┬──────┬────────┬────┬────────┬───────────────────────┬────────────────┐│
│  │Order   │Type  │Product │Ntl │Client/ │ Workflow              │Timer / Status  ││
│  │        │      │        │    │Broker  │                       │                ││
│  ├────────┼──────┼────────┼────┼────────┼───────────────────────┼────────────────┤│
│  │RFQ-001 │RFQ   │IRS 5Y  │50M │SCP     │ [●RFQ][●Qtd][○Acc]   │ ⏱ 18s remain  │ │
│  │        │      │        │    │        │  09:00 09:01          │ (validity)     ││
│  ├────────┼──────┼────────┼────┼────────┼───────────────────────┼────────────────┤│
│  │ORD-001 │LIMIT │FX SPOT │25M │—       │ [●Ord][◐Fill][○Done]  │ 15/25M filled  ││
│  │        │      │EUR/USD │    │        │  08:30 2 fills        │ VWAP: 1.0853   ││
│  ├────────┼──────┼────────┼────┼────────┼───────────────────────┼────────────────┤│
│  │ORD-002 │BROKER│FX FWD  │40M │ICAP    │ [●Sent][○Fill][○Rec]  │ awaiting fill  ││
│  │        │      │GBP/USD │    │        │  10:15                │                ││
│  ├────────┼──────┼────────┼────┼────────┼───────────────────────┼────────────────┤│
│  │RFQ-002 │RFQ   │FX OPT  │10M │EBC     │ [●RFQ][●Qtd][✕Exp]   │ EXPIRED        ││
│  │        │      │        │    │        │  08:00 08:01 08:01    │ (30s elapsed)  ││
│  └────────┴──────┴────────┴────┴────────┴───────────────────────┴────────────────┘│
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.5 Matching Blotter (ops/middle office view)

Dedicated matching view — every match record, grouped by scenario, with
pills showing LHS ↔ RHS correlation status.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Matching Blotter                [All Scenarios ▾] [Today ▾]     [⚙ Views] [⟳]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Status Pills:                                                                   │
│  [●47 Unmatched] [◐12 Partial] [●283 Matched] [▲8 Forced] [✕3 Dispute]           │
│                                                                                  │
│  Quick Filters:                                                                  │
│  [Sales↔Trader] [Clearing] [Allocations] [STP] [Broker] [Recon] [All]            │
│                                                                                  │
│  ┌────────┬───────────┬───────────┬────────────────────┬──────────────┬──────────┐│
│  │Match   │Type       │Scenario   │ LHS ←→ RHS         │Breaks        │Status    ││
│  ├────────┼───────────┼───────────┼────────────────────┼──────────────┼──────────┤│
│  │MAT-001 │Correlation│Sales→Trd  │ [●SALES]←→[○TRADE] │—             │UNMATCHED ││
│  │        │           │           │ TRD-FX-001  (wait) │              │          ││
│  ├────────┼───────────┼───────────┼────────────────────┼──────────────┼──────────┤│
│  │MAT-002 │Allocation │Block→Alloc│ [●BLOCK]←→[◐ALLOC] │remaining:20M │PARTIAL   ││
│  │        │           │           │ TRD-005     2/5    │              │          ││
│  ├────────┼───────────┼───────────┼────────────────────┼──────────────┼──────────┤│
│  │MAT-003 │Correlation│Clearing   │ [●TRADE]←→[●CCP  ] │—             │MATCHED   ││
│  │        │           │           │ TRD-003    LCH msg │cpty novated  │          ││
│  ├────────┼───────────┼───────────┼────────────────────┼──────────────┼──────────┤│
│  │MAT-004 │Recon      │EOD Pos    │ [●OURS ]←→[●CPTY ] │notional: $2K │PARTIAL   ││
│  │        │           │           │ BK-FX-US   BARC   │              │          ││
│  ├────────┼───────────┼───────────┼────────────────────┼──────────────┼──────────┤│
│  │MAT-005 │Correlation│Broker Exec│ [●ORDER]←→[●FILL ] │commission    │BREAK     ││
│  │        │           │           │ ORD-002    ICAP   │ +0.5bp over  │          ││
│  └────────┴───────────┴───────────┴────────────────────┴──────────────┴──────────┘│
│                                                                                  │
│  [Expand selected ▾]  Shows: Match Detail + Break Inspector + Timeline           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.6 Trade Lifecycle Tracker (detail — per trade)

Clicked from any blotter row. Shows the **full journey** of a single trade
with workflow pills as a horizontal pipeline. Each pill is clickable to
show the revision diff at that transition.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRD-003 — FX Forward GBP/USD 25M                              [SETTLED] ●green  │
│  Cpty: HSBC → LCH (novated)  │  Book: BK-FX-01  │  Trader: A.Chen                │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ══ LIFECYCLE PIPELINE ══════════════════════════════════════════════════════════│
│                                                                                  │
│    [●ORIGIN ]──▶[●BOOKED ]──▶[●MATCHED]──▶[●ALLOC  ]──▶[●CLEARED]──▶[●SETTLED]   │
│     RFQ          sales        auto         3/3          LCH          T+2         │
│     09:00        09:01        09:02        09:30        10:00        Mar-10      │
│     client       M.Jones      engine       alloc-eng    CCP          ops         │
│                                                                                  │
│  Click any pill above to see what changed ▲                                      │
│                                                                                  │
│  ══ CURRENT STATE ═══════════════════════════════════════════════════════════════│
│                                                                                  │
│  ┌─── Trade Economics ────────────┐  ┌─── NED ─────────────────────────┐         │
│  │ Product:  FPML-FX-FWD          │  │ Book:     BK-FX-01              │         │
│  │ Notional: 25,000,000 GBP       │  │ Portfolio: FX_US                │         │
│  │ Rate:     1.263400              │  │ Strategy:  Flow                 │        │
│  │ Fwd Pts:  +34.2                │  │ Clearing:  LCH                  │         │
│  │ Value Dt: 2026-06-10           │  │ UTI:      ABCD1234...           │         │
│  └────────────────────────────────┘  └─────────────────────────────────┘         │
│                                                                                  │
│  ┌─── Parties ────────────────────────────────────────────────────────┐          │
│  │ BUYER:  HSBC → LCH (novated at CLEARED stage)   Trader: K.Patel  │            │
│  │ SELLER: Global Markets LLC                       Sales: M.Jones   │           │
│  └────────────────────────────────────────────────────────────────────┘          │
│                                                                                  │
│  ══ RELATED RECORDS ═════════════════════════════════════════════════════════════│
│                                                                                  │
│  ┌── Legs (2) ────────────┐  ┌── Matches (2) ────────┐  ┌── Amendments (1) ──┐   │
│  │ LEG-001 FWD PAY  12.5M │  │ MAT-003 S→T  MATCHED  │  │ AMD-001 NED v2     │   │
│  │ LEG-002 FWD RCV  12.5M │  │ MAT-009 CLR  MATCHED  │  │ book_id changed    │   │
│  └────────────────────────┘  └────────────────────────┘  └────────────────────┘  │
│                                                                                  │
│  ┌── Allocations (3) ────────────────┐  ┌── Risk ─────────────────────────────┐  │
│  │ ACC-101  SCP   10M  BK-SCP-01     │  │ MTM: +$34,200  DV01: $2,150        │   │
│  │ ACC-205  EBC    8M  BK-EBC-03     │  │ FX Delta: -£625K  Theta: -$180/day │   │
│  │ ACC-310  NSAB   7M  BK-NSAB-01    │  │ As of: 2026-03-08 16:00            │   │
│  └───────────────────────────────────┘  └─────────────────────────────────────┘  │
│                                                                                  │
│  Actions: [Amend] [Cancel] [View History] [Export]                               │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.7 Revision Diff View (clicked from a pill)

When you click a workflow pill, this panel slides in showing **exactly what
changed** at that stage transition — git-diff style for trade fields.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRD-003 — Stage Transition: BOOKED → MATCHED                                    │
│  Transition at: 2026-03-08 09:02:14  │  By: Matching Engine (auto)               │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─── What Changed ──────────────────────────────────────────────────────────┐   │
│  │                                                                            │  │
│  │  Field              │ Before (v1)            │ After (v2)          │ Δ      │ │
│  │  ────────────────── │ ────────────────────── │ ─────────────────── │ ────── │ │
│  │  status             │ PENDING                │ CONFIRMED           │ ✓      │ │
│  │  match_status       │ UNMATCHED              │ MATCHED             │ ✓      │ │
│  │  matched_at         │ —                      │ 2026-03-08T09:02    │ + new  │ │
│  │  version            │ 1                      │ 2                   │ +1     │ │
│  │                     │                        │                     │        │ │
│  │  (14 fields unchanged — notional, rate, parties, ned, uti...)     │        │  │
│  │                                                                            │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── Match Record: MAT-003 ─────────────────────────────────────────────────┐   │
│  │ LHS: SALES_DESK → TRD-003 (M.Jones, 09:01)                                │   │
│  │ RHS: TRADING_DESK → TRD-003 (A.Chen, 09:02)                               │   │
│  │ Rule: RULE-FX-FWD  │  Breaks: 0  │  Auto-matched (within tolerance)       │   │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  [◀ Prev Stage]  [▶ Next Stage]  [View Full Diff]  [Close]                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### Revision Diff for Clearing/Novation (more complex)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRD-003 — Stage Transition: MATCHED → CLEARED                                   │
│  Transition at: 2026-03-08 10:00:32  │  By: CCP Clearing (LCH)                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─── What Changed ──────────────────────────────────────────────────────────┐   │
│  │                                                                            │  │
│  │  Field              │ Before (v2)            │ After (v3)          │ Δ      │ │
│  │  ────────────────── │ ────────────────────── │ ─────────────────── │ ────── │ │
│  │  parties[0].entity  │ HSBC                   │ LCH Clearnet        │ NOVATE │ │
│  │  ned.clearing       │ —                      │ LCH                 │ + new  │ │
│  │  status             │ CONFIRMED              │ CLEARED             │ ✓      │ │
│  │  version            │ 2                      │ 3                   │ +1     │ │
│  │                                                                            │  │
│  │  ⚠ COUNTERPARTY NOVATION: HSBC → LCH Clearnet                            │    │
│  │  Original cpty preserved in amendment history (AMD-002)                    │  │
│  │                                                                            │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌─── Clearing Message ──────────────────────────────────────────────────────┐   │
│  │ Source: LCH  │  Msg ID: CLR-2026030800032  │  Protocol: FpML 5.12        │    │
│  │ Novation: HSBC → LCH  │  Clearing ID: LCH-NV-00042                      │     │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  [◀ Prev Stage]  [▶ Next Stage]  [View Full Diff]  [Close]                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

#### Revision Diff for Allocation (1:N expansion)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRD-005 — Stage Transition: BOOKED → ALLOCATING                                 │
│  Transition at: 2026-03-08 09:10  │  By: Allocation Engine                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─── Block → Splits ───────────────────────────────────────────────────────┐    │
│  │                                                                           │   │
│  │  BLOCK TRADE: TRD-005  │  80,000,000 EUR/USD                             │    │
│  │  ████████████████████████████████████████░░░░░░░░░░░░░░░░░░  40%         │    │
│  │                                                                           │   │
│  │  Split │ Alloc Trade  │ Account │ Entity │ Quantity    │ Book    │ Status  │  │
│  │  ──────│──────────────│─────────│────────│─────────────│─────────│──────── │  │
│  │  1     │ TRD-AL-001   │ ACC-101 │ SCP    │ 20,000,000  │ BK-SCP  │ ●Done  │   │
│  │  2     │ TRD-AL-002   │ ACC-205 │ EBC    │ 12,000,000  │ BK-EBC  │ ●Done  │   │
│  │  3     │ (pending)    │         │        │             │         │ ○Wait  │   │
│  │  4     │ (pending)    │         │        │             │         │ ○Wait  │   │
│  │  5     │ (pending)    │         │        │             │         │ ○Wait  │   │
│  │                                                                           │   │
│  │  Allocated: 32,000,000  │  Remaining: 48,000,000                         │    │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Each split creates its own child trade with full lifecycle pills:               │
│  TRD-AL-001: [●Booked][●Matched][○Clr][○Sttl]                                    │
│  TRD-AL-002: [●Booked][○Match  ][○Clr][○Sttl]                                    │
│                                                                                  │
│  [Add Split] [Auto-Allocate Remaining] [Force Complete] [Close]                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.8 Matching Dashboard (aggregate ops view)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Matching Dashboard                           2026-03-08          [⚙ Config] [⟳] │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ══ STATUS SUMMARY ══════════════════════════════════════════════════════════════│
│                                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │UNMATCHED │ │ PARTIAL  │ │ MATCHED  │ │ FORCED   │ │ DISPUTE  │ │ EXPIRED  │   │
│  │    47    │ │    12    │ │   283    │ │     8    │ │     3   │ │     2    │    │
│  │   ●red   │ │  ◐amber  │ │  ●green  │ │  ▲blue   │ │  ✕red   │ │  ○grey   │    │
│  │  click→  │ │  click→  │ │  click→  │ │  click→  │ │  click→ │ │  click→  │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│                                                                                  │
│  ══ BY SCENARIO (pill buttons — click to filter blotter below) ══════════════    │
│                                                                                  │
│  Internal:    [Sales↔Trader 31] [B2B 8]        [Simult. 5]                       │
│  Pre-trade:   [RFQ 12]         [Orders 6]      [Broker 4]                        │
│  Post-trade:  [Clearing 18]    [Affirm 22]     [Give-up 3]   [OBO 5]             │
│  Allocation:  [Block→Split 9]                                                    │
│  STP:         [Auto-book 14]                                                     │
│  Recon:       [Amendment 7]    [EOD Pos 4]     [Settlement 8] [Margin 2]         │
│  Aggregation: [Netting 6]      [Compression 1]                                   │
│  Override:    [Force 8]        [Dispute 3]                                       │
│                                                                                  │
│  ══ SLA HEATMAP ═════════════════════════════════════════════════════════════════│
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────────┐│
│  │ 09:00  10:00  11:00  12:00  13:00  14:00  15:00  16:00  17:00              │  │
│  │ ██████ ██████ ██████ ██████ ░░░░░░ ░░░░░░ ░░░░░░ ░░░░░░ ░░░░░░            │   │
│  │  12     8      5      3    (future ───────────────────────────)              ││
│  │                                                                              ││
│  │ ██ = resolved on time   ▓▓ = resolved late   ░░ = pending / future          │ │
│  │ ⚠ 3 matches past SLA deadline                                               │ │
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ══ SCENARIO BREAKDOWN ══════════════════════════════════════════════════════════│
│                                                                                  │
│  ┌─── By Type (pie) ───────────┐  ┌─── By Source (bar) ──────────────────────┐   │
│  │      Correlation            │  │ SALES_DESK    ████████████████ 42        │   │
│  │      ████████ 58%           │  │ TRADING_DESK  ██████████ 28              │   │
│  │      Recon  ███ 12%         │  │ STP_PIPELINE  ████████ 22                │   │
│  │      Alloc  ██ 8%           │  │ CCP/LCH       ███████ 18                 │   │
│  │      STP    ████ 14%        │  │ MARKITWIRE    █████ 14                   │   │
│  │      Other  ██ 8%           │  │ BROKER        ███ 8                      │   │
│  └─────────────────────────────┘  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.9 Filter Bar & Saved Views (shared across all blotters)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  FILTER BAR (persistent, configurable per user)                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Dropdowns:                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │ [Product ▾]  [Cpty ▾]  [Desk ▾]  [Trader ▾]  [Status ▾]  [Date ▾]     │       │
│  │ [Scenario ▾] [Match Type ▾] [Source ▾] [Priority ▾] [SLA ▾]           │       │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  Role-Based Presets (auto-applied on login):                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │ TRADER:                                                                  │    │
│  │   Default: My Desk + Today + Unmatched first                            │     │
│  │   Quick: [My Trades] [Risk Book] [B2B Hedges] [Pending Match]           │     │
│  │                                                                          │    │
│  │ SALES:                                                                   │    │
│  │   Default: My Clients + Today + Pending actions first                   │     │
│  │   Quick: [My Clients] [OBO Tickets] [Block Allocs] [Pending Affirm]     │     │
│  │                                                                          │    │
│  │ OPERATIONS:                                                              │    │
│  │   Default: All trades + Unmatched + Past SLA first                      │     │
│  │   Quick: [Unmatched] [Breaks] [Past SLA] [Clearing] [Settlement]        │     │
│  │                                                                          │    │
│  │ RISK:                                                                    │    │
│  │   Default: All trades + Largest notional first                          │     │
│  │   Quick: [High Risk] [Limit Breach] [Margin Dispute] [Greeks]           │     │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  Saved Views (user-created, shareable):                                          │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │ [★ FX Spot Daily]  [★ IRS Pipeline]  [★ Block Allocs]  [+ Save View]   │      │
│  │                                                                          │    │
│  │ Each saved view stores:                                                  │    │
│  │   - Filter state (all dropdowns)                                        │     │
│  │   - Column visibility + order                                           │     │
│  │   - Sort order                                                          │     │
│  │   - Pill columns visible (which workflow stages shown)                   │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.10 Kanban Board (by match_status)

```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│UNMATCHED │ PARTIAL  │ MATCHED  │ FORCED   │ DISPUTED │
│          │          │          │          │          │
│ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │
│ │MAT-01│ │ │MAT-02│ │ │MAT-10│ │ │MAT-05│ │ │MAT-24│ │
│ │S→T   │ │ │Alloc │ │ │S→T   │ │ │Force │ │ │Margin│ │
│ │FX Spt│ │ │60%   │ │ │IRS   │ │ │FX Fwd│ │ │$50K  │ │
│ └──────┘ │ └──────┘ │ └──────┘ │ └──────┘ │ └──────┘ │
│ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │          │          │
│ │MAT-03│ │ │MAT-07│ │ │MAT-11│ │          │          │
│ │Clear │ │ │Broker│ │ │B2B   │ │          │          │
│ │LCH   │ │ │ICAP  │ │ │Hedge │ │          │          │
│ └──────┘ │ └──────┘ │ └──────┘ │          │          │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

### 6.11 Version History Panel (full trade revision log)

Accessible from [View History] on the lifecycle tracker. Shows every version
of the trade as a timeline with expandable diffs.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TRD-003 — Version History                                        [Export] [✕]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ● v4 — SETTLED                                          2026-03-10 14:00        │
│  │  By: Operations (auto-settlement)                                             │
│  │  Changed: status CLEARED → SETTLED                                            │
│  │  [Expand Diff]                                                                │
│  │                                                                               │
│  ● v3 — CLEARED (novation)                                2026-03-08 10:00       │
│  │  By: CCP Clearing (LCH msg CLR-2026030800032)                                 │
│  │  Changed: parties[0].entity HSBC → LCH, ned.clearing → LCH                    │
│  │  ┌─── Expanded Diff ──────────────────────────────────────────────────┐       │
│  │  │  - parties[0].entity_id: "ENT-HSBC"                               │        │
│  │  │  + parties[0].entity_id: "ENT-LCH"                                │        │
│  │  │  - ned.clearing: null                                              │       │
│  │  │  + ned.clearing: "LCH"                                            │        │
│  │  │  - status: "CONFIRMED"                                             │       │
│  │  │  + status: "CLEARED"                                               │       │
│  │  │  - version: 2                                                      │       │
│  │  │  + version: 3                                                      │       │
│  │  └────────────────────────────────────────────────────────────────────┘       │
│  │                                                                               │
│  ● v2 — CONFIRMED (matched)                               2026-03-08 09:02       │
│  │  By: Matching Engine (auto-match, MAT-003)                                    │
│  │  Changed: status PENDING → CONFIRMED, match_status → MATCHED                  │
│  │  [Expand Diff]                                                                │
│  │                                                                               │
│  ● v1 — PENDING (initial booking)                          2026-03-08 09:01      │
│     By: M.Jones (Sales Desk)                                                     │
│     Initial creation — all fields set                                            │
│     [View Full Record]                                                           │
│                                                                                  │
│  [Compare Any Two Versions ▾]  [Collapse All]  [Export History as JSON]          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 6.12 View Configuration Summary

> **Updated**: Mapped to xFTWS workstation architecture. See UIX.md for authoritative layouts.

| PRD View           | xFTWS Workspace                     | Type                                   | Key Features                                                  |
| ------------------ | ----------------------------------- | -------------------------------------- | ------------------------------------------------------------- |
| Trade Blotter      | **Trading** workspace               | table + status badges + detail sidebar | YAML-driven columns, filter presets, WorkflowPills in sidebar |
| Sales Blotter      | **Trading** workspace (filtered)    | table + badges                         | Same workspace, filtered to sales desk events                 |
| RFQ/Order Blotter  | **RFQ** workspace                   | table + timer column                   | Timer renderer for `payload.valid_until`, lifecycle sidebar   |
| Matching Blotter   | **Matching** workspace              | table + break count                    | Scenario grouping, ComparisonPanel in sidebar                 |
| Lifecycle Tracker  | Detail sidebar (mode: lifecycle)    | pipeline pills + sections              | WorkflowPills + economics/parties/NED sections                |
| Revision Diff      | Detail sidebar (chain mode)         | diff panel                             | RevisionDiff component from @xdsui/components/pipeline        |
| Version History    | Detail sidebar (history tab)        | timeline                               | EventTimeline + RevisionDiff per transition                   |
| Matching Dashboard | **Analytics** workspace             | charts                                 | ChartControl × N from `workstation.yaml` charts config        |
| Kanban Board       | *(deferred)*                        | —                                      | Not in v1 — replaced by StatusFilters navigation              |
| Allocation View    | Detail sidebar (allocation section) | SplitProgress                          | Shows when `links` has `PARENT_OF` relationship               |
| Chain Explorer     | **Chain** workspace                 | timeline + graph + diff                | EventTimeline + LinkGraph + RevisionDiff (3-panel)            |

---

## 7. Status Machine (Complete)

### 7.1 Core Match Statuses

```
                    ┌──────────┐
                    │UNMATCHED │ ← initial state (LHS arrives, no RHS)
                    └────┬─────┘
           │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌──────────┐ ┌──────┐ ┌──────────┐
        │ PARTIAL  │ │FORCED│ │ MATCHED  │
        │(breaks)  │ │(1:0) │ │(no break)│
        └────┬─────┘ └──────┘ └──────────┘
           │
      ┌──────┼──────┐
      ▼      ▼      ▼
┌──────────┐ │ ┌──────────┐
│ DISPUTED │ │ │ MATCHED  │ (breaks resolved)
└────┬─────┘ │ └──────────┘
     │     │
     ▼       ▼
┌──────────┐
│ RESOLVED │ (dispute settled)
└──────────┘
```

### 7.2 Pre-Trade (RFQ) Statuses

```
RFQ_OPEN → QUOTED → ACCEPTED → (creates trade, match MATCHED)
                  → REJECTED
                  → EXPIRED (validity window elapsed)
```

### 7.3 Execution (Order) Statuses

```
OPEN → PARTIAL_FILL → FILLED → (creates trade, match MATCHED)
                    → CANCELLED
```

---

## 8. Build Tree — Framework vs Domain (Event Model)

Now aligned with the unified event architecture from Section 5.

### 8.1 What Goes Where

```
xdspy/ (FRAMEWORK — data-agnostic)                    domains/xftws/ (DOMAIN — xftws-specific)
│                                                     │
│ ── MODIFY EXISTING ──                 │ ── SCHEMAS ──
│                                                     │
│ xds/dynamo/                                │ schemas/
│ ├── base.py                     ◀── MODIFY           │ ├── event.yaml              ◀── NEW (the ONE schema)
│ │   BaseObj:                                         │ │   Unified event record with polymorphic payload
│ │   + transitions[] auto-capture                     │ │
│ │   + pre_save_hook → diff computation               │ ├── _event_payloads/         ◀── NEW (payload schemas)
│ │   + version auto-increment on transition           │ │   ├── rfq.yaml             # RFQ payload shape
│ │                                                    │ │   ├── quote.yaml            # Quote payload shape
│ ├── computed_fields.py          ◀── MODIFY           │ │   ├── order.yaml            # Order payload shape
│ │   + _compute_diff(old, new) → dict                 │ │   ├── sales_booking.yaml    # Sales booking payload
│ │   + _append_transition(obj, from, to, diff)        │ │   ├── trading_booking.yaml  # Trading booking payload
│ │                                                    │ │   ├── stp_message.yaml      # STP message payload
│ ├── schema_compiler.py          ◀── MODIFY           │ │   ├── obo_ticket.yaml       # OBO ticket payload
│ │   + polymorphic payload validation                 │ │   ├── broker_fill.yaml      # Broker fill payload
│ │   + payload_schemas: { event_type → schema_ref }   │ │   ├── clearing_msg.yaml     # Clearing msg payload
│ │   + compile payload sub-schema per event_type      │ │   ├── affirm_msg.yaml       # Affirmation payload
│ │                                                    │ │   ├── giveup_notice.yaml    # Give-up payload
│ ├── model.py                    ◀── MODIFY           │ │   ├── alloc_split.yaml      # Allocation payload
│ │   + get_linked(rel_type) → list[Event]             │ │   ├── settlement_instr.yaml # Settlement payload
│ │   + get_chain() → ordered event list               │ │   ├── margin_call.yaml      # Margin payload
│ │   + get_parent() / get_children()                  │ │   ├── amendment.yaml        # Amendment payload
│ │   + walk_links(start, direction) → graph           │ │   ├── trade.yaml            # Materialized trade
│ │                                                    │ │   ├── risk_measure.yaml     # Risk measure payload
│ │                                                    │ │   ├── schedule_event.yaml   # Schedule payload
│ ├── links.py                    ◀── NEW              │ │   ├── position_snapshot.yaml # Position payload
│ │   LinkResolver:                                    │ │   └── net_settlement.yaml   # Net settlement payload
│ │   - resolve(event_id) → linked events              │ │
│ │   - walk_chain(event_id) → full lifecycle          │ ├── _enums.yaml              ◀── ENRICH
│ │   - find_root(event_id) → originating event        │ │   Add all new enums from Section 5.6
│ │                                                    │ │
│ xds/core/xns/registry.py       ◀── MODIFY           │ ├── entity.yaml              (keep as-is)
│   + link-aware resolution                            │ ├── book.yaml                (keep as-is)
│   + resolve_chain(event_id) → full chain             │ └── fpml.yaml                (keep as-is)
│                                                     │
│ ── NEW MODULES ──                                    │     (DELETE — absorbed into event.yaml):
│        │     trade.yaml, match.yaml, allocation.yaml,
│ xds/matching/                   ◀── NEW              │     amendment.yaml, measure.yaml, leg.yaml,
│ ├── __init__.py                   │     schedule.yaml
│ ├── engine.py                                       │
│ │   MatchEngine:                       │ ── SERVER ──
│ │   - correlate(lhs, rhs, rules) → updates both     │
│ │   - reconcile(lhs, rhs, fields) → breaks  │ server/
│ │   - allocate(parent, children) → status            │ ├── mock_data.py             ◀── REWRITE
│ │   - aggregate(events, group_key) → result          │ │   Single EventFactory (polymorphic)
│ │   - force(event_id, reason) → event                │ │   gen_fixtures() → event chains
│ │                                                    │ │   for all 30 scenarios
│ ├── rules.py                                         │ │
│ │   MatchRule:│ ├── matching/                 ◀── NEW
│ │   - key_fields, tolerance, auto_threshold          │ │   ├── __init__.py
│ │   - resolution_action, valid_transitions           │ │   ├── config.py
│ │                                                    │ │   │   xftws-specific match rules
│ ├── breaks.py                                        │ │   │   per product type
│ │   BreakDetector:                                   │ │   │
│ │   - detect(lhs, rhs) → list[Break]                │ │   ├── scenarios.py
│ │   - apply_tolerance(field, v1, v2) → bool          │ │   │   Scenario orchestration
│ │                                                    │ │   │
│ ├── transitions.py                                   │ │   └── services/
│ │   TransitionManager:                               │ │       ├── novation.py
│ │   - record(event, old_status, new_status, diff)    │ │       ├── stp.py
│ │   - get_timeline(event) → ordered transitions      │ │       ├── rfq.py
│ │   - render_diff(transition) → display format       │ │       ├── broker_recon.py
│ │                                                    │ │       ├── netting.py
│ └── materializer.py                                  │ │       └── giveup.py
│     TradeMaterializer:                               │ │
│     - materialize(correlated_events) → TRADE event   │ ├── ontology.yaml             ◀── REWRITE
│     - denormalize(trade_event) → blotter row         │ ├── assembly.yaml              ◀── REWRITE
│          │ └── settings.yaml             (keep as-is)
│ xds/enums/                                          │
│ └── matching.py                 ◀── NEW             │
│     Foundation enums (MATCH_TYPE, CARDINALITY, etc.)│
│                                                     │
│ xds/api/routers/                 │ ── UIX (xdsuix) ──
│ ├── events.py                   ◀── NEW             │
│ │   GET  /events           │ packages/components/src/
│ │   GET  /events/{id}                                │ ├── WorkflowPills.tsx        ◀── NEW
│ │   GET  /events/{id}/chain                          │ ├── RevisionDiff.tsx         ◀── NEW
│ │   GET  /events/{id}/transitions                    │ ├── EventTimeline.tsx        ◀── NEW
│ │   POST /events/{id}/transition                     │ ├── LinkGraph.tsx            ◀── NEW
│ │   GET  /events/blotter?event_type=TRADE            │ │
│ │                                 │ (REUSE existing):
│ └── matching.py                 ◀── NEW              │ DataTable, Badge, Kanban,
│     POST /matching/correlate│ FilterBar, DetailPanel,
│     POST /matching/force                │ ProgressBar
│     GET  /matching/rules                            │
│     GET  /matching/breaks/{id}                      │
```

### 8.2 File Change Summary

| Location          | Action  | Files                                                                                                        | Impact                                                  |
| ----------------- | ------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| **xdspy** dynamo  | MODIFY  | `base.py`, `computed_fields.py`, `schema_compiler.py`, `model.py`                                            | Transitions, diffs, polymorphic payload, link traversal |
| **xdspy** dynamo  | NEW     | `links.py`                                                                                                   | Link resolution + chain walking                         |
| **xdspy** core    | MODIFY  | `xds/core/xns/registry.py`                                                                                   | Link-aware namespace resolution                         |
| **xdspy**         | NEW     | `xds/matching/{__init__,engine,rules,breaks,transitions,materializer}.py`                                    | Matching engine (5 primitives)                          |
| **xdspy**         | NEW     | `xds/enums/matching.py`                                                                                      | Foundation matching enums                               |
| **xdspy**         | NEW     | `xds/api/routers/{events,matching}.py`                                                                       | Event + matching API endpoints                          |
| **xftws** schemas | NEW     | `event.yaml` + `_event_payloads/*.yaml` (19 payload schemas)                                                 | Unified event schema                                    |
| **xftws** schemas | ENRICH  | `_enums.yaml`                                                                                                | All new enums                                           |
| **xftws** schemas | DELETE  | `trade.yaml`, `match.yaml`, `allocation.yaml`, `amendment.yaml`, `measure.yaml`, `leg.yaml`, `schedule.yaml` | Absorbed into event.yaml                                |
| **xftws** server  | REWRITE | `mock_data.py`                                                                                               | EventFactory + scenario chain generation                |
| **xftws** server  | NEW     | `matching/{config,scenarios}.py`, `services/*.py`                                                            | xftws-specific matching                                 |
| **xftws**         | REWRITE | `ontology.yaml`, `assembly.yaml`                                                                             | Event-centric model                                     |
| **xdsuix**        | NEW     | `WorkflowPills.tsx`, `RevisionDiff.tsx`, `EventTimeline.tsx`, `LinkGraph.tsx`                                | New UI components                                       |

---

## 9. Mock Data — Event Chain Generation

### 9.1 Single Factory, Polymorphic Payloads

```python
class EventFactory(factory.Factory):
    """One factory for all event types.
    payload structure adapts based on event_type.
    """
    class Meta:
        model = dict

    event_id = factory.LazyFunction(lambda: _gen_id("EVT"))
    event_type = None       # Set per scenario
    status = "ACTIVE"
    version = 1
    source = None           # Set per scenario
    actor = None            # Set per scenario
    payload = None          # Set per scenario (type-specific)
    links = factory.LazyFunction(lambda: [])
    correlation = None      # Set when events get correlated
    transitions = factory.LazyFunction(lambda: [])
    created_at = factory.LazyFunction(lambda: _random_datetime(-30, 0))
```

### 9.2 Scenario Chain Generation

Mock data generates **linked event chains**, not isolated records.

```python
def _gen_sales_trader_chain(entities, books, fpmls) -> list[dict]:
    """Scenario #1: Sales books → Trader confirms → Trade materialized."""
    sales_evt = EventFactory(
        event_type="SALES_BOOKING",
        source="SALES_DESK",
        actor=random.choice(SALES_NAMES),
        payload=_gen_booking_payload(fpmls, books, entities),
    )
    trader_evt = EventFactory(
        event_type="TRADING_BOOKING",
        source="TRADING_DESK",
        actor=random.choice(TRADER_NAMES),
        payload=_gen_booking_payload(fpmls, books, entities),
        links=[{"event_id": sales_evt["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "MATCHED",
            "direction": "LHS_FIRST",
        },
    )
    trade_evt = EventFactory(
        event_type="TRADE",
        source="MATCHING_ENGINE",
        payload=_materialize_trade(sales_evt, trader_evt),
        links=[
            {"event_id": sales_evt["event_id"], "rel": "CREATED_FROM", "role": "LHS"},
            {"event_id": trader_evt["event_id"], "rel": "CREATED_FROM", "role": "RHS"},
        ],
        transitions=[
            {"from_status": None, "to_status": "PENDING", "at": sales_evt["created_at"], "by": sales_evt["actor"]},
            {"from_status": "PENDING", "to_status": "CONFIRMED", "at": trader_evt["created_at"], "by": "engine"},
        ],
    )
    return [sales_evt, trader_evt, trade_evt]
```

### 9.3 Scenario Coverage

| Scenario                   | Events Generated                        | Chain Shape           |
| -------------------------- | --------------------------------------- | --------------------- |
| #1 Sales→Trader (8 chains) | SALES_BOOKING → TRADING_BOOKING → TRADE | 3 events/chain        |
| #2 Trader→Sales (4 chains) | TRADING_BOOKING → SALES_BOOKING → TRADE | 3 events/chain        |
| #3 Simultaneous (3 chains) | SALES_BOOKING + TRADING_BOOKING → TRADE | 3 events/chain        |
| #4 Block→Alloc (3 chains)  | SALES_BOOKING → TRADE → ALLOC_SPLIT x N | 5-7 events/chain      |
| #5 Force (2 chains)        | SALES_BOOKING → TRADE (forced)          | 2 events/chain        |
| #6 Clearing (4 chains)     | ...→ TRADE → CLEARING_MSG               | +1 event/chain        |
| #7 STP (3 chains)          | STP_MESSAGE → TRADE                     | 2 events/chain        |
| #8 OBO (2 chains)          | OBO_TICKET → AFFIRM_MSG → TRADE         | 3 events/chain        |
| #9 Cpty Affirm (5 chains)  | ...→ TRADE → AFFIRM_MSG                 | +1 event/chain        |
| #10 Give-up (2 chains)     | GIVEUP_NOTICE → TRADE                   | 2 events/chain        |
| #11 B2B (3 chains)         | TRADE (client) ↔ TRADE (hedge)          | 2 events/chain        |
| #17 RFQ (4 chains)         | RFQ → QUOTE → TRADE (or EXPIRED)        | 2-3 events/chain      |
| #18 Order→Fills (3 chains) | ORDER → BROKER_FILL x N → TRADE         | 4-6 events/chain      |
| #19 Broker exec (3 chains) | ORDER → BROKER_FILL → TRADE             | 3 events/chain        |
| #13 Amendment (3 chains)   | ...→ AMENDMENT                          | +1 event/chain        |
| #15 Netting (2 chains)     | TRADE x N → NET_SETTLEMENT              | N+1 events/chain      |
| #20 Settlement (3 chains)  | ...→ SETTLEMENT_INSTR                   | +1 event/chain        |
| #22 Margin (2 chains)      | MARGIN_CALL x 2 (our + cpty)            | 2 events/chain        |
| #24 Dispute (2 chains)     | Any with disputed correlation           | existing + transition |

**Estimated total**: ~200+ event records forming ~60+ linked chains covering all 30 scenarios.

### 9.4 Payload Schemas as Reusable Generators

```python
PAYLOAD_GENERATORS = {
    "RFQ": _gen_rfq_payload,
    "QUOTE": _gen_quote_payload,
    "ORDER": _gen_order_payload,
    "SALES_BOOKING": _gen_booking_payload,
    "TRADING_BOOKING": _gen_booking_payload,
    "STP_MESSAGE": _gen_stp_payload,
    "OBO_TICKET": _gen_obo_payload,
    "BROKER_FILL": _gen_broker_fill_payload,
    "CLEARING_MSG": _gen_clearing_payload,
    "AFFIRM_MSG": _gen_affirm_payload,
    "GIVEUP_NOTICE": _gen_giveup_payload,
    "ALLOC_SPLIT": _gen_alloc_payload,
    "SETTLEMENT_INSTR": _gen_settlement_payload,
    "MARGIN_CALL": _gen_margin_payload,
    "AMENDMENT": _gen_amendment_payload,
    "TRADE": _gen_trade_payload,       # materialized
    "RISK_MEASURE": _gen_risk_payload,
    "SCHEDULE_EVENT": _gen_schedule_payload,
    "NET_SETTLEMENT": _gen_netting_payload,
    "POSITION_SNAPSHOT": _gen_position_payload,
}
```

---

## 10. Implementation Phases (Event Model)

### Phase 1 — Event Schema + Foundation Infra
- Create `event.yaml` unified schema
- Create `_event_payloads/*.yaml` (19 payload schemas)
- Add all new enums to `_enums.yaml`
- Modify xdspy `BaseObj` for transitions[] auto-capture + version increment
- Modify xdspy `schema_compiler` for polymorphic payload validation
- Rewrite `assembly.yaml` (4 datasets: entities, books, fpmls, events)
- Rewrite `ontology.yaml` for event-centric model
- **Delivers**: Event records can be stored, transitioned, and validated

### Phase 2 — Links + Matching Engine
- Build `xds/dynamo/links.py` (link resolution, chain walking)
- Build `xds/matching/` module (engine, rules, breaks, transitions, materializer)
- Build `xds/api/routers/{events,matching}.py`
- Extend XNS for link-aware resolution
- **Delivers**: Events can be linked, correlated, and trades materialized

### Phase 3 — Mock Data + Pure Config Scenarios
- Rewrite `mock_data.py` with EventFactory + chain generators
- Generate chains for scenarios #1-5, #13 (pure config — no services)
- Reference data (entities, books, fpmls) stays as-is
- **Delivers**: Demo-ready with 6 core scenarios

### Phase 4 — Domain Services + Full Scenario Coverage
- Build `matching/config.py` + `scenarios.py` (xftws match rules)
- Build `services/*.py` (novation, stp, rfq, broker_recon, netting, giveup)
- Generate chains for remaining 18 scenarios
- **Delivers**: Full 30-scenario coverage

### Phase 5 — UIX Components ✅
- ~~Build WorkflowPills, RevisionDiff, EventTimeline, LinkGraph~~ **Done** (in `@xdsui/components/pipeline`)
- ~~Build ComparisonPanel, SplitProgress~~ **Done**
- Wire blotter views to /events API → **Replaced by**: xFTWS workstation app (Phase 6)
- **Delivers**: All pipeline visualization components available

### Phase 6 — xFTWS Workstation App (NEW — IN PROGRESS)
- YAML-driven workstation shell (`apps/xftws/`) with 5 workspaces
- AppShell + AppHeader + StatusFilters + BlotterView + AnalyticsView **Done**
- EventDetail (context-aware sidebar) **TODO**
- Playwright scenarios from `workstation.yaml` **TODO**
- **Delivers**: Full trading workstation UI driven by `workstation.yaml`

---

## 11. Schema Transition Map

How the current 12 schemas migrate to the event-centric model. The full ontology
is in `ontology.yaml` (v2.0) — this section covers the field-level transition.

### 11.1 What Stays

| Schema         | Why                                                   |
| -------------- | ----------------------------------------------------- |
| `entity.yaml`  | Static reference data — legal entities, CCPs, brokers |
| `book.yaml`    | Static reference data — trading books / portfolios    |
| `fpml.yaml`    | Static reference data — product templates             |
| `_enums.yaml`  | Enriched with event/matching/link enums               |
| `_system.yaml` | System fields still auto-injected on all records      |

### 11.2 What Gets Absorbed into `event.yaml`

#### `trade.yaml` → `event_type: TRADE` payload

| Old Field    | New Location                                   | Notes                               |
| ------------ | ---------------------------------------------- | ----------------------------------- |
| `trade_id`   | `payload.trade_id`                             | Still unique within TRADE events    |
| `fpml_type`  | `payload.fpml_type` + top-level `product_type` | Dual: payload detail + event filter |
| `trade_date` | `payload.trade_date`                           |                                     |
| `status`     | `event.status` (top-level)                     | Universal event status              |
| `version`    | Implicit — `len(transitions)`                  | No explicit version field           |
| `parties[]`  | `payload.parties`                              | Same structure                      |
| `ned{}`      | `payload.ned`                                  | Same structure                      |
| `uti`        | `payload.uti`                                  |                                     |
| `usi`        | `payload.usi`                                  |                                     |

#### `leg.yaml` → Embedded in booking/trade payloads

| Old Field             | New Location                          | Notes                                    |
| --------------------- | ------------------------------------- | ---------------------------------------- |
| `leg_id`              | `payload.legs[n].leg_id`              | **No longer a separate dataset**         |
| `trade_id`            | `event.event_id` (parent)             | Implicit — legs live inside their parent |
| `leg_type`            | `payload.legs[n].leg_type`            |                                          |
| `direction`           | `payload.legs[n].direction`           |                                          |
| `notional`            | `payload.legs[n].notional`            |                                          |
| `currency`            | `payload.legs[n].currency`            |                                          |
| `rate`                | `payload.legs[n].rate`                |                                          |
| `start_date/end_date` | `payload.legs[n].start_date/end_date` |                                          |

#### `schedule.yaml` → `event_type: SCHEDULE_EVENT`

| Old Field     | New Location                         | Notes                                     |
| ------------- | ------------------------------------ | ----------------------------------------- |
| `schedule_id` | `event.event_id`                     |                                           |
| `trade_id`    | `links[{ rel: SCHEDULES }].event_id` | Link to parent trade                      |
| `leg_id`      | `payload.leg_id`                     |                                           |
| `event_type`  | `payload.event_subtype`              | Renamed to avoid collision with top-level |
| `date`        | `payload.date`                       |                                           |
| `amount`      | `payload.amount`                     |                                           |
| `status`      | `event.status`                       |                                           |

#### `match.yaml` → `correlation{}` sub-dict on events

| Old Field      | New Location                       | Notes                             |
| -------------- | ---------------------------------- | --------------------------------- |
| `match_id`     | `event.event_id`                   | The correlated event IS the match |
| `match_status` | `event.correlation.match_status`   |                                   |
| `match_rule`   | `event.correlation.scenario`       |                                   |
| `lhs{}`        | The event itself (initiating side) | No longer a nested dict           |
| `rhs{}`        | `links[{ rel: CORRELATES_WITH }]`  | Link to counterpart event         |
| `breaks[]`     | `event.correlation.breaks`         | Same structure                    |
| `matched_at`   | `event.correlation.matched_at`     |                                   |
| `matched_by`   | `event.correlation.matched_by`     |                                   |

**Key insight**: No separate match table. Both correlated events get `correlation{}` populated. The link between them is `CORRELATES_WITH`.

#### `allocation.yaml` → `event_type: ALLOC_SPLIT`

| Old Field        | New Location                             | Notes                                           |
| ---------------- | ---------------------------------------- | ----------------------------------------------- |
| `allocation_id`  | `event.event_id`                         |                                                 |
| `block_trade_id` | `links[{ rel: CHILD_OF }].event_id`      | Link to parent                                  |
| `allocations[]`  | Each split = its own `ALLOC_SPLIT` event | 1 event per split, not 1 record with array      |
| `validation{}`   | Parent TRADE's `correlation{}`           | `match_type: ALLOCATION, cardinality: ONE_MANY` |

#### `amendment.yaml` → `event_type: AMENDMENT` + `transitions[]`

| Old Field        | New Location                                      | Notes                                  |
| ---------------- | ------------------------------------------------- | -------------------------------------- |
| `amendment_id`   | `event.event_id`                                  |                                        |
| `trade_id`       | `links[{ rel: AMENDS }].event_id`                 | Link to target                         |
| `amendment_type` | `payload.amendment_type`                          |                                        |
| `version`        | Implicit — count of linked AMENDMENT events       |                                        |
| `changes[]`      | `payload.changes` + target's `transitions[].diff` | Dual: amendment payload + target audit |
| `approvals[]`    | `payload.approvals`                               |                                        |
| `status`         | `event.status`                                    |                                        |

#### `measure.yaml` → `event_type: RISK_MEASURE`

| Old Field      | New Location                        | Notes         |
| -------------- | ----------------------------------- | ------------- |
| `measure_id`   | `event.event_id`                    |               |
| `trade_id`     | `links[{ rel: MEASURES }].event_id` | Link to trade |
| `leg_id`       | `payload.leg_event_id`              |               |
| `metric`       | `payload.metric`                    |               |
| `value`        | `payload.value`                     |               |
| `denomination` | `payload.denomination`              |               |
| `tenor_bucket` | `payload.tenor_bucket`              |               |
| `as_of_date`   | `payload.as_of_date`                |               |

### 11.3 New Event Types (no v1 equivalent)

These are entirely new — they didn't exist in the old model:

| Event Type          | Purpose                      | Source                    |
| ------------------- | ---------------------------- | ------------------------- |
| `RFQ`               | Client request for quote     | CLIENT                    |
| `QUOTE`             | Desk response with price     | SALES_DESK / TRADING_DESK |
| `ORDER`             | Order with fill tracking     | ORDER_MGMT                |
| `SALES_BOOKING`     | Sales desk enters economics  | SALES_DESK                |
| `TRADING_BOOKING`   | Trader enters risk booking   | TRADING_DESK              |
| `OBO_TICKET`        | On-behalf-of client ticket   | SALES_DESK                |
| `STP_MESSAGE`       | Inbound STP/FIX/FpML message | STP_PIPELINE              |
| `BROKER_FILL`       | External broker execution    | BROKER                    |
| `CLEARING_MSG`      | CCP clearing/novation        | CCP                       |
| `AFFIRM_MSG`        | Counterparty affirmation     | MARKITWIRE / DTCC         |
| `GIVEUP_NOTICE`     | Give-up/take-up notice       | BROKER                    |
| `SETTLEMENT_INSTR`  | Payment instruction          | SALES_DESK / OPS          |
| `MARGIN_CALL`       | VM/IA margin call            | CCP / OPS                 |
| `NET_SETTLEMENT`    | Netted settlement            | NETTING_ENGINE            |
| `POSITION_SNAPSHOT` | EOD position snapshot        | TRADING_DESK              |

### 11.4 Assembly Changes

```yaml
# BEFORE (10 datasets)
datasets:
  entities:    { schema: entity,     dset: entities }
  books:       { schema: book,       dset: books }
  fpmls:       { schema: fpml,       dset: fpmls }
  trades:      { schema: trade,      dset: trades }
  legs:        { schema: leg,        dset: legs }
  schedules:   { schema: schedule,   dset: schedules }
  matches:     { schema: match,      dset: matches }
  allocations: { schema: allocation, dset: allocations }
  amendments:  { schema: amendment,  dset: amendments }
  measures:    { schema: measure,    dset: measures }

# AFTER (4 datasets)
datasets:
  entities:  { schema: entity, dset: entities }
  books:     { schema: book,   dset: books }
  fpmls:     { schema: fpml,   dset: fpmls }
  events:    { schema: event,  dset: events }
```

### 11.5 What to Do with Old Schema Files

```
schemas/
├── _enums.yaml          # KEEP — add new event/matching enums
├── _system.yaml         # KEEP — unchanged
├── entity.yaml          # KEEP — unchanged
├── book.yaml            # KEEP — unchanged
├── fpml.yaml            # KEEP — unchanged
├── event.yaml           # NEW  — the unified event schema
├── _event_payloads/     # NEW  — polymorphic payload schemas
│   ├── rfq.yaml
│   ├── quote.yaml
│   ├── order.yaml
│   ├── sales_booking.yaml
│   ├── trading_booking.yaml
│   ├── obo_ticket.yaml
│   ├── stp_message.yaml
│   ├── broker_fill.yaml
│   ├── clearing_msg.yaml
│   ├── affirm_msg.yaml
│   ├── giveup_notice.yaml
│   ├── alloc_split.yaml
│   ├── settlement_instr.yaml
│   ├── margin_call.yaml
│   ├── net_settlement.yaml
│   ├── amendment.yaml
│   ├── position_snapshot.yaml
│   ├── trade.yaml
│   ├── risk_measure.yaml
│   └── schedule_event.yaml
│
├── trade.yaml           # DELETE — absorbed into event payloads
├── leg.yaml             # DELETE — embedded in booking/trade payloads
├── schedule.yaml        # DELETE — becomes SCHEDULE_EVENT
├── match.yaml           # DELETE — becomes correlation{} on events
├── allocation.yaml      # DELETE — becomes ALLOC_SPLIT events
├── amendment.yaml       # DELETE — becomes AMENDMENT events
└── measure.yaml         # DELETE — becomes RISK_MEASURE events
```

---

## 12. Glossary

| Term               | Definition                                                                    |
| ------------------ | ----------------------------------------------------------------------------- |
| **Correlation**    | Pairing two independent events representing the same economic reality         |
| **Reconciliation** | Comparing two views of the same record to find field-level differences        |
| **Allocation**     | Splitting one parent record into N child records with completeness validation |
| **Aggregation**    | Combining N records into 1 or M records (netting, compression)                |
| **Override**       | Force-resolving a match without a counterpart                                 |
| **LHS**            | Left-hand side — the initiating event/record                                  |
| **RHS**            | Right-hand side — the responding event/record(s)                              |
| **Break**          | A field-level difference between LHS and RHS that exceeds tolerance           |
| **Novation**       | Replacing a counterparty (typically with a CCP) on a matched trade            |
| **STP**            | Straight-Through Processing — automated trade booking from inbound messages   |
| **OBO**            | On-Behalf-Of — sales entering a trade ticket as agent for a client            |
| **Give-up**        | Transferring a trade from executing broker to prime broker                    |
| **Back-to-back**   | Mirror trade linking client-facing trade to risk/hedge trade                  |
| **RFQ**            | Request for Quote — client asks for a price, desk responds                    |
| **VWAP**           | Volume-Weighted Average Price — computed from multiple fills                  |
| **NED**            | Non-Economic Details — booking, portfolio, strategy, clearing info            |

---

## 13. Implementation Status & UIX Reconciliation

### 13.1 Phase Status

| Phase                                           | Description                                                                                | Status                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------- |
| **Phase 1** — Event Schema + Foundation Infra   | `event.yaml`, `_enums.yaml`, `assembly.yaml` rewrite, `ontology.yaml` rewrite              | **Done**                |
| **Phase 2** — Links + Matching Engine           | `xds/matching/` module, `assembly.yaml` correlations + pipelines                           | **Done** (config-level) |
| **Phase 3** — Mock Data + Pure Config Scenarios | `mock_data.py` rewrite with EventFactory + 30-scenario chain generation (15 product types) | **Done**                |
| **Phase 4** — Domain Services                   | Transform services (novation, STP, RFQ, broker, netting, giveup)                           | TODO (server-side)      |
| **Phase 5** — UIX Components (xdsuix)           | WorkflowPills, RevisionDiff, EventTimeline, ComparisonPanel, SplitProgress, LinkGraph      | **Done**                |
| **Phase 6** — xFTWS Workstation App             | `apps/xftws/` — YAML-driven workstation shell                                              | **In Progress**         |

### 13.2 xFTWS App Layer Status

| Component                                                          | Status | Notes                                    |
| ------------------------------------------------------------------ | ------ | ---------------------------------------- |
| `workstation.yaml`                                                 | Done   | 5 workspaces, status filters, scenarios  |
| `UIX.md` architecture spec                                         | Done   | Full component inventory + layouts       |
| AppShell + AppHeader + StatusFilters                               | Done   | Persistent shell across workspaces       |
| useAppState hook (zustand)                                         | Done   | Workspace + filter + selection state     |
| App.tsx (SpacesProvider, no SpacesApp)                             | Done   | Standalone component approach            |
| Vite YAML plugin (virtual:workstation-config)                      | Done   | YAML → TS types at build time            |
| workstationConfig.ts types + virtual import                        | Done   | Type-safe YAML config access             |
| BlotterView (YAML-driven columns + filters)                        | Done   | Shared across Trading/Matching/Chain/RFQ |
| AnalyticsView (YAML-driven charts)                                 | Done   | ChartControl × N from config             |
| domain/columns.ts (from YAML)                                      | Done   | Per-workspace column definitions         |
| domain/filters.ts (from YAML)                                      | Done   | Preset + custom filter definitions       |
| domain/mappers/ (transitionsToPills, linksToGraph, scenarioLabels) | Done   | Data → component props                   |
| scenarioLabels + status colors → YAML lifecycle section            | Done   | Zero hardcoded business vocab in TS      |
| EventDetail (lifecycle/comparison/chain modes)                     | Done   | Context-aware sidebar from YAML config   |
| Domain hooks (pills, chain, comparison)                            | Done   | Memoized selectors for detail sidebar    |
| Playwright config + scenarios                                      | Done   | 8 declarative scenarios in YAML          |
| Domain code consolidated under apps/xftws/src/domain/              | Done   | domains/xftws/xftws/ is superseded       |

### 13.3 PRD ↔ UIX Architecture Reconciliation

The PRD (this document) was written before the workstation architecture was finalized. Key differences between original PRD Section 6 and the actual implementation (documented in `UIX.md`):

| PRD Concept (Section 6)                         | Actual Implementation (UIX.md)                                                                             | Resolution              |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------------- |
| Per-row workflow pills in trade blotter         | **Simple status badge** (colored dot) per row; WorkflowPills in detail sidebar ONLY                        | UIX.md is authoritative |
| Separate blotters (Trade, Sales, RFQ, Matching) | **Unified workspaces** with shared AppShell; BlotterView + workspace-specific columns/filters              | UIX.md is authoritative |
| No mention of `workstation.yaml`                | **workstation.yaml is golden source** for all UI config (workspaces, columns, filters, actions, scenarios) | UIX.md is authoritative |
| StatusFilters not defined                       | **StatusFilters are PRIMARY navigation** — clickable count buttons driving filter state                    | UIX.md is authoritative |
| Filter Bar with dropdowns + saved views         | **SmartFilter** with presets from YAML + custom LHS/RHS fields                                             | UIX.md is authoritative |
| Kanban board for match status (§6.10)           | Not in scope for v1 — workspaces replace per-status board views                                            | Deferred                |
| Matching Dashboard (§6.8) as separate view      | **Analytics workspace** covers this — charts from `workstation.yaml`                                       | UIX.md is authoritative |

**Rule**: For UI architecture, layout, and component decisions, `UIX.md` + `workstation.yaml` are authoritative. The PRD remains authoritative for: business scenarios (§3), data model (§5), workflow diagrams (§4), status machine (§7), and mock data architecture (§9).

### 13.4 Document Ownership Map

| Document               | Owns                 | Authoritative For                                                        |
| ---------------------- | -------------------- | ------------------------------------------------------------------------ |
| **PRD.md** (this file) | Business domain spec | Scenarios, data model, matching engine, workflow, enums, mock data       |
| **UIX.md**             | UI architecture spec | Component inventory, workspace layouts, state management, file structure |
| **workstation.yaml**   | UI runtime config    | Workspaces, columns, filters, actions, scenarios (golden source for app) |
| **assembly.yaml**      | Backend config       | Datasets, correlations, workflow, pipelines, RBAC, encryption            |
| **ontology.yaml**      | Domain ontology      | Entity definitions, relationships, field semantics, vocab                |
| **domain.yaml**        | Domain manifest      | Identity, features, deploy config                                        |
