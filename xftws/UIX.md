# xFTWS UIX Architecture — Trading Workstation

> Purpose-built trading workstation driven by `workstation.yaml`. StatusFilters are primary navigation, filters trigger workflows, and every scenario is replayable via Playwright.

### Related Documents

| Document             | Scope                                                                                                    | Location                         |
| -------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------- |
| **PRD.md**           | Business domain: 30 scenarios, 15 product types, data model, matching engine, workflow, enums, mock data | `domains/xftws/PRD.md`           |
| **workstation.yaml** | UI runtime config (golden source): workspaces, columns, filters, actions, scenarios                      | `domains/xftws/workstation.yaml` |
| **assembly.yaml**    | Backend config: datasets, correlations, workflow rules, pipelines, RBAC, encryption                      | `domains/xftws/assembly.yaml`    |
| **ontology.yaml**    | Domain ontology: entity definitions, relationships, field semantics                                      | `domains/xftws/ontology.yaml`    |

**Authority**: This document (UIX.md) is authoritative for UI architecture, layouts, and component decisions. PRD.md is authoritative for business scenarios, data model, and matching engine design. workstation.yaml is the runtime golden source consumed by the app.

---

## 1. Architecture Principles

### 1.1 Not a Data Explorer

xFTWS is a **vertical trading application**, not a generic data browser. It uses `@xdsui/components` à la carte — importing standalone components (AgGridWrapper, SmartFilter, pipeline/*, workflow/*) directly, with `SpacesProvider` for data infrastructure only. No SpacesApp shell.

### 1.2 YAML-Driven

`workstation.yaml` is the UI golden source, paralleling `assembly.yaml` for the backend:

| Backend (assembly.yaml) | Frontend (workstation.yaml)                                |
| ----------------------- | ---------------------------------------------------------- |
| `datasets:`             | `workspaces:` (source, columns, filters, detail, actions)  |
| `correlations:`         | `custom_filters:` (LHS/RHS field defs)                     |
| `workflow:`             | `lifecycle:` (scenario labels, label→status, status→color) |
| `pipelines:`            | `action_triggers:` (auto + manual bindings)                |
| —                       | `status_filters:` (primary navigation)                     |
| —                       | `scenarios:` (Playwright E2E test steps)                   |

### 1.3 Filter → Workflow → Action Loop

The defining UX pattern:

1. **StatusFilters** show population counts (Unmatched: 47, Matched: 283, ...)
2. User clicks a status → **blotter filters**
3. User adds **filter presets** or **custom LHS/RHS criteria**
4. User selects a row → **detail sidebar** opens with context-appropriate view
5. **Actions** computed from: current status + user role + workspace action rules
6. Action triggers **workflow transition** (TransitionDialog if needs fields/confirmation)
7. Pipeline executes (auto or manual) → event updated → view refreshes
8. StatusFilter counts update automatically

### 1.4 Naming Convention

"Fixed Income" appears only in the app title. Components use generic names: `AppShell`, `StatusFilters`, `EventDetail` — not domain-prefixed names.

---

## 2. Component Inventory

### Standalone Components (from @xdsui/components, no SpacesApp context)

| Component             | Import Path         | Used For                                        |
| --------------------- | ------------------- | ----------------------------------------------- |
| **AgGridWrapper**     | `@xdsui/components` | All blotter views                               |
| **SmartFilter**       | `@xdsui/components` | Filter bar with presets + custom LHS/RHS fields |
| **ChartControl**      | `@xdsui/components` | Analytics workspace charts                      |
| **SchemaForm**        | `@xdsui/components` | Event detail editing, TransitionDialog fields   |
| **WorkflowActions**   | `@xdsui/components` | Transition buttons per workspace                |
| **TransitionDialog**  | `@xdsui/components` | Confirm + collect fields for transitions        |
| **WorkflowStatusBar** | `@xdsui/components` | Status progression in detail sidebar            |
| **CommandPalette**    | `@xdsui/components` | Cmd+K quick actions                             |

### Pipeline Components (from @xdsui/components/pipeline, domain-agnostic)

| Component           | Used In                             | Purpose                                  |
| ------------------- | ----------------------------------- | ---------------------------------------- |
| **WorkflowPills**   | Detail sidebar ONLY (not grid rows) | Single event lifecycle visualization     |
| **RevisionDiff**    | Chain Explorer, History tab         | Field-level diff for transitions         |
| **EventTimeline**   | Chain Explorer                      | Vertical ordered event chain             |
| **LinkGraph**       | Chain Explorer                      | DAG visualization of event relationships |
| **ComparisonPanel** | Matching detail                     | LHS ↔ RHS with break highlighting        |
| **SplitProgress**   | Trading detail (block trades)       | Allocation progress + child splits       |

### Infrastructure (from @xdsui/components/spaces — data layer only)

| Export                 | Purpose                                              |
| ---------------------- | ---------------------------------------------------- |
| `SpacesProvider`       | Zustand store + fixture loading + profile management |
| `useDatasets()`        | Read events, entities, books, fpmls from store       |
| `useSelectedProfile()` | Current profile (fixture/mock/local)                 |
| `useAppActions()`      | Store mutations                                      |

### App-Specific Components (built in apps/xftws/)

| Component       | Purpose                                                               |
| --------------- | --------------------------------------------------------------------- |
| `AppShell`      | Main layout: header + status filters + filter bar + content + sidebar |
| `AppHeader`     | Logo, workspace tabs, profile badge                                   |
| `StatusFilters` | Clickable status count buttons (PRIMARY navigation)                   |
| `BlotterView`   | Single reusable grid — columns, filters, data source all from YAML    |
| `AnalyticsView` | Charts dashboard (YAML-driven chart configs)                          |
| `EventDetail`   | Context-aware detail sidebar (lifecycle / comparison / chain modes)   |

---

## 3. Workspace Layouts

### 3.1 App Shell (All Workspaces)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│                                                                     │
│ ┌─────┐ ┌─────┐ ┌──────┐ ┌──────┐ ┌──────┐                          │
│ │● 47 │ │◐ 12 │ │● 283 │ │▲  8  │ │✕  3  │     ← StatusFilters      │
│ │Unm. │ │Part.│ │Match │ │Forcd │ │Faild │       (toggle on/off)    │
│ └─────┘ └─────┘ └──────┘ └──────┘ └──────┘                          │
├─────────────────────────────────────────────────────────────────────┤
│ [+ Filter] [Preset ▾] [Preset ▾]         276 of 350 ← SmartFilter   │
│ active: event_type IN (...) AND notional > 1M        ← Summary      │
├────────────────────────────────────┬────────────────────────────────┤
│                                    │                                │
│         Active View                │        Detail Sidebar          │
│         (per workspace)            │        (per workspace mode)    │
│                                    │                                │
└────────────────────────────────────┴────────────────────────────────┘
```

**Header**: Fixed across all workspaces. Workspace tabs switch the active view. StatusFilters persist and apply globally.

**Filter Bar**: Shows workspace-specific presets. [+ Filter] opens SmartFilter with standard + LHS/RHS custom fields. Summary line shows active criteria in natural language.

**Content + Sidebar**: Split panel. Content is the blotter/chart. Sidebar shows detail for selected row. Sidebar mode depends on workspace (lifecycle, comparison, chain_explorer).

### 3.2 Trading Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│ [● 47 Unmatched] [◐ 12 Partial] [● 283 Matched] [▲ 8] [✕ 3]         │
├─────────────────────────────────────────────────────────────────────┤
│ [+ Filter] [My Desk] [Today] [Large >10M]    276 of 350 events      │
├───────────────────────────────────┬─────────────────────────────────┤
│  ID      │ Type    │ ● │ Prod  │ │  TRD-FX-042                      │
│  EVT-001 │ TRADE   │ ● │ FX    │ │                                  │
│  EVT-002 │ TRADE   │ ● │ IRS   │ │  [●Booked]→[●Matched]→[◐Alloc]   │
│  EVT-003 │ S_BOOK  │ ◐ │ FX    │ │  →[○Cleared]→[○Settled]          │
│▸ EVT-004 │ TRADE   │ ● │ BOND  │ │                                  │
│  EVT-005 │ T_BOOK  │ ○ │ FX_O  │ │  ── Economics ────────────────   │
│  EVT-006 │ TRADE   │ ▲ │ IRS   │ │  Product:  FX Spot               │
│  EVT-007 │ S_BOOK  │ ✕ │ FX    │ │  Notional: 10,000,000 USD        │
│          │         │   │       │ │  Rate:     1.0842                │
│          │         │   │       │ │  Cpty:     Global Markets LLC    │
│          │ ● = status badge   │ │                                   │
│          │ (dot + color only) │ │  ── Allocation ───────────────    │
│          │ NOT workflow pills │ │  ████████░░ 80% (8M of 10M)       │
│          │                    │ │  Split 1: East 5M  ●              │
│          │                    │ │  Split 2: West 3M  ●              │
│          │                    │ │  Split 3: Asia 2M  ○ pending      │
│          │                    │ │                                   │
│          │                    │ │  [Amend] [Cancel]                 │
└───────────────────────────────────┴─────────────────────────────────┘
  Blotter: simple status dot        Detail: full WorkflowPills         
  per row (●◐○▲✕)                   + lifecycle + actions              
```

**Blotter**: Filtered to TRADE, SALES_BOOKING, TRADING_BOOKING by default. Simple status badge (colored dot) per row — NOT workflow pills. StatusFilters above provide workflow context.

**Detail sidebar (mode: lifecycle)**: WorkflowPills for the selected event's full pipeline. Payload sections (economics, parties, NED). SplitProgress if block trade with PARENT_OF links. Actions: Amend, Cancel.

### 3.3 Matching Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│ [● 47 Unmatched ✓] [◐ 12 Partial] [● 283] [▲ 8] [✕ 3]               │
├─────────────────────────────────────────────────────────────────────┤
│ [+ Filter] [Sales ↔ Trading] [Clearing Breaks] [With Breaks]        │
│ correlation.match_status = UNMATCHED                                │
├───────────────────────────────────┬─────────────────────────────────┤
│  ID      │ Scenario   │ ● │ Brk │ │  ── Correlation ────────────    │
│  EVT-010 │ Sales↔Trd  │ ○ │  0  │ │  Type:     CORRELATION          │
│  EVT-011 │ Sales↔Trd  │ ○ │  2  │ │  Scenario: SALES_TRADER         │
│▸ EVT-012 │ Broker     │ ○ │  1  │ │  Status:   UNMATCHED            │
│  EVT-013 │ Clearing   │ ◐ │  0  │ │                                 │
│  EVT-014 │ STP Auto   │ ○ │  0  │ │  ── LHS ↔ RHS ──────────────    │
│          │            │   │     │ │  ┌─────────┬──┬──────────┐      │
│          │            │   │     │ │  │ LHS     │  │ RHS      │      │
│          │            │   │     │ │  │ S_BOOK  │  │ T_BOOK   │      │
│          │            │   │     │ │  │ Sales   │  │ Trading  │      │
│          │            │   │     │ │  ├─────────┼──┼──────────┤      │
│          │            │   │     │ │  │ 10.0M   │⚠ │ 10.1M   │       │
│          │            │   │     │ │  │ 1.0842  │✓ │ 1.0842  │       │
│          │            │   │     │ │  │ T+2     │✓ │ T+2     │       │
│          │            │   │     │ │  └─────────┴──┴──────────┘      │
│          │            │   │     │ │  1 break: notional ±0.01        │
│          │            │   │     │ │                                 │
│ ──── Custom Filter (LHS/RHS) ── │ │  [Force Match] [Dispute]        │
│ lhs.source = SALES_DESK         │ │                                 │
│ AND rhs.source = TRADING_DESK   │ │                                 │
│ AND break.count > 0             │ │                                 │
└───────────────────────────────────┴─────────────────────────────────┘
```

**Blotter**: Filtered to events with correlation metadata. Columns: scenario, primitive, match_status, direction, break count. Break count column uses `break_count` renderer (red badge if > 0).

**Filter bar**: Workspace presets for common matching views (Sales ↔ Trading, Clearing Breaks, With Breaks). [+ Filter] shows LHS/RHS combined fields from `custom_filters.lhs_rhs_combined`.

**Detail sidebar (mode: comparison)**: Correlation metadata badges. ComparisonPanel showing LHS ↔ RHS with field-level break highlighting. Actions: Force Match, Resolve Break, Dispute.

### 3.4 Analytics Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│ [● 47 Unmatched] [◐ 12 Partial] [● 283 Matched] [▲ 8] [✕ 3]         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐  ┌────────────────────────────────────┐   │
│  │  By Event Type (pie) │  │  By Source (bar)                   │   │
│  │                      │  │                                    │   │
│  │    ┌───┐             │  │  SALES_DESK    ████████████ 42     │   │
│  │   /TRADE\  58%       │  │  TRADING_DESK  ████████ 28         │   │
│  │  │ BOOK │            │  │  STP_PIPELINE  ██████ 22           │   │
│  │   \RFQ /  12%        │  │  BROKER        ████ 15             │   │
│  │    └───┘             │  │  CCP           ███ 12              │   │
│  └──────────────────────┘  └────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Match Status Distribution (bar)                             │   │
│  │  MATCHED    ████████████████████████████████████████ 283     │   │
│  │  UNMATCHED  ██████████ 47                                    │   │
│  │  PARTIAL    ████ 12                                          │   │
│  │  FORCED     ███ 8                                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Click any chart segment → cross-filters Trading/Matching blotter   │
└─────────────────────────────────────────────────────────────────────┘
```

**Full-width charts**, no detail sidebar. Configured via `workstation.yaml` charts section. Chart segments are clickable — clicking "UNMATCHED" bar switches to Matching workspace with that status pre-filtered.

### 3.5 Chain Explorer Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│ [● 47] [◐ 12] [● 283] [▲ 8] [✕ 3]                                   │
├─────────────────────────────────────────────────────────────────────┤
│ [+ Filter] [Has Links]    Events with linked chains                 │
├──────────────────────────┬──────────────────────────────────────────┤
│  EventTimeline           │  LinkGraph                               │
│                          │                                          │
│  ● EVT-001 (RFQ)        │     [RFQ] ──→ [QUOTE]                     │
│  │  client, 09:00        │       │                                  │
│  ● EVT-002 (QUOTE)      │       ▼                                   │
│  │  desk, 09:01          │  [S_BOOK] ──→ [TRADE] ──→ [ALLOC-1]      │
│  ● EVT-003 (S_BOOK)     │       ▲         │    ──→ [ALLOC-2]        │
│  │  sales, 09:02         │  [T_BOOK]       ▼                        │
│  ● EVT-005 (TRADE)      │            [CLR_MSG]                      │
│  │  engine, 09:02        │                 │                        │
│  ● EVT-008 (CLR_MSG)    │            [SETTLE]                       │
│    LCH, 10:00            │                                          │
├──────────────────────────┴──────────────────────────────────────────┤
│  RevisionDiff (click any timeline node)                             │
│  EVT-005 v2→v3: parties[0].entity HSBC → LCH (NOVATE)               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ - parties[0].entity_id    ENT-HSBC                          │    │
│  │ + parties[0].entity_id    ENT-LCH          [NOVATE]         │    │
│  │ - status                  CONFIRMED                          │   │
│  │ + status                  CLEARED                            │   │
│  │   14 fields unchanged                                        │   │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

**Three-panel layout**: EventTimeline (left) + LinkGraph (right) + RevisionDiff (bottom, collapsible). Clicking a timeline node or graph node selects it and shows its transition diff below.

**Data source**: Blotter at top (hidden once a chain is selected). `/events/{id}/chain` returns full chain → EventTimeline renders ordered → LinkGraph renders DAG → Node click → RevisionDiff shows transition.

### 3.6 RFQ / Orders Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ xFTWS    [Trading][Matching][Analytics][Chain][RFQ]    [env▾][👤]  │
│ [● 47] [◐ 12] [● 283] [▲ 8] [✕ 3]                                   │
├─────────────────────────────────────────────────────────────────────┤
│ [+ Filter] [Pending RFQs] [Open Orders]                             │
├───────────────────────────────────┬─────────────────────────────────┤
│  ID      │ Type  │ ● │ Prod │ ⏱  │ │  RFQ-FX-007                    │
│  EVT-020 │ RFQ   │ ○ │ FX   │ 3m │ │                                │
│  EVT-021 │ QUOTE │ ● │ FX   │ —  │ │  [●RFQ]→[●Quoted]→[○Accept]    │
│▸ EVT-022 │ RFQ   │ ○ │ IRS  │ 8m │ │  →[○Booked]→[○Cleared]         │
│  EVT-023 │ ORDER │ ◐ │ BOND │ —  │ │                                │
│  EVT-024 │ FILL  │ ● │ BOND │ —  │ │  ── Request ───────────────    │
│          │       │   │      │    │ │  Product: IRS 5Y               │
│          │       │   │      │    │ │  Notional: 50,000,000 EUR      │
│          │       │   │      │    │ │  Client: Pacific Trading       │
│          │       │   │      │    │ │  Expires: 8m remaining         │
│          │       │   │      │    │ │                                │
│          │ ⏱ = countdown timer  │ │  [Send Quote] [Reject]          │
└───────────────────────────────────┴─────────────────────────────────┘
```

**Timer column**: `payload.valid_until` rendered as countdown timer for RFQs. Shows remaining time, changes color as deadline approaches (green > 10m, amber > 5m, red < 5m).

**Detail sidebar (mode: lifecycle)**: WorkflowPills for pre-trade pipeline (RFQ → Quoted → Accept → Booked → Cleared). Actions: Send Quote, Accept, Reject.

---

## 4. Filter Architecture

### 4.1 Filter Layers

```
Layer 1: StatusFilters (toggle buttons)
         ↓ OR logic between active statuses
Layer 2: Workspace default filter (from workstation.yaml)
         ↓ AND with Layer 1
Layer 3: Filter presets (from workstation.yaml, user toggles)
         ↓ AND with Layer 1+2
Layer 4: Custom SmartFilter rules (user adds via [+ Filter])
         ↓ AND with Layer 1+2+3
         = Final filtered dataset → AgGridWrapper
```

### 4.2 Custom LHS/RHS Filters

SmartFilter is extended with virtual field prefixes defined in `workstation.yaml` → `custom_filters.lhs_rhs_combined`:

| Prefix   | Resolution                                           | Example                     |
| -------- | ---------------------------------------------------- | --------------------------- |
| `lhs.`   | Current event (if direction=LHS) or linked LHS event | `lhs.source = SALES_DESK`   |
| `rhs.`   | Linked event via `links[rel=CORRELATES_WITH]`        | `rhs.source = TRADING_DESK` |
| `break.` | Computed from `correlation.breaks[]`                 | `break.count > 0`           |

**Filter engine resolves** these prefixes at query time:
- For `lhs.*` / `rhs.*`: follows `links[rel=CORRELATES_WITH]` to load the paired event
- For `break.*`: aggregates over `correlation.breaks[]` array

### 4.3 Filter → Action Wiring

```
SmartFilter state
     │
     ├── Active StatusFilters → match_status filter
     ├── Workspace default → event_type filter
     ├── Presets → scenario/status/desk filters
     └── Custom rules → LHS/RHS/break criteria
     │
     ▼
AgGridWrapper (filtered rows)
     │ (row selection)
     ▼
Action availability computed:
     ├── Current event.status → which transitions allowed (from assembly workflow)
     ├── User role → which transitions permitted (from workspace actions.role)
     ├── Workspace actions → which buttons shown
     └── Result: enabled/disabled action buttons in detail sidebar
```

---

## 5. Action Architecture

### 5.1 Manual Actions (User-Triggered)

Defined per workspace in `workstation.yaml` → `workspaces.{name}.actions`:

```yaml
actions:
  - key: force_match
    label: Force Match
    transition_to: FORCED
    needs: [correlation.resolution]    # Fields collected via TransitionDialog
    role: [operations, admin]          # Who can trigger
    confirm: true                      # Requires confirmation checkbox
    audit: full                        # Full audit trail
```

**UI flow**: Action button in detail sidebar → TransitionDialog (if `needs` or `confirm`) → API PATCH → pipeline triggers → view refreshes.

### 5.2 Automatic Actions (Pipeline-Triggered)

Defined in `workstation.yaml` → `action_triggers.auto`:

```yaml
auto:
  on_booking_received:
    source_filter: { event_type: [SALES_BOOKING, TRADING_BOOKING, ...] }
    pipeline: $pipelines.on_booking_received
```

These run server-side when events are saved. The UI observes results via:
- Streaming updates (if enabled)
- StatusFilter count refresh
- Blotter data refresh on profile/filter change

### 5.3 Action → Pipeline Mapping

| User Action           | Pipeline                  | Result                                |
| --------------------- | ------------------------- | ------------------------------------- |
| Save SALES_BOOKING    | `on_booking_received`     | Auto-correlate → MATCHED or UNMATCHED |
| Save BROKER_FILL      | `on_external_message`     | Auto-reconcile → update TRADE         |
| Save ALLOC_SPLIT      | `on_allocation_requested` | Validate split sums                   |
| Click [Force Match]   | `on_override_action`      | FORCED status + audit trail           |
| Click [Dispute]       | `on_override_action`      | DISPUTED status                       |
| Save AMENDMENT        | `on_amendment_filed`      | Diff applied to target trade          |
| Save SETTLEMENT_INSTR | `on_settlement_due`       | Process settlement/netting            |

---

## 6. Filter → Workflow → Action Flow

```
  USER INTERACTION                    SYSTEM RESPONSE
  ────────────────                    ───────────────

  Click [● 47 Unmatched]  ──────→  Filter blotter: match_status=UNMATCHED
         │                          StatusFilter button fills (active)
         │                          Count badge updates
         ▼
  Click [Sales ↔ Trading]  ─────→  AND: scenario=SALES_TRADER
  preset button                     SmartFilter shows combined criteria
         │
         ▼
  Add custom filter:        ────→  AND: lhs.source=SALES_DESK
  [+ Filter] → LHS/RHS tab         AND: break.count > 0
  lhs.source = SALES_DESK          SmartFilter renders LHS/RHS fields
  break.count > 0                   Grid re-filters
         │
         ▼
  Select row EVT-012        ────→  Detail sidebar opens
  in filtered blotter               ComparisonPanel shows LHS ↔ RHS
                                    Breaks highlighted in red
                                    Available actions computed from:
                                      current status + user role + rules
         │
         ▼
  Click [Force Match]       ────→  TransitionDialog opens
                                    Needs: correlation.resolution (textarea)
                                    Shows: confirm checkbox
         │
         ▼
  Fill resolution reason    ────→  API: PATCH /events/{id}/transition
  Click [Confirm]                   Pipeline: on_override_action triggers
                                    Event status → FORCED
                                    correlation.match_status → FORCED
                                    audit trail appended to transitions[]
         │
         ▼
  View auto-refreshes       ────→  StatusFilter counts update:
                                    Unmatched: 47→46, Forced: 8→9
                                    Row moves out of current filter
                                    (or stays if filter includes FORCED)


  ═══════════════════════════════════════════════════════════════

  AUTOMATIC TRIGGER (no user action)
  ──────────────────────────────────

  New SALES_BOOKING saved    ────→  Pipeline: on_booking_received
  (via API or streaming)            Step 1: classify_scenario
                                    Step 2: find_counterpart (query events)
                                    Step 3: correlate (key_fields + tolerance)
         │
         ▼
  Match found?
  ├── YES ──→ Both events: correlation.match_status = MATCHED
  │           TRADE event materialized
  │           StatusFilter: Matched count +1
  │           Blotter refreshes (if streaming enabled)
  │
  └── NO  ──→ Event: correlation.match_status = UNMATCHED
              StatusFilter: Unmatched count +1
              Blotter refreshes
```

---

## 7. Component Composition Tree

```
App
├── AuthProvider
│   └── SpacesProvider (data infra only — NO SpacesApp)
│       └── CommandPaletteProvider
│           └── AppShell
│               ├── AppHeader
│               │   ├── Logo + "xFTWS"
│               │   ├── WorkspaceTabs [Trading|Matching|Analytics|Chain|RFQ]
│               │   ├── EnvSelector (fixture/mock/local)
│               │   └── UserMenu (sign out)
│ │
│               ├── StatusFilters
│               │   └── StatusButton × 5 (toggle, count badge, color)
│ │
│               ├── FilterBar
│               │   ├── SmartFilter (standard + LHS/RHS custom fields)
│               │   ├── PresetButtons (from workspace.filters.presets)
│               │   └── FilterSummary (natural language active criteria)
│ │
│               └── ActiveView (switches by workspace tab)
│ │
│                   ├── TradingView
│                   │   ├── AgGridWrapper (status_badge renderer, NO pills)
│                   │   └── EventDetail (mode: lifecycle)
│                   │       ├── WorkflowPills (single event pipeline)
│                   │       ├── Payload sections (economics, parties, NED)
│                   │       ├── SplitProgress (if block trade)
│                   │       └── WorkflowActions (Amend, Cancel)
│ │
│                   ├── MatchingView
│                   │   ├── AgGridWrapper (scenario, break_count renderer)
│                   │   └── EventDetail (mode: comparison)
│                   │       ├── Correlation badges
│                   │       ├── ComparisonPanel (LHS ↔ RHS + breaks)
│                   │       └── WorkflowActions (Force Match, Dispute)
│ │
│                   ├── AnalyticsView
│                   │   ├── ChartControl × 3 (pie, bar, bar)
│                   │   └── (no detail sidebar)
│ │
│                   ├── ChainExplorerView
│                   │   ├── EventTimeline (left panel)
│                   │   ├── LinkGraph (right panel)
│                   │   └── RevisionDiff (bottom panel, collapsible)
│ │
│                   └── RfqView
│                       ├── AgGridWrapper (timer renderer for valid_until)
│                       └── EventDetail (mode: lifecycle)
│                           ├── WorkflowPills (RFQ pipeline)
│                           └── WorkflowActions (Quote, Accept, Reject)
```

---

## 8. State Management

### useAppState (zustand store — implemented)

```typescript
interface AppState {
  // Navigation
  activeWorkspace: WorkspaceKey          // 'trading' | 'matching' | 'analytics' | 'chain' | 'rfq'
  setActiveWorkspace: (ws: WorkspaceKey) => void  // resets selection + filters on switch

  // Selection
  selectedEventId: string | null         // Currently selected row
  selectedEventData: Record<string, unknown> | null
  selectEvent: (id: string | null, data?: Record<string, unknown> | null) => void

  // Sidebar
  sidebarOpen: boolean                   // Detail sidebar visibility (auto-opens on select)
  setSidebarOpen: (open: boolean) => void  // clear selection when closing

  // Status filter counts (computed from SpacesProvider data, set by StatusCountUpdater)
  statusCounts: Record<string, number>   // { unmatched: 47, partial: 12, ... }
  setStatusCounts: (counts: Record<string, number>) => void

  // Active filters (per workspace, reset on workspace switch)
  filters: ActiveFilters
  toggleStatusFilter: (key: string) => void  // toggle status key on/off (OR logic)
  togglePreset: (key: string) => void
  addCustomRule: (rule: FilterRule) => void
  removeCustomRule: (index: number) => void
  clearFilters: () => void
}

interface ActiveFilters {
  statusKeys: string[]      // toggled status filter keys (OR between them)
  presetKeys: string[]      // active preset keys
  customRules: FilterRule[] // user-added SmartFilter rules
}
```

### Data Flow

```
SpacesProvider (zustand)
  └── useDatasets() → events[], entities[], books[], fpmls[]
        │
        ▼
  StatusCountUpdater: iterates YAML status_filters.items, counts matching events → setStatusCounts()
  StatusFilters:      reads statusCounts from useAppState → renders count buttons
  FilterBar:          reads workspace.filters.presets from YAML → toggle buttons
  BlotterView:        applyAllFilters(events, workspace, statusKeys, presetKeys, customRules)
                      → builds ag-grid ColDefs from YAML columns → renders AgGridWrapper
  EventDetail:        reads detail.mode from YAML → selects renderer:
                        lifecycle:      useWorkflowPills(data) → WorkflowPills + field sections
                        comparison:     useMatchComparison(data) → ComparisonPanel + breaks
                        chain_explorer: useEventChain(data) → EventTimeline + LinkGraph
```

---

## 9. File Structure

```
apps/xftws/
├── src/
│   ├── main.tsx                     # Entry (lazy App)
│   ├── App.tsx                      # Auth + SpacesProvider + AppShell
│   ├── index.css                    # Tailwind v4 + theme
│   ├── vite-env.d.ts                # Type declaration for virtual:workstation-config
│   ├── config/
│   │   └── workstationConfig.ts     # TS types for workstation.yaml + virtual module import
│   ├── hooks/
│   │   ├── useAuthAdapter.ts        # Auth detection (XDS API vs passthrough)
│   │   └── useAppState.ts           # Workspace + filter + selection state (zustand)
│   ├── shell/
│   │   ├── AppShell.tsx             # Layout: StatusCountUpdater + header + filters + content + sidebar
│   │   ├── AppHeader.tsx            # Logo, workspace tabs, profile badge
│   │   └── StatusFilters.tsx        # Clickable count buttons (colors from YAML)
│   ├── views/
│   │   ├── BlotterView.tsx          # Single grid for all blotter workspaces (columns + filters from YAML)
│   │   └── AnalyticsView.tsx        # Charts dashboard (chart configs from YAML)
│   └── domain/
│       ├── columns.ts               # getWorkspaceColumns() reads from YAML
│       ├── filters.ts               # applyAllFilters() — 4 layers, all from YAML
│       ├── detail/
│       │   └── EventDetail.tsx      # Context-aware sidebar (mode from YAML: lifecycle/comparison/chain)
│       ├── hooks/
│       │   ├── useWorkflowPills.ts  # event data → PillStage[] via YAML scenario labels
│       │   ├── useEventChain.ts     # links[] → TimelineNode[] + GraphNode[] + GraphEdge[]
│       │   └── useMatchComparison.ts # correlation → ComparisonRecord + FieldBreak[]
│       └── mappers/
│           ├── scenarioLabels.ts    # Re-exports from wsConfig.lifecycle (YAML golden source)
│           ├── transitionsToPills.ts # EventTransition[] → PillStage[]
│           ├── linksToGraph.ts      # EventRecord[] → {nodes, edges}
│           └── breaksToComparison.ts # CorrelationData → ComparisonPanel props
├── e2e/
│   ├── scenarios.spec.ts            # Playwright scenario replay tests (8 scenarios)
│   └── test-utils.ts               # Shared selectors + helpers
├── playwright.config.ts             # Port 3001, webServer: pnpm dev
├── package.json
├── tsconfig.json
├── vite.config.ts                   # workstationYaml() plugin + xdsFixtureFiles + aliases
└── index.html
```

### Library vs App Boundary

| Concern               | Location                          | Rationale                                  |
| --------------------- | --------------------------------- | ------------------------------------------ |
| Pipeline components   | `@xdsui/components/pipeline`      | Domain-agnostic, reusable                  |
| Standalone components | `@xdsui/components`               | Generic (AgGrid, SmartFilter, Chart)       |
| Data infrastructure   | `@xdsui/components/spaces`        | Provider + hooks only                      |
| YAML config (golden)  | `domains/xftws/workstation.yaml`  | All business vocabulary lives here         |
| TS types + import     | `apps/xftws/src/config/`          | Build-time bridge via Vite virtual module  |
| Column + filter logic | `apps/xftws/src/domain/`          | Reads from YAML, no hardcoded definitions  |
| Data mappers          | `apps/xftws/src/domain/mappers/`  | Transform event data → component props     |
| Domain hooks          | `apps/xftws/src/domain/hooks/`    | Memoized selectors (pills, chain, compare) |
| Shell + views         | `apps/xftws/src/shell/`, `views/` | App chrome + grid/chart rendering          |

---

## 10. Playwright Scenario Tests

### Test Architecture

Each scenario in `workstation.yaml` → `scenarios` maps to a Playwright test. Tests run against fixture data (no API required) at `http://localhost:3001`.

### Scenarios

| Scenario                   | Validates                                            |
| -------------------------- | ---------------------------------------------------- |
| `status_filter_navigation` | StatusFilter toggle, count badges, blotter filtering |
| `sales_trader_match`       | Trading view → detail → Matching view → comparison   |
| `force_match`              | Action button → TransitionDialog → status update     |
| `rfq_to_trade`             | Pre-trade lifecycle → chain explorer                 |
| `block_allocation`         | SplitProgress in detail sidebar                      |
| `amendment_recon`          | History tab → RevisionDiff                           |
| `chain_explorer`           | EventTimeline + LinkGraph + RevisionDiff             |
| `workspace_switching`      | All 5 workspaces render correctly                    |

### Scenario ↔ PRD Business Scenario Mapping

These 8 Playwright scenarios cover the core UI flows. The PRD (§3) defines 24 business scenarios for the matching engine — each generates fixture data that these E2E tests validate through the UI. Key mappings:

| Playwright Scenario  | PRD Business Scenarios Exercised                  |
| -------------------- | ------------------------------------------------- |
| `sales_trader_match` | #1 Sales→Trader, #2 Trader→Sales, #3 Simultaneous |
| `force_match`        | #5 Force match                                    |
| `rfq_to_trade`       | #17 RFQ→Quote→Accept                              |
| `block_allocation`   | #4 Block→Allocations                              |
| `amendment_recon`    | #13 Amendment matching                            |
| `chain_explorer`     | #6 Clearing, #17 RFQ (full chain traversal)       |

Scenarios #6-#12, #14-#16, #18-#24 exercise backend pipelines and will be validated via API tests, not Playwright. The fixture data covers all 30 scenarios across 15 product types so the blotter displays diverse event chains.

### Test Execution

```bash
cd apps/xftws
npx playwright test                    # All scenarios
npx playwright test --grep "force"     # Single scenario
npx playwright test --ui               # Interactive mode
```

---

## 11. Foundation vs Domain Layers

The workstation architecture cleanly separates **domain-agnostic foundation** (reusable across any XDS domain app) from **domain-specific configuration** (xftws-only). This means any future domain workstation (xodyssey, xorg, etc.) reuses the same foundation — only the YAML config and domain mappers change.

### 11.1 Server-Side Foundation (xdspy — domain-agnostic)

These are XDS engine capabilities configured by `assembly.yaml`, not built per-domain:

| Foundation Service           | Engine Provides                                     | Domain Configures (YAML only)                           |
| ---------------------------- | --------------------------------------------------- | ------------------------------------------------------- |
| **Workflow Engine**          | Schema-driven state machine, transition validation  | States, transitions, SLA timers in `workflow:`          |
| **Pipeline Executor**        | Step sequencing, retry, error handling              | Pipeline steps + bindings in `pipelines:`               |
| **Correlation Engine**       | Key matching, tolerance comparison, break detection | Rules + scenarios in `correlations:`                    |
| **Streaming Infrastructure** | WebSocket push, interval, op, key, limit            | Per-dataset streaming config in `datasets[].streaming:` |
| **RBAC Enforcer**            | Role-based dataset permissions, scope evaluation    | Roles + ACLs in `rbac:`                                 |
| **Field Encryption**         | DEK management, encrypt/decrypt per-field           | DEK assignments in `encryption:`                        |
| **Auth Policy**              | Ordered rule evaluation, JWT verification           | Policy rules in `auth_policy:`                          |
| **View Engine**              | Virtual computed datasets, joins                    | View definitions in `views:`                            |
| **Fixture Generator**        | `StaticFixtureGenerator`, system field injection    | Factory classes in `server/mock_data.py`                |
| **Contract Validator**       | Schema↔model consistency, startup gate              | Schemas in `schemas/*.yaml`                             |

**Key API endpoints (domain-agnostic)**:
- `PATCH /events/{id}/transition` — Workflow engine validates transition + fires pipeline
- `GET /events/{id}/chain` — Correlation engine returns linked event chain
- `GET /meta/datasets/{domain}.{dataset}` — Schema + field metadata
- `WS /ws/stream/{dataset}` — Streaming infrastructure pushes updates

**What does NOT exist in the engine yet** (extension points for domain services):
- Source transformers (FIX/FpML/SWIFT adapters)
- Enrichment services (risk, regulatory, settlement)
- Matching plugins (per-scenario custom logic beyond key matching)
- Break tolerance configuration (auto-resolution rules)

### 11.2 Client-Side Foundation (xdsuix — domain-agnostic)

These components work with ANY domain's data, configured via props:

| Layer            | Component / Module       | What It Does                                            | Domain Knows? |
| ---------------- | ------------------------ | ------------------------------------------------------- | ------------- |
| **Data Infra**   | `SpacesProvider`         | Zustand store + fixture/API loading + profile switching | No            |
|                  | `useDatasets()`          | Reactive access to any dataset's records                | No            |
|                  | `useSelectedProfile()`   | Current infra profile (fixture/mock/local)              | No            |
|                  | `useAppActions()`        | Store mutations (add/update/delete datasets)            | No            |
| **Grid**         | `AgGridWrapper`          | Virtualized data grid with column defs                  | No            |
| **Filtering**    | `SmartFilter`            | 24-operator filter builder with recursive groups        | No            |
| **Charts**       | `ChartControl`           | Recharts wrapper with type switching                    | No            |
| **Workflow**     | `WorkflowActions`        | Transition buttons computed from workflow config        | No            |
|                  | `TransitionDialog`       | Collect fields + confirm for a transition               | No            |
|                  | `WorkflowStatusBar`      | Status progression bar                                  | No            |
| **Pipeline Viz** | `WorkflowPills`          | Multi-stage lifecycle pill visualization                | No            |
|                  | `RevisionDiff`           | Field-level before/after diff                           | No            |
|                  | `EventTimeline`          | Vertical ordered event list                             | No            |
|                  | `ComparisonPanel`        | Side-by-side with break highlighting                    | No            |
|                  | `SplitProgress`          | Parent→child allocation progress                        | No            |
|                  | `LinkGraph`              | DAG visualization of linked records                     | No            |
| **Forms**        | `SchemaForm`             | Schema-driven form rendering                            | No            |
| **Commands**     | `CommandPaletteProvider` | Cmd+K quick actions                                     | No            |

**None of these components contain any domain-specific logic.** They receive data and config as props. The domain layer (§11.3) provides the config.

### 11.3 Domain Layer (xftws-specific)

This is the only layer that knows about fixed income trading concepts:

| Concern            | File                                | What It Does                                                   |
| ------------------ | ----------------------------------- | -------------------------------------------------------------- |
| **UI config**      | `domains/xftws/workstation.yaml`    | Workspaces, columns, filters, actions, lifecycle, scenarios    |
| **Backend config** | `domains/xftws/assembly.yaml`       | Datasets, correlations, workflow, pipelines, encryption        |
| **Schemas**        | `domains/xftws/schemas/*.yaml`      | Event schema, entity, book, fpml, enums                        |
| **Ontology**       | `domains/xftws/ontology.yaml`       | Entity defs, hierarchies, vocab, validators                    |
| **Factories**      | `domains/xftws/server/mock_data.py` | FK-wired fixture generation for 30 scenarios, 15 product types |
| **Data mappers**   | `apps/xftws/src/domain/mappers/`    | `transitionsToPills`, `linksToGraph`, `breaksToComparison`     |
| **Domain hooks**   | `apps/xftws/src/domain/hooks/`      | `useWorkflowPills`, `useEventChain`, `useMatchComparison`      |
| **Column configs** | `apps/xftws/src/domain/columns.ts`  | `getWorkspaceColumns()` reads from YAML                        |
| **Filter engine**  | `apps/xftws/src/domain/filters.ts`  | `applyAllFilters()` — 4 filter layers, all rules from YAML     |
| **Event detail**   | `apps/xftws/src/domain/detail/`     | Context-aware sidebar (lifecycle, comparison, chain modes)     |

### 11.4 Foundation ↔ Domain Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  SERVER FOUNDATION (xdspy)                                          │
│                                                                     │
│  assembly.yaml ──→ Workflow Engine ──→ validates transitions        │
│                ──→ Pipeline Executor ──→ runs steps                 │
│                ──→ Correlation Engine ──→ matches events            │
│                ──→ Streaming ──→ pushes to WS clients               │
│                ──→ RBAC ──→ enforces permissions                    │
│                ──→ Encryption ──→ encrypts/decrypts fields          │
│                                                                     │
│  schemas/*.yaml ──→ Contract Validator ──→ blocks startup if drift  │
│  server/mock_data.py ──→ StaticFixtureGenerator ──→ fixture JSON    │
├─────────────────────────────────────────────────────────────────────┤
│  CLIENT FOUNDATION (xdsuix)                                         │
│                                                                     │
│  SpacesProvider ──→ loads fixtures OR API data ──→ zustand store    │
│  useDatasets() ──→ events[], entities[], books[] ──→ grid + charts  │
│  AgGridWrapper ──→ renders filtered data with column defs           │
│  SmartFilter ──→ builds filter tree from standard + custom fields   │
│  Pipeline components ──→ visualize workflow/chain/comparison data   │
│  WorkflowActions ──→ renders buttons from assembly workflow config  │
├─────────────────────────────────────────────────────────────────────┤
│  DOMAIN LAYER (xftws-specific)                                      │
│                                                                     │
│  workstation.yaml ──→ workspace configs → column defs, filters,     │
│                       actions, status_filters, scenarios            │
│  domain/mappers/ ──→ transform event data → component props         │
│  domain/hooks/ ──→ memoized selectors for xftws-specific logic      │
│  domain/detail/ ──→ context-aware sidebar mode selection            │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.5 Building a New Domain Workstation (Recipe)

To build a workstation for another domain (e.g., xodyssey):

1. **Create `domains/xodyssey/workstation.yaml`** — define workspaces, status_filters, columns, actions
2. **Create `apps/xodyssey-ws/`** — new Vite app with same shell structure
3. **Write domain mappers** — transform xodyssey event shapes to component props
4. **Write domain hooks** — memoized selectors for xodyssey-specific logic
5. **Write domain detail** — context-aware sidebar for xodyssey event types
6. **Configure `assembly.yaml`** — workflow states, pipelines, correlations (server-side)
7. **Foundation components are already done** — AgGridWrapper, SmartFilter, pipeline/*, workflow/* just work

**Zero changes to xdsuix or xdspy required.** The foundation is complete.

---

## 12. Technology Dependencies

| Dependency          | Purpose          | In xdsuix? |
| ------------------- | ---------------- | ---------- |
| `ag-grid-react` v35 | Data grids       | Yes        |
| `recharts` v3       | Charts           | Yes        |
| `@radix-ui/react-*` | Dialogs, slots   | Yes        |
| `framer-motion` v11 | Animations       | Yes        |
| `zustand` v5        | State management | Yes        |
| `lucide-react`      | Icons            | Yes        |
| `playwright`        | E2E testing      | Dev dep    |

**No new dependencies needed.** All components exist in @xdsui/components. The app only adds Playwright as a dev dependency.

---

## 12. Build Status

### Library Layer (xdsuix) — COMPLETE

All pipeline components implemented and exported from `@xdsui/components/pipeline`:

| Component                   | Status | LOC |
| --------------------------- | ------ | --- |
| `WorkflowPills`             | Done   | 100 |
| `WorkflowPillsCellRenderer` | Done   | ~40 |
| `RevisionDiff`              | Done   | 173 |
| `EventTimeline`             | Done   | 219 |
| `ComparisonPanel`           | Done   | 205 |
| `SplitProgress`             | Done   | 167 |
| `LinkGraph`                 | Done   | 415 |

### App Layer (apps/xftws) — COMPLETE

| Task                                           | Status |
| ---------------------------------------------- | ------ |
| `workstation.yaml` (with lifecycle section)    | Done   |
| `UIX.md` rewrite                               | Done   |
| AppShell + AppHeader + StatusFilters           | Done   |
| useAppState hook                               | Done   |
| App.tsx rewrite (SpacesProvider, no SpacesApp) | Done   |
| Vite YAML plugin (virtual:workstation-config)  | Done   |
| workstationConfig.ts types + virtual import    | Done   |
| BlotterView (YAML-driven columns + filters)    | Done   |
| AnalyticsView (YAML-driven charts)             | Done   |
| domain/columns.ts (from YAML)                  | Done   |
| domain/filters.ts (4-layer, from YAML)         | Done   |
| scenarioLabels → YAML (lifecycle section)      | Done   |
| status colors → YAML (lifecycle.status_colors) | Done   |
| EventDetail (lifecycle/comparison/chain modes) | Done   |
| Domain hooks (pills, chain, comparison)        | Done   |
| Domain mappers (pills, graph, comparison)      | Done   |
| Playwright config + scenario tests             | Done   |
| Typecheck: zero errors                         | Done   |
