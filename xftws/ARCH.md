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
# xftws Architecture

> How xftws is built and why.

## Design Philosophy

xftws is an event-centric fixed income trading domain where all business actions — bookings, fills, amendments, risk measures, settlements — are variants of a single polymorphic `events` collection. This replaces the traditional model of separate trade, leg, schedule, and match tables. The architecture is built around five matching primitives (CORRELATION, RECONCILIATION, ALLOCATION, AGGREGATION, OVERRIDE) that handle 24 real-world trading scenarios, combined with a 19-state workflow engine and three-layer payload model (raw/payload/enriched).

## Component Map

```
domains/xftws/
├── assembly.yaml              # Golden source — event-centric datasets, workflow,
│                              #   24 correlation scenarios, 7 pipelines, RBAC
├── domain.yaml                # Identity (emerald accent, America/New_York TZ)
├── ontology.yaml              # Entity relationships, event taxonomy
├── settings.yaml              # Environment overrides
├── schemas/
│   ├── _enums.yaml            # Trade type/status/product enumerations
│   ├── _system.yaml           # Auto-injected system fields
│   ├── entity.yaml            # Legal entities, CCPs, brokers (LEI)
│   ├── book.yaml              # Trading books/portfolios
│   ├── fpml.yaml              # ISDA FpML product templates
│   ├── event.yaml             # Unified polymorphic event schema
│   └── _event_payloads/       # 19 event type payload schemas
│       ├── sales_booking.yaml
│       ├── trading_booking.yaml
│       ├── rfq.yaml
│       ├── quote.yaml
│       ├── order.yaml
│       ├── broker_fill.yaml
│       ├── trade.yaml
│       ├── amendment.yaml
│       ├── alloc_split.yaml
│       ├── stp_message.yaml
│       ├── obo_ticket.yaml
│       ├── clearing_msg.yaml
│       ├── affirm_msg.yaml
│       ├── giveup_notice.yaml
│       ├── settlement_instr.yaml
│       ├── margin_call.yaml
│       ├── position_snapshot.yaml
│       ├── net_settlement.yaml
│       ├── risk_measure.yaml
│       └── schedule_event.yaml
├── server/
│   └── mock_data.py           # gen_fixtures() — all datasets from one entry
├── pipelines/
│   ├── on_booking_received.yaml
│   ├── on_external_message.yaml
│   ├── on_allocation_requested.yaml
│   ├── on_settlement_due.yaml
│   ├── on_amendment_filed.yaml
│   ├── on_position_snapshot.yaml
│   └── on_override_action.yaml
└── vocabs/
    └── xftws.yaml             # FICC trading vocabulary
```

## Data Flow

```
              External Messages          Internal Bookings
              (STP, AFFIRM, etc.)        (Sales, Trading)
                     │                              │
                     ▼                         ▼     
              ┌─────────────────────────────────────┐
              │           EVENTS (unified)          │
              │   event_type → polymorphic payload  │
              │   status → 19-state workflow        │
              └──────────────┬──────────────────────┘
                                                    │
              ┌──────────────┼──────────────────────┐
              │              │                      │
      ┌───────▼───────┐  ┌──▼──────────┐    ┌─────▼──────┐
      │ CORRELATION   │  │RECONCILIATION│    │ ALLOCATION │
      │ (1:1 pairing) │  │ (diff-based) │    │ (1:N split)│
      │ 11 scenarios  │  │ 5 scenarios  │    │ 2 scenarios│
      └───────┬───────┘  └──────┬───────┘    └─────┬──────┘
              │                  │                  │
              ├──────────────────┼───────────────────┤
              │                  │                  │
      ┌───────▼──────┐   ┌──────▼───────┐   ┌──────▼──────┐
      │ AGGREGATION  │   │   OVERRIDE   │   │  WORKFLOW   │
      │ (N:1 compress│   │ (force match)│   │ (19 states) │
      │ 2 scenarios) │   │ 2 scenarios  │   │ SLA timers  │
      └──────────────┘   └──────────────┘   └─────────────┘
                                                    │
                                        ┌───────────▼───────────┐
                                        │    trade_blotter      │
                                        │ (view: events + entity│
                                        │  + book context)      │
                                        └───────────────────────┘
```

## Key Decisions

- **Single polymorphic events collection** — all 19 event types in one collection, discriminated by `event_type`. Eliminates N-table joins for trade lifecycle queries, enables unified audit trail and streaming
- **Three-layer payload model** — `raw` (original message), `payload` (normalized economics), `enriched` (computed fields). Preserves source fidelity while enabling standardized processing
- **Five matching primitives** — CORRELATION (1:1), RECONCILIATION (diff), ALLOCATION (1:N), AGGREGATION (N:1), OVERRIDE (manual). These compose to cover 24 real scenarios from RFQ to settlement recon
- **19-state workflow with SLA timers** — schema-driven state machine with role guards, required fields, auto-set timestamps, and regulatory SLA deadlines (e.g., UNMATCHED must resolve within 24h)
- **Three encryption DEKs** — trade economics, counterparty PII, and risk measures each get separate keys for granular access control
- **America/New_York timezone** — FICC trading follows NYC business hours
- **Streaming events at 2s** — append-mode streaming (not upsert) because events are immutable; `limit: 100` caps the streaming window
- **Six RBAC roles** — sales, trading, operations, risk (read-only), compliance (read-only), admin — mapped to real trading desk functions
- **col: property for column ordering** — event_type (`"1<"`), event_id (`"2<"`), status (3), source (4) pinned in table view for scan-friendly blotter display
- **Shared @xdsui components** — UI consumes RecordDetail sidebar, RecordEditForm, and other shared components from xdsuix, eliminating domain-specific boilerplate
