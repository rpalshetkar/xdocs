"""xftws demo factories — unified event-centric data generation.

Produces 4 datasets matching assembly.yaml:
  entities  — legal entities, trading desks, CCPs, brokers (reference)
  books     — trading books/portfolios (reference)
  fpmls     — ISDA FpML product templates (reference)
  events    — THE unified event log (all 20 event types, scenario-linked)

Events are generated as realistic trading scenarios — chains of causally
linked events that mirror real fixed income desk workflows:

  Pre-trade / execution:
    RFQ_HIT           — CLIENT_RFQ v1→QUOTE v1→CLIENT_RFQ v2→QUOTE v2→CLIENT_RFQ v3(ACCEPTED)→TRADE
    BACK_TO_BACK      — CLIENT_TRADE + INTERNAL_TRANSFER + STREET_HEDGE (x2-3)
    TRADE_CONFIRM     — SALES_BOOKING → AFFIRM_MSG from counterparty
    STP_AUTO          — STP_MESSAGE → TRADE
    BROKER_EXEC       — ORDER → BROKER_FILL (x2-3 separate) → TRADING_BOOKING → TRADE
    OBO_CLIENT        — OBO_TICKET → SALES_BOOKING → TRADE
    GIVEUP            — GIVEUP_NOTICE → GIVEUP_ACCEPT → TRADE
    DISPUTE           — SALES_BOOKING + TRADING_BOOKING matched then disputed

  Pre-trade expansion:
    AXE_TO_RFQ        — Dealer AXE → client RFQ → QUOTE → accept → TRADE
    AXE_WITHDRAW      — AXE(LIVE) → AXE(WITHDRAWN)
    OUTBOUND_RFQ_HIT  — Our desk sends RFQ to venue → QUOTE → accept → TRADE
    OUTBOUND_RFQ_MISS — Our desk sends RFQ → QUOTE → TRADED_AWAY
    STREAMING_QUOTE   — 3 streaming QUOTE updates (v1→v2→v3 expired)
    STREAM_TO_TRADE   — Streaming QUOTE → client hits → TRADE
    STREAM_TO_RFQ     — Streaming QUOTE → RFQ(firm) → QUOTE(FIRM) → accept → TRADE

  Spread / benchmark:
    SPREAD_RFQ        — IRS RFQ with benchmark+spread → QUOTE(all_in_rate) → TRADE
    IMM_FIXING_RFQ    — IRS RFQ → QUOTE(PENDING fixing) → QUOTE(FIXED) → TRADE

  Direct clearing:
    DIRECT_CLEARING   — TRADE → CLEARING_SUBMISSION(PENDING→ACCEPTED) → CLEARING_MSG → MARGIN_CALL
    CLEARING_REJECTED — TRADE → CLEARING_SUBMISSION(PENDING→REJECTED)

  Bond auction:
    BOND_AUCTION_FULL    — AUCTION_BID(OPEN→AWARDED 100%) → SETTLEMENT_INSTR
    BOND_AUCTION_PARTIAL — AUCTION_BID(OPEN→AWARDED <100%)
    BOND_AUCTION_MISS    — AUCTION_BID(OPEN→MISSED, 0% allotment)

  China Connect:
    BOND_CONNECT_BUY     — RFQ(BOND_CONNECT) → QUOTE(CNY) → TRADE → CLEARING_MSG(SHCH)
    BOND_CONNECT_SELL    — RFQ(BOND_CONNECT) → QUOTE → TRADE → SETTLEMENT_INSTR(CMU)
    SWAP_CONNECT         — RFQ(SWAP_CONNECT, IRS) → QUOTE(FR007/LPR) → TRADE → CLEARING(SHCH)
    SWAP_CONNECT_REJECT  — RFQ → TRADE → CLEARING_SUBMISSION(REJECTED by SHCH)

  Asset-class specific:
    FX_COMPENSATION   — Import/export facility draws + compensation netting
    IRS_CLEARING      — SEF execution + CCP novation
    BOND_BROKER_EXEC  — D2C/voice bond execution
    FX_OPTION_HEDGE   — Client option hedging

  Post-trade / recon:
    SETTLEMENT_RECON  — Settlement instruction vs cleared trade
    EOD_POSITION      — Position snapshots from different sources
    MARGIN_RECON      — Margin call vs computed exposure
    REGULATORY_RECON  — Regulatory vs internal position snapshots
    COMPRESSION       — Trade compression (N→1)

Post-trade events (clearing, affirm, settlement, risk, schedules, amendments,
allocations, margin, netting, position snapshots) are layered on top.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from pathlib import Path

import factory
import yaml
from shared.fixture_context import FixtureContext

logger = logging.getLogger(__name__)


# =============================================================================
# SCHEMA QUALIFIER LOADING
# =============================================================================


def _load_qualifiers() -> dict[str, str]:
    """Load qualifier strings from schema YAML files."""
    schemas_dir = Path(__file__).parent.parent / "schemas"
    qualifiers: dict[str, str] = {}
    if not schemas_dir.exists():
        return qualifiers
    for schema_file in schemas_dir.glob("*.yaml"):
        if schema_file.name.startswith("_"):
            continue
        try:
            with open(schema_file) as f:
                config = yaml.safe_load(f)
            if config and isinstance(config, dict) and "qualifier" in config:
                qualifiers[schema_file.stem] = config["qualifier"]
        except Exception:
            pass
    return qualifiers


QUALIFIERS = _load_qualifiers()

# =============================================================================
# CONSTANTS
# =============================================================================

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "SGD", "HKD", "INR"]
NDF_CURRENCIES = ["CNY", "BRL", "MXN", "KRW", "TWD"]
PRODUCT_TYPES = [
    "FX_SPOT",
    "FX_FORWARD",
    "FX_SWAP",
    "FX_NDF",
    "FX_OPTION",
    "IRS",
    "XCCY_SWAP",
    "SWAPTION",
    "FRA",
    "BOND",
    "BOND_FUTURE",
    "REPO",
    "CDS",
    "TRS",
    "EQUITY",
]
DIRECTIONS = ["PAY", "RECEIVE"]
REGIONS = ["US", "EU", "APAC"]
DESKS = [
    "FX Spot",
    "FX Options",
    "Rates Trading",
    "Credit Trading",
    "EM Rates",
    "G10 Rates",
    "Repo Desk",
    "Equity Trading",
    "Structured Products",
]
STRATEGIES = ["Market Making", "Flow", "Prop", "Client Hedging", "Structured"]
METRICS = [
    "MTM",
    "DV01",
    "FXDELTA",
    "FXVEGA",
    "VEGA",
    "FIXING",
    "THETA",
    "GAMMA",
    "RHO",
]
TENOR_BUCKETS = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
ENTITY_TYPES = ["LEGAL_ENTITY", "TRADING_DESK", "BRANCH", "CCP", "BROKER"]
INDICES = ["SOFR", "EURIBOR", "SONIA", "TIBOR", "BBSW", "CDOR"]
DAY_COUNTS = ["ACT/360", "ACT/365", "30/360", "ACT/ACT"]
CCPS = ["LCH", "CME", "JSCC", "EUREX", "ICE"]
FEE_TYPES = ["BROKERAGE", "COMMISSION", "UPFRONT", "CLEARING", "EXECUTION"]
AMENDMENT_TYPES = ["ECONOMIC", "NED", "CANCEL", "REBOOK"]
RISK_FLAGS = [
    "LARGE_NOTIONAL",
    "CONCENTRATION_RISK",
    "NEW_COUNTERPARTY",
    "LIMIT_BREACH",
    "UNUSUAL_TENOR",
    "OFF_MARKET_PRICE",
]
PRIORITIES = ["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"]

ENTITY_NAMES = [
    ("Global Markets LLC", "GMLC"),
    ("Pacific Trading Corp", "PTC"),
    ("Atlantic Securities", "ATLS"),
    ("Summit Capital Partners", "SCP"),
    ("Meridian Financial", "MFIN"),
    ("Apex Trading Desk", "APEX"),
    ("Nordic Securities AB", "NSAB"),
    ("Eastern Bridge Capital", "EBC"),
    ("Pinnacle Markets", "PNMK"),
    ("Vanguard OTC", "VOTC"),
    ("LCH Clearnet", "LCH"),
    ("CME Clearing", "CME"),
    ("Deutsche Boerse AG", "DBAG"),
    ("HSBC Markets", "HSBC"),
    ("JP Morgan Securities", "JPM"),
    ("Barclays Capital", "BARC"),
    ("Citibank NA", "CITI"),
    ("Goldman Sachs Intl", "GSI"),
    ("Morgan Stanley Intl", "MSI"),
    ("BNP Paribas SA", "BNPP"),
]

TRADER_NAMES = [
    "J. Smith",
    "A. Chen",
    "M. Kumar",
    "S. Nakamura",
    "R. Mueller",
    "L. Thompson",
    "K. Patel",
    "D. Rodriguez",
    "T. Yamamoto",
    "P. Dubois",
]
SALES_NAMES = [
    "M. Jones",
    "H. Williams",
    "R. Singh",
    "C. Tanaka",
    "E. Fischer",
    "B. Anderson",
    "N. Sharma",
    "F. Garcia",
    "W. Suzuki",
    "J. Martin",
]

# Source → protocol mapping (realistic combinations)
SOURCE_PROTOCOL = {
    "BLOOMBERG": "FIX",
    "TRADEWEB": "FIX",
    "MARKITWIRE": "FPML",
    "DTCC": "FPML",
    "LCH": "FPML",
    "CME": "FIX",
    "ICE": "FIX",
    "BROKER": "FIX",
    "STP_PIPELINE": "SWIFT_MT",
    "CLIENT": "REST",
    "MANUAL": "INTERNAL",
    "MATCHING_ENG": "INTERNAL",
    "NETTING_ENG": "INTERNAL",
    "BLOOMBERG_CHAT": "FIX",
    "SYMPHONY": "REST",
    "CFETS": "FIX",
    "SHCH": "FPML",
    "CMU": "SWIFT_MT",
}

# Per-scenario TTL rules: (from_event_type, expected_event_type, ttl_minutes)
SCENARIO_TTLS: dict[str, list[tuple[str, str, int]]] = {
    "RFQ_HIT": [("RFQ", "QUOTE", 2), ("QUOTE", "TRADE", 5)],
    "RFQ_MISS": [("RFQ", "QUOTE", 2)],
    "COMPETITIVE_RFQ": [("RFQ", "QUOTE", 2), ("QUOTE", "TRADE", 10)],
    "SALES_DIRECT": [("SALES_BOOKING", "TRADING_ACCEPT", 60), ("TRADING_ACCEPT", "TRADE", 15)],
    "TRADER_FIRST": [("TRADING_BOOKING", "SALES_BOOKING", 60)],
    "BACK_TO_BACK": [("TRADE", "INTERNAL_TRANSFER", 30)],
    "STP_AUTO": [("STP_MESSAGE", "TRADE", 5)],
    "BROKER_EXEC": [("ORDER", "BROKER_FILL", 15)],
    "BOND_BROKER_EXEC": [("ORDER", "BROKER_FILL", 15)],
    "_default": [("TRADE", "CLEARING_MSG", 240), ("TRADE", "SETTLEMENT_INSTR", 1440)],
}

# Event-type → actor_role fallback for events missing explicit assignment
_ACTOR_ROLE_FALLBACK: dict[str, str] = {
    "RFQ": "CLIENT",
    "QUOTE": "TRADING",
    "TRADE": "SYSTEM",
    "SALES_BOOKING": "SALES",
    "TRADING_BOOKING": "TRADING",
    "TRADING_ACCEPT": "TRADING",
    "OBO_TICKET": "SALES",
    "ORDER": "TRADING",
    "BROKER_FILL": "BROKER",
    "STP_MESSAGE": "SYSTEM",
    "INTERNAL_TRANSFER": "TRADING",
    "GIVEUP_NOTICE": "BROKER",
    "GIVEUP_ACCEPT": "OPS",
    "MATCH": "SYSTEM",
    "UNMATCH": "SYSTEM",
    "CLEARING_MSG": "CCP",
    "AFFIRM_MSG": "OPS",
    "SETTLEMENT_INSTR": "OPS",
    "CANCEL_REQUEST": "TRADING",
    "CANCEL_CONFIRM": "SYSTEM",
    "NOVATION_REQUEST": "TRADING",
    "NOVATION_ACCEPT": "OPS",
    "EXERCISE_NOTICE": "TRADING",
    "RISK_MEASURE": "SYSTEM",
    "MARGIN_CALL": "CCP",
    "POSITION_SNAPSHOT": "SYSTEM",
    "SCHEDULE_EVENT": "SYSTEM",
    "ALLOC_SPLIT": "OPS",
    "AMENDMENT": "TRADING",
    "NET_SETTLEMENT": "SYSTEM",
    "FX_COMPENSATION": "TRADING",
    "COMPRESSION_REQUEST": "TRADING",
    "COMPRESSION_RESULT": "SYSTEM",
    "ROLL_REQUEST": "TRADING",
    "ROLL_CONFIRM": "SYSTEM",
    "AXE": "TRADING",
    "AUCTION_BID": "TRADING",
    "CLEARING_SUBMISSION": "OPS",
}


def _apply_sla_deadlines(chain: list[dict[str, Any]], scenario_name: str) -> None:
    """Set sla_deadline on events based on scenario TTL rules."""
    ttl_rules = SCENARIO_TTLS.get(scenario_name, []) + SCENARIO_TTLS.get("_default", [])
    for evt in chain:
        event_type = evt["event_type"]
        for from_type, _expect_type, ttl_mins in ttl_rules:
            if event_type == from_type:
                created = evt.get("created_at")
                if created:
                    try:
                        ts = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
                        evt["sla_deadline"] = (ts + timedelta(minutes=ttl_mins)).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except (ValueError, TypeError):
                        pass
                break  # Only first matching rule


# Product → leg configuration (realistic per asset class)
PRODUCT_LEG_MAP: dict[str, list[tuple[str, str]]] = {
    "FX_SPOT": [("SPOT", "PAY"), ("SPOT", "RECEIVE")],
    "FX_FORWARD": [("FORWARD", "PAY"), ("FORWARD", "RECEIVE")],
    "FX_SWAP": [("NEAR", "PAY"), ("FAR", "RECEIVE")],
    "FX_NDF": [("FORWARD", "PAY"), ("FORWARD", "RECEIVE")],
    "FX_OPTION": [("OPTION", "PAY"), ("FEE", "RECEIVE")],
    "IRS": [("FIXED", "PAY"), ("FLOAT", "RECEIVE")],
    "XCCY_SWAP": [("FIXED", "PAY"), ("FLOAT", "RECEIVE")],
    "SWAPTION": [("OPTION", "PAY"), ("FEE", "RECEIVE")],
    "FRA": [("FRA", "PAY")],
    "BOND": [("FIXED", "PAY")],
    "BOND_FUTURE": [("FUTURE", "PAY")],
    "REPO": [("REPO", "PAY"), ("COLLATERAL", "RECEIVE")],
    "CDS": [("PROTECTION", "PAY"), ("PREMIUM", "RECEIVE")],
    "TRS": [("TOTAL_RETURN", "PAY"), ("FINANCING", "RECEIVE")],
    "EQUITY": [("CASH", "PAY")],
}

# Realistic FX pairs — majors, crosses, EM
FX_MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
FX_CROSS_PAIRS = ["EURGBP", "EURJPY", "GBPJPY", "AUDNZD", "EURCHF"]
NDF_PAIRS = ["USDCNY", "USDBRL", "USDKRW", "USDTWD", "USDMXN", "USDINR"]

# Realistic rate ranges per product
RATE_RANGES: dict[str, tuple[float, float]] = {
    "FX_SPOT": (0.6, 1.6),  # spot rates
    "FX_FORWARD": (0.6, 1.6),  # forward rates (spot + points)
    "FX_SWAP": (0.6, 1.6),  # near/far rates
    "FX_NDF": (5.0, 80.0),  # EM ccy rates (e.g. USDCNY ~7, USDBRL ~5)
    "FX_OPTION": (0.7, 1.4),  # strike prices
    "IRS": (2.5, 5.5),  # swap rates
    "XCCY_SWAP": (2.0, 5.0),  # cross-ccy swap rates
    "SWAPTION": (2.5, 5.5),  # swaption strike rates
    "FRA": (3.0, 6.0),  # FRA contract rates
    "BOND": (3.0, 7.0),  # bond yields
    "BOND_FUTURE": (95.0, 135.0),  # futures price (per 100 face)
    "REPO": (4.0, 6.0),  # repo rates (annualized %)
    "CDS": (20.0, 500.0),  # CDS spread in bps
    "TRS": (0.01, 0.05),  # financing spread (SOFR+ bps as decimal)
    "EQUITY": (10.0, 500.0),  # share price
}

# Realistic notional ranges per product (USD equivalent)
NOTIONAL_RANGES: dict[str, tuple[float, float]] = {
    "FX_SPOT": (500_000, 100_000_000),
    "FX_FORWARD": (1_000_000, 200_000_000),
    "FX_SWAP": (5_000_000, 500_000_000),
    "FX_NDF": (1_000_000, 100_000_000),
    "FX_OPTION": (1_000_000, 75_000_000),
    "IRS": (5_000_000, 500_000_000),
    "XCCY_SWAP": (10_000_000, 500_000_000),
    "SWAPTION": (10_000_000, 300_000_000),
    "FRA": (5_000_000, 200_000_000),
    "BOND": (1_000_000, 50_000_000),
    "BOND_FUTURE": (1_000_000, 100_000_000),
    "REPO": (10_000_000, 500_000_000),
    "CDS": (5_000_000, 100_000_000),
    "TRS": (5_000_000, 200_000_000),
    "EQUITY": (100_000, 50_000_000),
}

# IRS tenor configurations
IRS_TENORS = ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
IRS_FREQUENCIES = {"FIXED": ["3M", "6M", "1Y"], "FLOAT": ["1M", "3M"]}

# Bond coupon frequencies
BOND_COUPONS = ["SEMI", "ANNUAL", "QUARTERLY"]

# FX swap tenors
FX_SWAP_TENORS = ["O/N", "T/N", "S/N", "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y"]

# FRA periods (start x end in months)
FRA_PERIODS = ["1x4", "3x6", "3x9", "6x9", "6x12", "9x12", "12x18"]

# Cross-currency swap benchmarks
XCCY_BENCHMARKS: dict[str, dict[str, str]] = {
    "USD": {"index": "SOFR", "dc": "ACT/360"},
    "EUR": {"index": "EURIBOR", "dc": "ACT/360"},
    "GBP": {"index": "SONIA", "dc": "ACT/365"},
    "JPY": {"index": "TIBOR", "dc": "ACT/360"},
}

# Swaption tenors (option expiry x underlying tenor)
SWAPTION_EXPIRIES = ["1M", "3M", "6M", "1Y", "2Y", "5Y"]
SWAPTION_UNDERLYINGS = ["2Y", "5Y", "10Y", "20Y", "30Y"]

# Bond futures contracts
_BOND_FUTURES = [
    ("ZN", "CBOT", "US 10Y Note Future", 100_000),
    ("ZB", "CBOT", "US Long Bond Future", 100_000),
    ("ZF", "CBOT", "US 5Y Note Future", 100_000),
    ("RX", "EUREX", "Euro-Bund Future", 100_000),
    ("OAT", "EUREX", "Euro-OAT Future", 100_000),
    ("JB", "OSE", "JGB 10Y Future", 100_000_000),
    ("R", "ICE", "UK Long Gilt Future", 100_000),
]

# Cheapest-to-deliver ISINs for bond futures
_CTD_ISINS = [
    "US912810TT08",
    "US912810RZ53",
    "US912810SV08",
    "DE0001102580",
    "FR0014007TZ9",
    "JP1201551L51",
    "GB00BN65R198",
]

# Repo collateral types
_REPO_COLLATERAL = [
    ("UST", "US Treasury", "US912810TT08"),
    ("GILT", "UK Gilt", "GB00BN65R198"),
    ("BUND", "German Bund", "DE0001102580"),
    ("JGB", "Japan JGB", "JP1201551L51"),
    ("AGENCY", "US Agency MBS", "US31398VJ210"),
]

# CDS reference entities
_CDS_ENTITIES = [
    ("Ford Motor Co", "FORD", "FORD-SNR-USD", "BBB-"),
    ("General Electric", "GE", "GE-SNR-USD", "BBB+"),
    ("AT&T Inc", "T", "T-SNR-USD", "BBB"),
    ("Boeing Co", "BA", "BA-SNR-USD", "BBB-"),
    ("Volkswagen AG", "VOW", "VOW-SNR-EUR", "BBB+"),
    ("Deutsche Bank AG", "DB", "DB-SNR-EUR", "BBB+"),
    ("Barclays PLC", "BARC", "BARC-SNR-GBP", "A-"),
    ("SoftBank Group", "SFTBY", "SFTBY-SNR-JPY", "BB+"),
]
CDS_RESTRUCTURING = ["CR", "MR", "MM", "XR"]
CDS_SENIORITY = ["SENIOR_UNSECURED", "SUBORDINATED", "SENIOR_SECURED"]

# TRS underlyings
_TRS_UNDERLYINGS = [
    ("SPX", "S&P 500 Index", "USD"),
    ("SX5E", "Euro Stoxx 50", "EUR"),
    ("NKY", "Nikkei 225", "JPY"),
    ("UKX", "FTSE 100", "GBP"),
    ("AAPL US", "Apple Inc", "USD"),
    ("MSFT US", "Microsoft Corp", "USD"),
    ("NVDA US", "NVIDIA Corp", "USD"),
    ("7203 JP", "Toyota Motor", "JPY"),
]

# Equity tickers
_EQUITY_TICKERS = [
    ("AAPL", "NASDAQ", "Apple Inc", "USD"),
    ("MSFT", "NASDAQ", "Microsoft Corp", "USD"),
    ("NVDA", "NASDAQ", "NVIDIA Corp", "USD"),
    ("AMZN", "NASDAQ", "Amazon.com Inc", "USD"),
    ("JPM", "NYSE", "JPMorgan Chase", "USD"),
    ("SHEL", "LSE", "Shell PLC", "GBP"),
    ("SAP", "XETRA", "SAP SE", "EUR"),
    ("7203", "TSE", "Toyota Motor Corp", "JPY"),
    ("9988", "HKEX", "Alibaba Group", "HKD"),
    ("RELIANCE", "NSE", "Reliance Industries", "INR"),
]


# =============================================================================
# HELPERS
# =============================================================================


def _gen_id(schema_or_prefix: str) -> str:
    """Generate a qualified ID using qualifier from schema config.

    Accepts a schema name (e.g. "entity", "event") and looks up its
    qualifier from the schema YAML. The qualifier already includes its
    separator (e.g. "fte-"), so we just prepend it.
    """
    qualifier = QUALIFIERS.get(schema_or_prefix, "")
    return f"{qualifier}{uuid.uuid4().hex[:8].upper()}"


def _random_date(start_days: int = -90, end_days: int = 365) -> str:
    base = datetime.now() + timedelta(days=random.randint(start_days, end_days))
    return base.strftime("%Y-%m-%d")


def _random_datetime(start_days: int = -90, end_days: int = 0) -> str:
    base = datetime.now() + timedelta(
        days=random.randint(start_days, end_days),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _offset_minutes(base_ts: str, min_min: int, max_min: int) -> str:
    """Return a timestamp offset by a random number of minutes from base_ts."""
    base = datetime.strptime(base_ts, "%Y-%m-%dT%H:%M:%SZ")
    return (base + timedelta(minutes=random.randint(min_min, max_min))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ── Realistic timing for event chains ──────────────────────────────────────
# Maps event_type to (min_seconds, max_seconds) delay from previous event.
# These represent realistic fixed income workflow timing.
EVENT_TYPE_DELAYS: dict[str, tuple[int, int]] = {
    # Pre-trade (seconds — fast electronic flow)
    "RFQ": (0, 5),
    "CLIENT_RFQ": (0, 5),
    "QUOTE": (15, 45),           # trader responds in 15-45s
    "ORDER": (5, 15),
    "BROKER_FILL": (30, 180),    # 30s-3min to fill
    "OBO_TICKET": (10, 30),
    "STP_MESSAGE": (1, 5),       # automated wire
    "GIVEUP_NOTICE": (30, 120),
    "GIVEUP_ACCEPT": (60, 300),
    # Booking (seconds-minutes — human data entry)
    "SALES_BOOKING": (30, 120),
    "TRADING_BOOKING": (45, 180),
    "TRADING_ACCEPT": (30, 90),
    "INTERNAL_TRANSFER": (10, 60),
    # Matching/Materialization
    "MATCH": (5, 15),
    "UNMATCH": (5, 15),
    "TRADE": (10, 30),           # matching engine confirms in 10-30s
    # Post-trade (minutes-hours — external/batch)
    "CLEARING_MSG": (120, 600),  # 2-10 min (CCP processing)
    "AFFIRM_MSG": (300, 1800),   # 5-30 min (counterparty platform)
    "ALLOC_SPLIT": (60, 300),    # 1-5 min
    "AMENDMENT": (300, 1800),    # 5-30 min (human review)
    "SETTLEMENT_INSTR": (600, 3600),  # 10-60 min
    "NET_SETTLEMENT": (1800, 7200),   # 30min-2hr (netting batch)
    "MARGIN_CALL": (3600, 14400),     # 1-4 hr
    "POSITION_SNAPSHOT": (7200, 28800),  # 2-8 hr (EOD)
    "RISK_MEASURE": (30, 120),   # 30s-2min (quant engine)
    "SCHEDULE_EVENT": (60, 600),
    # Lifecycle
    "CANCEL_REQUEST": (60, 600),
    "CANCEL_CONFIRM": (30, 300),
    "NOVATION_REQUEST": (120, 900),
    "NOVATION_ACCEPT": (60, 600),
    "EXERCISE_NOTICE": (60, 300),
    "AXE": (0, 1),
    "AUCTION_BID": (0, 5),
    "CLEARING_SUBMISSION": (60, 300),
}


def _chain_timestamps(chain: list[dict[str, Any]], base: datetime | None = None) -> None:
    """Overwrite created_at/updated_at on all events in a chain with sequential
    realistic timestamps. Events are assumed to be in causal order (append order).

    Also patches raw.received_at and transitions[0].at to match.
    """
    cursor = base or (datetime.now() - timedelta(minutes=random.randint(5, 120)))

    for evt in chain:
        et = evt["event_type"]
        lo, hi = EVENT_TYPE_DELAYS.get(et, (10, 60))
        cursor += timedelta(seconds=random.randint(lo, hi))

        ts = cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        evt["created_at"] = ts
        evt["updated_at"] = ts

        # Patch raw.received_at
        raw = evt.get("raw")
        if isinstance(raw, dict):
            raw["received_at"] = ts

        # Patch first transition timestamp
        transitions = evt.get("transitions")
        if isinstance(transitions, list) and transitions:
            transitions[0]["at"] = ts


def _uti() -> str:
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=32))


def _lei() -> str:
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=20))


def _pick_ccy_pair(product_type: str) -> tuple[str, str, str | None]:
    """Return (ccy, far_ccy, ccy_pair) appropriate for product type."""
    if product_type in ("FX_SPOT", "FX_FORWARD", "FX_SWAP"):
        pair = random.choice(FX_MAJOR_PAIRS + FX_CROSS_PAIRS)
        return pair[:3], pair[3:], pair
    if product_type == "FX_NDF":
        pair = random.choice(NDF_PAIRS)
        return pair[:3], pair[3:], pair
    if product_type == "FX_OPTION":
        pair = random.choice(FX_MAJOR_PAIRS)
        return pair[:3], pair[3:], pair
    if product_type == "XCCY_SWAP":
        # Two different currencies
        pay_ccy = random.choice(["USD", "EUR", "GBP"])
        recv_pool = [c for c in ["USD", "EUR", "GBP", "JPY"] if c != pay_ccy]
        recv_ccy = random.choice(recv_pool)
        return pay_ccy, recv_ccy, f"{pay_ccy}{recv_ccy}"
    if product_type in ("IRS", "SWAPTION", "FRA"):
        ccy = random.choice(["USD", "EUR", "GBP", "JPY"])
        return ccy, ccy, None
    if product_type in ("BOND", "BOND_FUTURE", "REPO"):
        ccy = random.choice(["USD", "EUR", "GBP"])
        return ccy, ccy, None
    if product_type == "CDS":
        entity = random.choice(_CDS_ENTITIES)
        ccy = "USD" if "USD" in entity[2] else ("EUR" if "EUR" in entity[2] else "GBP")
        return ccy, ccy, None
    if product_type == "TRS":
        underlying = random.choice(_TRS_UNDERLYINGS)
        return underlying[2], underlying[2], None
    if product_type == "EQUITY":
        ticker = random.choice(_EQUITY_TICKERS)
        return ticker[3], ticker[3], None
    # Fallback
    ccy = random.choice(["USD", "EUR", "GBP"])
    return ccy, ccy, None


def _pick_ndf_pair() -> tuple[str, str, str]:
    """NDF pair with restricted currency."""
    pair = random.choice(NDF_PAIRS)
    return pair[:3], pair[3:], pair


def _notional_for(product_type: str) -> float:
    lo, hi = NOTIONAL_RANGES.get(product_type, (500_000, 50_000_000))
    return round(random.uniform(lo, hi), 2)


def _rate_for(product_type: str) -> float:
    lo, hi = RATE_RANGES.get(product_type, (0.5, 5.0))
    return round(random.uniform(lo, hi), 6)


# =============================================================================
# REFERENCE DATA FACTORIES
# =============================================================================


def _generate_entity_xmeta() -> dict[str, Any]:
    return {
        "credit_rating": random.choice(["AAA", "AA+", "AA", "A+", "A", "BBB+", "BBB"]),
        "rating_agency": random.choice(["S&P", "Moody's", "Fitch"]),
        "netting_eligible": random.choice([True, False]),
        "csa_agreement": random.choice([True, False]),
        "jurisdiction": random.choice(["US", "UK", "EU", "SG", "HK", "JP"]),
    }


class EntityFactory(factory.Factory):
    class Meta:
        model = dict

    entity_id = factory.LazyFunction(lambda: _gen_id("entity"))
    entity_type = factory.LazyFunction(lambda: random.choice(ENTITY_TYPES))
    name = None
    short_name = None
    lei = factory.LazyFunction(_lei)
    funding_ccy = factory.LazyFunction(lambda: random.choice(CURRENCIES[:5]))
    settlement_ccys = factory.LazyFunction(
        lambda: random.sample(CURRENCIES[:8], k=random.randint(2, 5)),
    )
    default_ssi_id = factory.LazyFunction(lambda: _gen_id("event"))
    parent_entity_id = None
    subsidiaries = factory.LazyFunction(lambda: [])
    status = "ACTIVE"
    contacts = factory.LazyFunction(lambda: [
        {
            "contact_type": random.choice(["OPS", "LEGAL", "TRADING", "SETTLEMENT", "COMPLIANCE", "PRIMARY"]),
            "name": f"{random.choice(['John', 'Sarah', 'Mike', 'Lisa', 'James'])} {random.choice(['Smith', 'Chen', 'Patel', 'Garcia', 'Kim'])}",
            "email": f"{uuid.uuid4().hex[:6]}@example.com",
            "phone": f"+1{random.randint(2000000000, 9999999999)}",
            "primary": True,
        },
        {
            "contact_type": random.choice(["OPS", "SETTLEMENT", "COMPLIANCE"]),
            "name": f"{random.choice(['Anna', 'David', 'Emma', 'Robert', 'Yuki'])} {random.choice(['Lee', 'Brown', 'Kumar', 'Martinez', 'Tanaka'])}",
            "email": f"{uuid.uuid4().hex[:6]}@example.com",
            "phone": f"+1{random.randint(2000000000, 9999999999)}",
            "primary": False,
        },
    ])
    addresses = factory.LazyFunction(lambda: [
        {
            "address_type": "REGISTERED",
            "line1": f"{random.randint(1, 999)} {random.choice(['Broadway', 'Park Ave', 'Wall St', 'Canary Wharf', 'Fleet St'])}",
            "line2": f"Floor {random.randint(1, 50)}",
            "city": random.choice(["New York", "London", "Singapore", "Hong Kong", "Tokyo"]),
            "state": random.choice(["NY", "LDN", "SG", "HK", "TK"]),
            "postal_code": f"{random.randint(10000, 99999)}",
            "country": random.choice(["US", "GB", "SG", "HK", "JP"]),
        },
    ])
    xmeta = factory.LazyFunction(_generate_entity_xmeta)


class BookFactory(factory.Factory):
    class Meta:
        model = dict

    book_id = factory.LazyFunction(lambda: _gen_id("book"))
    entity_id = None
    name = factory.LazyFunction(
        lambda: f"{random.choice(DESKS)} - {random.choice(REGIONS)}",
    )
    desk = factory.LazyFunction(lambda: random.choice(DESKS))
    region = factory.LazyFunction(lambda: random.choice(REGIONS))
    strategy = factory.LazyFunction(lambda: random.choice(STRATEGIES))
    status = "ACTIVE"
    currency = factory.LazyFunction(lambda: random.choice(CURRENCIES[:5]))
    risk_limit = factory.LazyFunction(
        lambda: round(random.uniform(1_000_000, 100_000_000), 0),
    )


class FPMLFactory(factory.Factory):
    class Meta:
        model = dict

    fpml_id = None
    product_type = None
    description = None
    leg_types = factory.LazyFunction(lambda: [])
    required_fields = factory.LazyFunction(lambda: {})
    validation_rules = factory.LazyFunction(lambda: [])
    template = factory.LazyFunction(lambda: {})


# =============================================================================
# EVENT BUILDER
# =============================================================================


class _EventSeq:
    """Global event sequence counter."""

    _n = 0

    @classmethod
    def next(cls, event_type: str) -> str:
        cls._n += 1
        return f"EVT-{event_type}-{cls._n:04d}"

    @classmethod
    def reset(cls) -> None:
        cls._n = 0


def _make_event(
    event_type: str,
    *,
    status: str = "ACTIVE",
    source: str = "MANUAL",
    actor: str | None = None,
    desk: str | None = None,
    payload: dict[str, Any],
    product_type: str | None = None,
    notional: float | None = None,
    ccy: str | None = None,
    cpty_id: str | None = None,
    links: list[dict[str, Any]] | None = None,
    correlation: dict[str, Any] | None = None,
    transitions: list[dict[str, Any]] | None = None,
    raw: dict[str, Any] | None = None,
    enriched: dict[str, Any] | None = None,
    created_at: str | None = None,
    priority: str = "NORMAL",
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build a single event record matching event.yaml schema."""
    eid = _EventSeq.next(event_type)
    protocol = SOURCE_PROTOCOL.get(source, "INTERNAL")
    ts = created_at or _random_datetime(-60, 0)

    return {
        "event_id": eid,
        "event_type": event_type,
        "status": status,
        "version": 1,
        "source": source,
        "source_ref": f"{source[:3]}-{uuid.uuid4().hex[:12].upper()}",
        "protocol": protocol,
        "actor": actor or random.choice(TRADER_NAMES),
        "desk": desk or random.choice(DESKS),
        "thread_id": thread_id,
        "raw": raw
        or {
            "format": protocol if protocol != "REST" else "JSON",
            "version": {
                "FIX": "4.4",
                "FPML": "5.12",
                "SWIFT_MT": "MT300",
                "INTERNAL": "1.0",
            }.get(protocol, "1.0"),
            "content": {},
            "raw_text": None,
            "received_at": ts,
            "checksum": uuid.uuid4().hex,
            "source_msg_id": f"{source[:3]}-MSG-{uuid.uuid4().hex[:8].upper()}",
        },
        "payload": payload,
        "enriched": enriched,
        "product_type": product_type,
        "notional": notional,
        "ccy": ccy,
        "cpty_id": cpty_id,
        "links": links or [],
        "correlation": {
            "chain_id": None,
            "match_type": None,
            "scenario": None,
            "match_status": None,
            "cardinality": None,
            "direction": None,
            "actor_role": None,
            "breaks": None,
            "resolution": None,
            "matched_at": None,
            "matched_by": None,
            **(correlation or {}),
        } if correlation is not None else None,
        "transitions": transitions
        or [
            {
                "from_status": "PENDING",
                "to_status": status,
                "at": ts,
                "by": "SYSTEM",
                "reason": "Created",
                "diff": {},
            },
        ],
        "created_at": ts,
        "updated_at": ts,
        "sla_deadline": None,
        "priority": priority,
    }

    # Auto-populate valid_until relative to created_at (realistic minute-level expiry)
    _EXPIRY_MINUTES: dict[str, tuple[int, int]] = {
        "RFQ": (5, 30),
        "CLIENT_RFQ": (5, 30),
        "QUOTE": (2, 15),
        "ORDER": (1, 10),
        "BROKER_FILL": (1, 5),
    }
    p = evt.get("payload")
    if isinstance(p, dict) and p.get("valid_until") is None and event_type in _EXPIRY_MINUTES:
        lo, hi = _EXPIRY_MINUTES[event_type]
        p["valid_until"] = _offset_minutes(ts, lo, hi)

    return evt


# =============================================================================
# ASSET-CLASS-SPECIFIC LEG GENERATORS
# =============================================================================


def _make_fx_spot_legs(
    ccy: str, far_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """FX Spot: two legs — near ccy PAY, far ccy RECEIVE. T+2 settlement."""
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "SPOT",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 3),
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "SPOT",
            "direction": "RECEIVE",
            "notional": round(notional * rate, 2),
            "ccy": far_ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 3),
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
    ]


def _make_fx_fwd_legs(
    ccy: str, far_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """FX Forward: two legs with forward points and future delivery."""
    fwd_points = round(random.uniform(-500, 500), 2)
    fwd_rate = round(rate + fwd_points / 10_000, 6)
    delivery = _random_date(30, 365)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FORWARD",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": fwd_rate,
            "start_date": _random_date(-2, 0),
            "end_date": delivery,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": fwd_points,
            "fixing_freq": None,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FORWARD",
            "direction": "RECEIVE",
            "notional": round(notional * fwd_rate, 2),
            "ccy": far_ccy,
            "rate": fwd_rate,
            "start_date": _random_date(-2, 0),
            "end_date": delivery,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": fwd_points,
            "fixing_freq": None,
        },
    ]


def _make_ndf_legs(
    ccy: str, ndf_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """NDF: non-deliverable forward — settlement in convertible ccy only."""
    fixing_date = _random_date(30, 180)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FORWARD",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": fixing_date,
            "day_count": "ACT/365",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FORWARD",
            "direction": "RECEIVE",
            "notional": round(notional * rate, 2),
            "ccy": ndf_ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": fixing_date,
            "day_count": "ACT/365",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
    ]


def _make_irs_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """IRS: fixed leg PAY vs floating leg RECEIVE. Realistic tenors and indices."""
    tenor = random.choice(IRS_TENORS)
    years = int(tenor.replace("Y", ""))
    start = _random_date(-5, 0)
    end = _random_date(years * 365 - 30, years * 365 + 30)
    index = {"USD": "SOFR", "EUR": "EURIBOR", "GBP": "SONIA", "JPY": "TIBOR"}.get(
        ccy, "SOFR"
    )
    fixed_freq = random.choice(IRS_FREQUENCIES["FIXED"])
    float_freq = random.choice(IRS_FREQUENCIES["FLOAT"])
    spread_bps = round(random.uniform(-20, 150), 1)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FIXED",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": start,
            "end_date": end,
            "day_count": random.choice(["30/360", "ACT/360"]),
            "index": None,
            "spread_bps": None,
            "fixing_freq": fixed_freq,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FLOAT",
            "direction": "RECEIVE",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": random.choice(["ACT/360", "ACT/365"]),
            "index": index,
            "spread_bps": spread_bps,
            "fixing_freq": float_freq,
        },
    ]


def _make_bond_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """Bond: single fixed coupon leg. Realistic coupon and maturity."""
    maturity_years = random.choice([2, 3, 5, 7, 10, 20, 30])
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FIXED",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-365, 0),
            "end_date": _random_date(
                maturity_years * 365 - 30, maturity_years * 365 + 30
            ),
            "day_count": random.choice(["30/360", "ACT/ACT"]),
            "index": None,
            "spread_bps": None,
            "fixing_freq": random.choice(["6M", "1Y"]),
        },
    ]


def _make_fx_option_legs(
    ccy: str, far_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """FX Option: option leg + fee leg. Realistic strikes and premiums."""
    strike = round(rate * random.uniform(0.95, 1.05), 6)
    premium = round(notional * random.uniform(0.005, 0.03), 2)
    expiry = _random_date(30, 365)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "OPTION",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": strike,
            "start_date": _random_date(-2, 0),
            "end_date": expiry,
            "day_count": "ACT/365",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FEE",
            "direction": "RECEIVE",
            "notional": premium,
            "ccy": far_ccy,
            "rate": None,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 5),
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
        },
    ]


def _make_fx_swap_legs(
    ccy: str, far_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """FX Swap: near leg + far leg with swap points."""
    near_date = _random_date(1, 5)
    tenor = random.choice(FX_SWAP_TENORS)
    far_days = {
        "O/N": 1,
        "T/N": 2,
        "S/N": 3,
        "1W": 7,
        "2W": 14,
        "1M": 30,
        "2M": 60,
        "3M": 90,
        "6M": 180,
        "9M": 270,
        "1Y": 365,
    }.get(tenor, 90)
    far_date = _random_date(far_days - 5, far_days + 5)
    swap_points = round(random.uniform(-200, 200), 2)
    far_rate = round(rate + swap_points / 10_000, 6)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "NEAR",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": near_date,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "swap_points": swap_points,
            "tenor": tenor,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FAR",
            "direction": "RECEIVE",
            "notional": notional,
            "ccy": ccy,
            "rate": far_rate,
            "start_date": near_date,
            "end_date": far_date,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": swap_points,
            "fixing_freq": None,
            "tenor": tenor,
        },
    ]


def _make_xccy_swap_legs(
    ccy: str, far_ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """Cross-currency swap: pay fixed in one ccy, receive float in another."""
    tenor = random.choice(IRS_TENORS)
    years = int(tenor.replace("Y", ""))
    start = _random_date(-5, 0)
    end = _random_date(years * 365 - 30, years * 365 + 30)
    fx_rate = round(random.uniform(0.7, 1.5), 6)
    far_notional = round(notional * fx_rate, 2)
    pay_bm = XCCY_BENCHMARKS.get(ccy, {"index": "SOFR", "dc": "ACT/360"})
    recv_bm = XCCY_BENCHMARKS.get(far_ccy, {"index": "EURIBOR", "dc": "ACT/360"})
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FIXED",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": start,
            "end_date": end,
            "day_count": pay_bm["dc"],
            "index": None,
            "spread_bps": None,
            "fixing_freq": "6M",
            "notional_exchange": "BOTH",
            "fx_rate": fx_rate,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FLOAT",
            "direction": "RECEIVE",
            "notional": far_notional,
            "ccy": far_ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": recv_bm["dc"],
            "index": recv_bm["index"],
            "spread_bps": round(random.uniform(-30, 50), 1),
            "fixing_freq": "3M",
            "notional_exchange": "BOTH",
            "fx_rate": fx_rate,
        },
    ]


def _make_swaption_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """Swaption: option on an underlying IRS."""
    expiry_tenor = random.choice(SWAPTION_EXPIRIES)
    underlying_tenor = random.choice(SWAPTION_UNDERLYINGS)
    expiry_days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730, "5Y": 1825}.get(
        expiry_tenor, 365
    )
    expiry = _random_date(expiry_days - 10, expiry_days + 10)
    option_type = random.choice(["PAYER", "RECEIVER"])
    settlement_type = random.choice(["PHYSICAL", "CASH"])
    impl_vol = round(random.uniform(15.0, 60.0), 2)
    fwd_rate = round(rate * random.uniform(0.95, 1.05), 4)
    premium = round(notional * random.uniform(0.003, 0.02), 2)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "OPTION",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": expiry,
            "day_count": "ACT/365",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "option_type": option_type,
            "settlement_type": settlement_type,
            "underlying_tenor": underlying_tenor,
            "impl_vol": impl_vol,
            "forward_swap_rate": fwd_rate,
            "expiry_tenor": expiry_tenor,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FEE",
            "direction": "RECEIVE",
            "notional": premium,
            "ccy": ccy,
            "rate": None,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 5),
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "fee_type": "UPFRONT",
            "premium": premium,
        },
    ]


def _make_fra_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """FRA: single leg with contract rate, fixing date, settlement date."""
    period = random.choice(FRA_PERIODS)
    start_months, end_months = [int(x) for x in period.split("x")]
    fixing_date = _random_date(start_months * 30 - 5, start_months * 30 + 5)
    settlement_date = _random_date(start_months * 30, start_months * 30 + 3)
    end_date = _random_date(end_months * 30 - 5, end_months * 30 + 5)
    index = {"USD": "SOFR", "EUR": "EURIBOR", "GBP": "SONIA", "JPY": "TIBOR"}.get(
        ccy, "SOFR"
    )
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FRA",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": fixing_date,
            "end_date": end_date,
            "day_count": "ACT/360",
            "index": index,
            "spread_bps": None,
            "fixing_freq": None,
            "period": period,
            "contract_rate": rate,
            "fixing_date": fixing_date,
            "settlement_date": settlement_date,
            "reference_rate": index,
        },
    ]


def _make_bond_future_legs(
    ccy: str, notional: float, rate: float
) -> list[dict[str, Any]]:
    """Bond future: single futures leg with contract details."""
    future = random.choice(_BOND_FUTURES)
    contract_code, exchange, description, contract_size = future
    ctd_isin = random.choice(_CTD_ISINS)
    delivery_months = ["H", "M", "U", "Z"]  # Mar, Jun, Sep, Dec
    delivery_month = f"20{random.randint(26, 28)}{random.choice(delivery_months)}"
    conversion_factor = round(random.uniform(0.75, 1.15), 6)
    num_contracts = max(1, int(notional / contract_size))
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FUTURE",
            "direction": "PAY",
            "notional": num_contracts * contract_size,
            "ccy": ccy,
            "rate": rate,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(30, 180),
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "contract_code": contract_code,
            "exchange": exchange,
            "delivery_month": delivery_month,
            "CTD_ISIN": ctd_isin,
            "conversion_factor": conversion_factor,
            "basis": round(random.uniform(-5, 15), 2),
            "tick_size": 0.015625,
            "contract_size": contract_size,
            "num_contracts": num_contracts,
        },
    ]


def _make_repo_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """Repo: cash leg + collateral leg."""
    collateral = random.choice(_REPO_COLLATERAL)
    coll_type, coll_desc, coll_isin = collateral
    term_days = random.choice([1, 7, 14, 30, 60, 90])
    haircut = round(random.uniform(1.0, 5.0), 2)
    collateral_value = round(notional * (1 + haircut / 100), 2)
    start = _random_date(-2, 0)
    end = _random_date(term_days - 1, term_days + 1)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "REPO",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": rate,
            "start_date": start,
            "end_date": end,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "repo_rate": rate,
            "term_days": term_days,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "COLLATERAL",
            "direction": "RECEIVE",
            "notional": collateral_value,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "collateral_type": coll_type,
            "collateral_description": coll_desc,
            "collateral_ISIN": coll_isin,
            "haircut_pct": haircut,
            "triparty_agent": random.choice(
                ["BNY Mellon", "JPMorgan", "Euroclear", None]
            ),
        },
    ]


def _make_cds_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """CDS: protection leg + premium leg."""
    entity = random.choice(_CDS_ENTITIES)
    ref_name, ref_ticker, red_code, rating = entity
    tenor = random.choice(["1Y", "3Y", "5Y", "7Y", "10Y"])
    years = int(tenor.replace("Y", ""))
    start = _random_date(-5, 0)
    end = _random_date(years * 365 - 30, years * 365 + 30)
    upfront_pct = round(random.uniform(-2.0, 5.0), 4) if rate > 100 else 0.0
    recovery = round(random.uniform(30.0, 45.0), 1)
    restructuring = random.choice(CDS_RESTRUCTURING)
    seniority = random.choice(CDS_SENIORITY)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "PROTECTION",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "reference_entity": ref_name,
            "RED_code": red_code,
            "seniority": seniority,
            "restructuring": restructuring,
            "recovery_rate": recovery,
            "rating": rating,
            "ISDA_year": random.choice(["2003", "2014"]),
            "credit_events": ["BANKRUPTCY", "FAILURE_TO_PAY", "RESTRUCTURING"],
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "PREMIUM",
            "direction": "RECEIVE",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": rate,
            "fixing_freq": "3M",
            "upfront_pct": upfront_pct,
            "running_spread_bps": rate,
        },
    ]


def _make_trs_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """TRS: total return leg + financing leg."""
    underlying = random.choice(_TRS_UNDERLYINGS)
    ticker, name, ul_ccy = underlying
    initial_price = round(random.uniform(50, 500), 2)
    reset_freq = random.choice(["1M", "3M", "6M"])
    index = {"USD": "SOFR", "EUR": "EURIBOR", "GBP": "SONIA", "JPY": "TIBOR"}.get(
        ccy, "SOFR"
    )
    financing_spread_bps = round(random.uniform(20, 150), 1)
    start = _random_date(-5, 0)
    end = _random_date(90, 365)
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "TOTAL_RETURN",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": "ACT/360",
            "index": None,
            "spread_bps": None,
            "fixing_freq": reset_freq,
            "underlying_asset": ticker,
            "underlying_name": name,
            "initial_price": initial_price,
            "return_type": random.choice(["TOTAL", "PRICE"]),
            "dividend_treatment": random.choice(["PASS_THROUGH", "MANUFACTURED"]),
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FINANCING",
            "direction": "RECEIVE",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": "ACT/360",
            "index": index,
            "spread_bps": financing_spread_bps,
            "fixing_freq": reset_freq,
        },
    ]


def _make_equity_legs(ccy: str, notional: float, rate: float) -> list[dict[str, Any]]:
    """Equity: single cash leg with share details."""
    ticker_info = random.choice(_EQUITY_TICKERS)
    ticker, exchange, name, eq_ccy = ticker_info
    price = rate  # rate is used as price for equity
    quantity = max(1, int(notional / price))
    return [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "CASH",
            "direction": "PAY",
            "notional": round(quantity * price, 2),
            "ccy": eq_ccy,
            "rate": price,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 3),
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "quantity": quantity,
            "price": price,
            "side": random.choice(["BUY", "SELL"]),
            "order_type": random.choice(["MARKET", "LIMIT", "VWAP", "TWAP"]),
            "VWAP": round(price * random.uniform(0.99, 1.01), 4)
            if random.random() > 0.5
            else None,
        },
    ]


def _make_legs_for(
    product_type: str,
    fpml_id: str,
    ccy: str,
    far_ccy: str,
    notional: float,
    rate: float,
) -> list[dict[str, Any]]:
    """Dispatch to asset-class-specific leg generator."""
    if fpml_id == "FPML-FX-NDF":
        return _make_ndf_legs(ccy, far_ccy, notional, rate)
    if fpml_id == "FPML-FX-FWD":
        return _make_fx_fwd_legs(ccy, far_ccy, notional, rate)
    dispatch: dict[str, Any] = {
        "FX_SPOT": lambda: _make_fx_spot_legs(ccy, far_ccy, notional, rate),
        "FX_FORWARD": lambda: _make_fx_fwd_legs(ccy, far_ccy, notional, rate),
        "FX_SWAP": lambda: _make_fx_swap_legs(ccy, far_ccy, notional, rate),
        "FX_NDF": lambda: _make_ndf_legs(ccy, far_ccy, notional, rate),
        "FX_OPTION": lambda: _make_fx_option_legs(ccy, far_ccy, notional, rate),
        "IRS": lambda: _make_irs_legs(ccy, notional, rate),
        "XCCY_SWAP": lambda: _make_xccy_swap_legs(ccy, far_ccy, notional, rate),
        "SWAPTION": lambda: _make_swaption_legs(ccy, notional, rate),
        "FRA": lambda: _make_fra_legs(ccy, notional, rate),
        "BOND": lambda: _make_bond_legs(ccy, notional, rate),
        "BOND_FUTURE": lambda: _make_bond_future_legs(ccy, notional, rate),
        "REPO": lambda: _make_repo_legs(ccy, notional, rate),
        "CDS": lambda: _make_cds_legs(ccy, notional, rate),
        "TRS": lambda: _make_trs_legs(ccy, notional, rate),
        "EQUITY": lambda: _make_equity_legs(ccy, notional, rate),
    }
    return dispatch.get(
        product_type, lambda: _make_fx_spot_legs(ccy, far_ccy, notional, rate)
    )()


# =============================================================================
# SHARED PAYLOAD BUILDERS
# =============================================================================


def _make_trade_economics(
    product_type: str, ccy: str, notional: float, rate: float, ccy_pair: str | None
) -> dict[str, Any]:
    """Core trade terms reused in booking/trade payloads."""
    base = {
        "product_type": product_type,
        "trade_date": _random_date(-60, 0),
        "value_date": _random_date(1, 90),
        "direction": random.choice(DIRECTIONS),
        "notional": notional,
        "ccy": ccy,
        "ccy_pair": ccy_pair,
        "rate": rate,
        "spread": None,
    }
    # Product-specific extensions
    if product_type in ("IRS", "XCCY_SWAP", "SWAPTION", "FRA"):
        base["spread"] = round(random.uniform(-20, 50), 2)
    if product_type == "CDS":
        base["spread"] = rate  # spread_bps IS the rate for CDS
        base["rate"] = None
    if product_type == "EQUITY":
        base["rate"] = rate  # price
        base["quantity"] = max(1, int(notional / rate))
    if product_type == "REPO":
        base["repo_rate"] = rate
        base["term_days"] = random.choice([1, 7, 14, 30, 60, 90])
    if product_type == "BOND_FUTURE":
        base["futures_price"] = rate
    return base


def _make_parties(buyer_id: str, seller_id: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "BUYER",
            "entity_id": buyer_id,
            "trader": random.choice(TRADER_NAMES),
            "sales": random.choice(SALES_NAMES),
        },
        {
            "role": "SELLER",
            "entity_id": seller_id,
            "trader": random.choice(TRADER_NAMES),
            "sales": random.choice(SALES_NAMES),
        },
    ]


def _make_enriched() -> dict[str, Any]:
    """Post-match enrichment for materialized trades."""
    return {
        "risk_flags": random.sample(RISK_FLAGS, k=random.randint(0, 2)),
        "regulatory": {
            "uti": _uti(),
            "usi": _uti()[:20],
            "lei": _lei(),
            "jurisdiction": random.sample(
                ["US", "EU", "UK", "SG"], k=random.randint(1, 2)
            ),
            "reporting_status": random.choice(["PENDING", "REPORTED", "EXEMPT"]),
            "reported_at": _random_datetime(-5, 0),
        },
        "settlement": {
            "ssi_id": _gen_id("event"),
            "nostro": f"{random.choice(['JPMC', 'CITI', 'HSBC', 'BARC'])}-{random.choice(['NY', 'LDN', 'TYO', 'SGP'])}",
            "value_date": _random_date(1, 30),
            "settlement_status": random.choice(
                ["PENDING", "INSTRUCTED", "MATCHED", "SETTLED"]
            ),
        },
        "pricing": {
            "mid_price": round(random.uniform(0.5, 5.0), 6),
            "spread": round(random.uniform(0.5, 5.0), 4),
            "markup_bps": round(random.uniform(0.5, 10.0), 2),
            "benchmark": random.choice(
                ["WMR 4PM Fix", "ECB Fix", "SOFR O/N", "ICE LIBOR"]
            ),
        },
        "compliance": {
            "approved_by": random.choice(TRADER_NAMES),
            "limit_check": random.choice(["PASS", "PASS", "PASS", "BREACH"]),
            "wash_trade_flag": False,
            "best_execution": random.choice(["PASS", "REVIEW"]),
        },
        "enriched_at": _random_datetime(-2, 0),
        "enriched_by": "ENRICHMENT-SVC",
    }


def _make_raw_wire(source: str, protocol: str, product_type: str) -> dict[str, Any]:
    """Generate a realistic raw{} layer based on source and protocol."""
    ts = _random_datetime(-10, 0)
    msg_id = f"{source[:3]}-MSG-{uuid.uuid4().hex[:8].upper()}"

    raw_text = None
    content: dict[str, Any] = {}
    if protocol == "FIX":
        raw_text = f"8=FIX.4.4|9=256|35=D|49={source}|56=XFTWS|55={product_type}|..."
        content = {"msg_type": "D", "sender_comp_id": source, "target_comp_id": "XFTWS"}
    elif protocol == "FPML":
        raw_text = '<FpML xmlns="http://www.fpml.org/FpML-5/confirmation"><trade>...</trade></FpML>'
        content = {"namespace": "fpml-5-12", "message_type": "tradeConfirmation"}
    elif protocol == "SWIFT_MT":
        mt = (
            "MT300"
            if product_type
            in ("FX_SPOT", "FX_FORWARD", "FX_SWAP", "FX_NDF", "FX_OPTION")
            else "MT360"
        )
        raw_text = f"{{1:F01BANKUS33AXXX0000000000}}{{2:O{mt}...}}"
        content = {
            "message_type": mt,
            "sender_bic": f"BANK{random.choice(['US', 'GB', 'DE'])}33",
        }

    return {
        "format": protocol if protocol != "REST" else "JSON",
        "version": {
            "FIX": "4.4",
            "FPML": "5.12",
            "SWIFT_MT": "MT300",
            "INTERNAL": "1.0",
        }.get(protocol, "1.0"),
        "content": content,
        "raw_text": raw_text,
        "received_at": ts,
        "checksum": uuid.uuid4().hex,
        "source_msg_id": msg_id,
    }


# =============================================================================
# SCENARIO: RFQ_HIT
# CLIENT_RFQ v1 → QUOTE v1 → CLIENT_RFQ v2 (revised notional) →
# QUOTE v2 (revised rate) → CLIENT_RFQ v3 (ACCEPTED) → TRADE
# Bilateral negotiation — direct client↔trader, no sales desk
# =============================================================================


def _scenario_rfq_hit(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pt = "FX_SPOT"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional_v1 = _notional_for(pt)
    rate_v1 = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    direction = random.choice(DIRECTIONS)

    # ~30% of RFQ chains originate from chat (BBG IB or Symphony)
    _chat_src = random.choice(["BLOOMBERG_CHAT", "SYMPHONY"]) if random.random() < 0.3 else None
    _thr_id = f"THR-{uuid.uuid4().hex[:12].upper()}" if _chat_src else None

    # ── v1: CLIENT_RFQ (initial request) ──
    rfq_v1 = _make_event(
        "RFQ",
        status="ACTIVE",
        source=_chat_src or "CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v1,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional_v1,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": None,
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq_v1)

    # ── v1: QUOTE (trader responds with indicative rate) ──
    quote_v1 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v1,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v1["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq_v1["event_id"],
            "price": rate_v1,
            "spread": round(random.uniform(0.5, 10.0), 2),
            "valid_until": None,
            "quoted_by": trader,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(quote_v1)

    # ── v2: CLIENT_RFQ (revised notional — client adjusts size) ──
    notional_v2 = round(notional_v1 * random.uniform(0.8, 1.3), 2)
    rfq_v2 = _make_event(
        "RFQ",
        status="ACTIVE",
        source=_chat_src or "CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v2,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional_v2,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": None,
            "limit_price": round(rate_v1 * random.uniform(0.99, 1.01), 6),
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 2,
            "negotiation_status": "REVISED",
            "revision_reason": "Client adjusted notional",
        },
    )
    events.append(rfq_v2)

    # ── v2: QUOTE (revised rate — trader reprices for new size) ──
    rate_v2 = round(rate_v1 * random.uniform(0.998, 1.003), 6)
    quote_v2 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v2,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_v2["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
            {"event_id": quote_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq_v2["event_id"],
            "price": rate_v2,
            "spread": round(random.uniform(0.5, 10.0), 2),
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 2,
            "revision_reason": "Repriced for revised notional",
        },
    )
    events.append(quote_v2)

    # ── v3: CLIENT_RFQ (ACCEPTED — client hits the quote) ──
    rfq_v3 = _make_event(
        "RFQ",
        status="ACCEPTED",
        source=_chat_src or "CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v2,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v2["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional_v2,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": None,
            "limit_price": rate_v2,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 3,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": quote_v2["event_id"],
        },
    )
    events.append(rfq_v3)

    # ── TRADE (materialized from accepted negotiation) ──
    fpml_spot = next((f for f in fpmls if f["product_type"] == "FX_SPOT"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional_v2, rate_v2, ccy_pair)
    legs = _make_legs_for(pt, fpml_spot["fpml_id"], ccy, far_ccy, notional_v2, rate_v2)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional_v2,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_v3["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote_v2["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_spot["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
        priority=random.choice(["NORMAL", "HIGH"]),
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: STP_AUTO
# STP_MESSAGE → TRADE (auto-booked from wire)
# =============================================================================


def _scenario_stp_auto(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    source = random.choice(["BLOOMBERG", "TRADEWEB", "MARKITWIRE"])
    desk = random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    protocol = SOURCE_PROTOCOL[source]

    # STP_MESSAGE
    stp = _make_event(
        "STP_MESSAGE",
        status="ACTIVE",
        source="STP_PIPELINE",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "STP_AUTO",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SYSTEM",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "STP_PIPELINE",
        },
        raw=_make_raw_wire(source, protocol, pt),
        payload={
            "parsed_economics": {
                "product_type": pt,
                "direction": econ["direction"],
                "notional": notional,
                "ccy": ccy,
                "ccy_pair": ccy_pair,
                "rate": rate,
                "trade_date": econ["trade_date"],
                "value_date": econ["value_date"],
            },
            "sender": seller["short_name"],
            "receiver": buyer["short_name"],
            "stp_status": "BOOKED",
            "error": None,
        },
    )
    events.append(stp)

    # TRADE
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="STP_PIPELINE",
        actor="STP_PIPELINE",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": stp["event_id"], "rel": "CREATED_FROM", "role": "PARENT"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20] if pt == "IRS" else None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: BROKER_EXEC
# ORDER → BROKER_FILL (x2-3 separate events) → TRADING_BOOKING → TRADE
# =============================================================================


def _scenario_broker_exec(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pt = "FX_OPTION"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    brokers = [e for e in entities if e["entity_type"] == "BROKER"]
    broker = random.choice(brokers) if brokers else random.choice(entities[:5])
    buyer = random.choice(
        [e for e in entities[:10] if e["entity_id"] != broker["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    fpml_opt = next((f for f in fpmls if f["product_type"] == "FX_OPTION"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_opt["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], broker["entity_id"])

    # ORDER
    n_fills = random.randint(2, 3)
    order = _make_event(
        "ORDER",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "order_type": random.choice(["LIMIT", "MARKET"]),
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": round(rate * 1.01, 6) if random.random() > 0.4 else None,
            "broker_entity_id": broker["entity_id"],
            "expected_fills": n_fills,
            "filled_qty": 0.0,
            "remaining_qty": notional,
        },
    )
    events.append(order)

    # BROKER_FILL — each fill is its own separate event
    fill_events: list[dict[str, Any]] = []
    remaining = notional
    total_qty_price = 0.0
    for i in range(n_fills):
        fill_qty = (
            round(notional / n_fills, 2) if i < n_fills - 1 else round(remaining, 2)
        )
        remaining -= fill_qty
        fill_price = round(rate * random.uniform(0.999, 1.001), 6)
        total_qty_price += fill_qty * fill_price
        fill_links = [
            {"event_id": order["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}
        ]
        if fill_events:
            fill_links.append(
                {
                    "event_id": fill_events[-1]["event_id"],
                    "rel": "FOLLOWS",
                    "role": "SEQUENCE",
                }
            )

        bf = _make_event(
            "BROKER_FILL",
            status="ACTIVE",
            source="BROKER",
            actor=broker["short_name"],
            desk=desk,
            product_type=pt,
            notional=fill_qty,
            ccy=ccy,
            cpty_id=broker["entity_id"],
            links=fill_links,
            correlation={
                "match_type": "RECONCILIATION",
                "scenario": "BROKER_RECON",
                "match_status": "PARTIAL",
                "cardinality": "MANY_TO_ONE",
                "direction": "RHS",
                "actor_role": "BROKER",
                "breaks": [],
                "resolution": None,
                "matched_at": _random_datetime(-3, 0),
                "matched_by": "MATCHING_ENG",
            },
            raw=_make_raw_wire("BROKER", "FIX", pt),
            payload={
                "broker_entity_id": broker["entity_id"],
                "exec_id": _gen_id("event"),
                "price": fill_price,
                "qty": fill_qty,
                "venue": random.choice(["D2C", "SEF", "OTC", "CLOB"]),
                "commission": round(fill_qty * random.uniform(0.0001, 0.001), 2),
                "commission_bps": round(random.uniform(0.5, 5.0), 2),
                "product_type": pt,
                "ccy": ccy,
                "exec_type": "PARTIAL_FILL" if i < n_fills - 1 else "FILL",
                "fill_number": i + 1,
                "total_fills": n_fills,
                "cumulative_qty": round(notional - remaining, 2),
            },
        )
        events.append(bf)
        fill_events.append(bf)

    vwap = round(total_qty_price / notional, 6)

    # TRADING_BOOKING
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        links=[
            {"event_id": order["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"},
            *[
                {"event_id": bf["event_id"], "rel": "CORRELATES_WITH", "role": "LHS"}
                for bf in fill_events
            ],
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
            "vwap": vwap,
        },
    )
    events.append(tb)

    # TRADE
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            *[
                {"event_id": bf["event_id"], "rel": "CREATED_FROM", "role": "PARENT"}
                for bf in fill_events
            ],
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_opt["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.4 else None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: OBO_CLIENT
# OBO_TICKET → SALES_BOOKING → TRADE
# =============================================================================


def _scenario_obo_client(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pt = "CDS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    client = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != client["entity_id"]]
    )
    book = random.choice(books)
    sales, desk = random.choice(SALES_NAMES), random.choice(DESKS)
    fpml_cds = next((f for f in fpmls if f["product_type"] == "CDS"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_cds["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(client["entity_id"], seller["entity_id"])

    obo = _make_event(
        "OBO_TICKET",
        status="ACTIVE",
        source="CLIENT",
        actor=client["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=client["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
        },
        payload={
            "client_entity_id": client["entity_id"],
            "on_behalf_of": client["name"],
            "ticket_ref": _gen_id("event"),
            "allocation_status": "PENDING",
            "trade_economics": {
                "product_type": pt,
                "direction": econ["direction"],
                "notional": notional,
                "ccy": ccy,
                "ccy_pair": ccy_pair,
                "rate": rate,
                "value_date": econ["value_date"],
            },
        },
    )
    events.append(obo)

    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=client["entity_id"],
        links=[{"event_id": obo["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "OBO_BOOKING",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": "Client Hedging",
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(sb)

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=client["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": obo["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_cds["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Client Hedging",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: UNMATCHED_BOOKING
# SALES_BOOKING (no matching TRADING_BOOKING yet — pending on blotter)
# =============================================================================


def _scenario_unmatched_booking(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Sales booking waiting for trader hedge — shows up as UNMATCHED on blotter."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    sales, desk = random.choice(SALES_NAMES), random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    sb = _make_event(
        "SALES_BOOKING",
        status="PENDING",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": None,
            "matched_by": None,
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        priority=random.choice(["HIGH", "URGENT"]),
    )
    events.append(sb)
    return events


# =============================================================================
# SCENARIO: PARTIAL_MATCH
# SALES_BOOKING + TRADING_BOOKING with breaks (notional mismatch)
# =============================================================================


def _scenario_partial_match(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Booking pair with notional break — shows PARTIAL on blotter, needs resolution."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional_lhs = _notional_for(pt)
    # Intentional mismatch — RHS is off by 1-5%
    notional_rhs = round(notional_lhs * random.uniform(1.01, 1.05), 2)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    econ_lhs = _make_trade_economics(pt, ccy, notional_lhs, rate, ccy_pair)
    econ_rhs = _make_trade_economics(pt, ccy, notional_rhs, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional_lhs, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    breaks = [
        {
            "field": "notional",
            "lhs": str(notional_lhs),
            "rhs": str(notional_rhs),
            "tolerance": "100",
        },
    ]

    sb = _make_event(
        "SALES_BOOKING",
        status="PENDING",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional_lhs,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": breaks,
            "resolution": None,
            "matched_at": None,
            "matched_by": None,
        },
        payload={
            "trade_economics": econ_lhs,
            "book_id": book_s["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        priority="HIGH",
    )
    events.append(sb)

    tb = _make_event(
        "TRADING_BOOKING",
        status="PENDING",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional_rhs,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": breaks,
            "resolution": None,
            "matched_at": None,
            "matched_by": None,
        },
        payload={
            "trade_economics": econ_rhs,
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        priority="HIGH",
    )
    events.append(tb)
    return events


# =============================================================================
# SCENARIO: FAILED_STP
# STP_MESSAGE with parse error — no trade materialized
# =============================================================================


def _scenario_failed_stp(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Inbound wire that failed to parse — stuck in STP queue."""
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    source = random.choice(["BLOOMBERG", "TRADEWEB", "MARKITWIRE"])
    seller = random.choice(entities[:10])
    buyer = random.choice(
        [e for e in entities[:10] if e["entity_id"] != seller["entity_id"]]
    )
    desk = random.choice(DESKS)
    protocol = SOURCE_PROTOCOL[source]

    errors = [
        "Missing mandatory field: tradeDate",
        "Invalid currency pair: USDXYZ",
        "Notional exceeds STP threshold (>500M)",
        f"Unknown counterparty LEI: {_lei()}",
        "FpML schema validation failed: leg count mismatch",
    ]

    stp = _make_event(
        "STP_MESSAGE",
        status="FAILED",
        source="STP_PIPELINE",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        priority="URGENT",
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SYSTEM",
        },
        raw=_make_raw_wire(source, protocol, pt),
        payload={
            "parsed_economics": {
                "product_type": pt,
                "direction": None,
                "notional": notional,
                "ccy": ccy,
                "ccy_pair": ccy_pair,
                "rate": None,
                "trade_date": None,
                "value_date": None,
            },
            "sender": seller["short_name"],
            "receiver": buyer["short_name"],
            "stp_status": "FAILED",
            "error": random.choice(errors),
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "ACTIVE",
                "at": _random_datetime(-10, -5),
                "by": "STP_PIPELINE",
                "reason": "Received",
                "diff": {},
            },
            {
                "from_status": "ACTIVE",
                "to_status": "FAILED",
                "at": _random_datetime(-5, 0),
                "by": "STP_PIPELINE",
                "reason": random.choice(errors),
                "diff": {},
            },
        ],
    )
    return [stp]


# =============================================================================
# SCENARIO: FORCE_MATCH
# Disputed bookings resolved by operations force-match
# =============================================================================


def _scenario_force_match(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Bookings with break → ops force-match → TRADE → rematch tail (6 events).

    After force match, corrected booking comes in → UNMATCH forced trade → clean MATCH.
    """
    events: list[dict[str, Any]] = []
    pt = "FX_SWAP"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    fpml_swap = next((f for f in fpmls if f["product_type"] == "FX_SWAP"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_swap["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    ops_user = random.choice(TRADER_NAMES)
    force_time = _random_datetime(-5, -3)

    # Small rate break
    rate_lhs = rate
    rate_rhs = round(rate * 1.002, 6)
    breaks = [
        {
            "field": "rate",
            "lhs": str(rate_lhs),
            "rhs": str(rate_rhs),
            "tolerance": "0.0001",
        }
    ]
    resolution = {
        "action": "FORCE_MATCH",
        "service": "OPS_CONSOLE",
        "params": {"overridden_by": ops_user, "reason": "Within acceptable tolerance"},
        "executed_at": force_time,
    }

    # 1. SALES_BOOKING (LHS — original with break)
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "OVERRIDE",
            "scenario": "FORCE_MATCH",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": breaks,
            "resolution": resolution,
            "matched_at": force_time,
            "matched_by": ops_user,
        },
        payload={
            "trade_economics": econ,
            "book_id": book_s["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "PENDING",
                "at": _random_datetime(-10, -7),
                "by": "SYSTEM",
                "reason": "Created",
                "diff": {},
            },
            {
                "from_status": "PENDING",
                "to_status": "PENDING",
                "at": _random_datetime(-7, -5),
                "by": "MATCHING_ENG",
                "reason": "Partial match — rate break",
                "diff": {},
            },
            {
                "from_status": "PENDING",
                "to_status": "MATCHED",
                "at": force_time,
                "by": ops_user,
                "reason": "Force-matched by operations",
                "diff": {"match_status": {"old": "UNMATCHED", "new": "FORCED"}},
            },
        ],
    )
    events.append(sb)

    # 2. TRADING_BOOKING v1 (RHS — with incorrect rate)
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"}],
        correlation={
            "match_type": "OVERRIDE",
            "scenario": "FORCE_MATCH",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": breaks,
            "resolution": resolution,
            "matched_at": force_time,
            "matched_by": ops_user,
        },
        payload={
            "trade_economics": {**econ, "rate": rate_rhs},
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "PENDING",
                "at": _random_datetime(-10, -7),
                "by": "SYSTEM",
                "reason": "Created",
                "diff": {},
            },
            {
                "from_status": "PENDING",
                "to_status": "MATCHED",
                "at": force_time,
                "by": ops_user,
                "reason": "Force-matched by operations",
                "diff": {"match_status": {"old": "UNMATCHED", "new": "FORCED"}},
            },
        ],
    )
    events.append(tb)

    # 3. TRADE (materialized from force match — will be unmatched)
    trade = _make_event(
        "TRADE",
        status="CANCELLED",
        source="MATCHING_ENG",
        actor=ops_user,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_swap["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": force_time,
                "by": ops_user,
                "reason": "Materialized from force-match",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "CANCELLED",
                "at": _random_datetime(-3, -2),
                "by": "MATCHING_ENG",
                "reason": "Unmatched — corrected booking received",
                "diff": {},
            },
        ],
    )
    events.append(trade)

    # ── Rematch tail: correct notional arrives, unmatch forced trade, clean match ──
    correct_notional = round(
        notional * random.uniform(0.99, 1.0), 2
    )  # very close to original
    rematch_time = _random_datetime(-2, 0)

    # 4. TRADING_BOOKING v2 (correct notional)
    tb_v2 = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=correct_notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": tb["event_id"], "rel": "SUPERSEDES", "role": "LHS"},
            {"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "FORCE_MATCH_REMATCH",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": [],
            "resolution": None,
            "matched_at": rematch_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": {**econ, "notional": correct_notional, "rate": rate_lhs},
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
            "correction_reason": "Rate corrected to match sales booking",
        },
    )
    events.append(tb_v2)

    # 5. UNMATCH (breaks the forced trade)
    unmatch = _make_event(
        "UNMATCH",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": trade["event_id"], "rel": "BREAKS", "role": "PARENT"},
            {"event_id": tb_v2["event_id"], "rel": "TRIGGERED_BY", "role": "RHS"},
        ],
        payload={
            "broken_trade_id": trade["payload"]["trade_id"],
            "reason": "Corrected booking received — force match superseded",
            "original_match_type": "FORCED",
            "new_match_type": "EXACT",
        },
    )
    events.append(unmatch)

    # 6. MATCH (exact match, clean)
    clean_legs = _make_legs_for(
        pt, fpml_swap["fpml_id"], ccy, far_ccy, correct_notional, rate_lhs
    )
    match_evt = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=correct_notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb_v2["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": unmatch["event_id"], "rel": "FOLLOWS", "role": "SEQUENCE"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_swap["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": clean_legs,
            "uti": _uti(),
            "usi": None,
            "rematch_reason": "Exact match after corrected booking",
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": rematch_time,
                "by": "MATCHING_ENG",
                "reason": "Clean match — exact",
                "diff": {},
            },
        ],
    )
    events.append(match_evt)
    return events


# =============================================================================
# SCENARIO: GIVEUP
# GIVEUP_NOTICE → TRADE
# =============================================================================


def _scenario_giveup(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pt = "BOND"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    brokers = [e for e in entities if e["entity_type"] == "BROKER"]
    exec_broker = random.choice(brokers) if brokers else random.choice(entities[:5])
    prime_broker = random.choice(
        [e for e in entities[:10] if e["entity_id"] != exec_broker["entity_id"]]
    )
    book = random.choice(books)
    desk = random.choice(DESKS)
    fpml_bond = next((f for f in fpmls if f["product_type"] == "BOND"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_bond["fpml_id"], ccy, far_ccy, notional, rate)
    giveup_ref = _gen_id("event")

    # 1. GIVEUP_NOTICE — executing broker notifies giveup
    gu = _make_event(
        "GIVEUP_NOTICE",
        status="ACTIVE",
        source="BROKER",
        actor=exec_broker["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=exec_broker["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "GIVEUP",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "BROKER",
            "breaks": [],
            "resolution": None,
            "matched_at": None,
            "matched_by": None,
        },
        raw=_make_raw_wire("BROKER", "FIX", pt),
        payload={
            "executing_broker": exec_broker["entity_id"],
            "prime_broker": prime_broker["entity_id"],
            "giveup_ref": giveup_ref,
            "trade_economics": {
                "product_type": pt,
                "direction": econ["direction"],
                "notional": notional,
                "ccy": ccy,
                "ccy_pair": ccy_pair,
                "rate": rate,
                "trade_date": econ["trade_date"],
                "value_date": econ["value_date"],
            },
        },
    )
    events.append(gu)

    # 2. GIVEUP_ACCEPT — prime broker accepts the giveup
    accept_time = _random_datetime(-3, 0)
    ga = _make_event(
        "GIVEUP_ACCEPT",
        status="ACTIVE",
        source="MANUAL",
        actor=prime_broker["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=prime_broker["entity_id"],
        links=[{"event_id": gu["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "GIVEUP",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "OPS",
            "breaks": [],
            "resolution": None,
            "matched_at": accept_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "giveup_ref": giveup_ref,
            "executing_broker": exec_broker["entity_id"],
            "prime_broker": prime_broker["entity_id"],
            "acceptance_status": "ACCEPTED",
            "accepted_by": prime_broker["short_name"],
            "accepted_at": accept_time,
        },
    )
    events.append(ga)

    # 3. TRADE — materialized after acceptance
    parties = _make_parties(prime_broker["entity_id"], exec_broker["entity_id"])
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=prime_broker["entity_id"],
        links=[
            {"event_id": gu["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": ga["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_bond["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: FX_COMPENSATION
# Import/export contract draws → compensation netting
#
# Real-world flow: Corporate treasury has FX facility for commercial contracts.
# Import contracts = buy foreign ccy (pay supplier).
# Export contracts = sell foreign ccy (receive from buyer).
# Multiple utilization draws over time, then bank compensates (nets) the flows.
# =============================================================================

# Realistic import/export contract references
_IMPORT_REFS = [
    "IMP-DE-MACHINERY-2026",
    "IMP-JP-ELECTRONICS-2026",
    "IMP-CN-TEXTILES-2026",
    "IMP-KR-SEMICONDUCTORS-2026",
    "IMP-IT-AUTOMOTIVE-2026",
    "IMP-TW-COMPONENTS-2026",
]
_EXPORT_REFS = [
    "EXP-US-PHARMA-2026",
    "EXP-EU-AGRI-2026",
    "EXP-UK-CHEMICALS-2026",
    "EXP-SG-OIL-2026",
    "EXP-AU-MINING-2026",
    "EXP-BR-COMMODITIES-2026",
]


def _scenario_fx_compensation(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Import/export FX compensation — facility draws + netting.

    Generates 3-5 FX trades for the same client/ccy pair:
      - Some are import draws (client buys foreign ccy = PAY direction)
      - Some are export draws (client sells foreign ccy = RECEIVE direction)
    Then generates SETTLEMENT_INSTRs + a compensation NET_SETTLEMENT.

    Each draw goes: OBO_TICKET → SALES_BOOKING → TRADE.
    The facility utilization is tracked in the OBO_TICKET payload.
    """
    events: list[dict[str, Any]] = []

    # Pick FX spot or forward template
    fx_fpmls = [f for f in fpmls if f["product_type"] == "FX_SPOT"]
    fpml = random.choice(fx_fpmls) if fx_fpmls else fpmls[0]
    is_ndf = fpml["fpml_id"] == "FPML-FX-NDF"

    # Same client, same ccy pair for all draws
    client = random.choice(entities[:10])
    bank = random.choice(
        [e for e in entities[:10] if e["entity_id"] != client["entity_id"]]
    )
    book = random.choice(books)
    sales = random.choice(SALES_NAMES)
    desk = random.choice(["FX Spot", "FX Options", "EM Rates"])

    if is_ndf:
        ccy, far_ccy, ccy_pair = _pick_ndf_pair()
    else:
        ccy, far_ccy, ccy_pair = _pick_ccy_pair("FX_SPOT")

    # Facility details — shared across all draws
    facility_id = _gen_id("event")
    facility_limit = round(random.uniform(50_000_000, 500_000_000), 2)
    facility_rate = _rate_for("FX_SPOT")  # pre-agreed indicative rate

    # Generate 3-5 draws — mix of import and export
    n_draws = random.randint(3, 5)
    n_imports = random.randint(1, n_draws - 1)  # at least 1 import and 1 export
    draw_directions = ["PAY"] * n_imports + ["RECEIVE"] * (n_draws - n_imports)
    random.shuffle(draw_directions)

    trade_events_local: list[dict[str, Any]] = []
    settlement_events_local: list[dict[str, Any]] = []
    utilized_total = 0.0

    for draw_idx, direction in enumerate(draw_directions, 1):
        # Each draw is a fraction of the facility
        draw_amount = round(facility_limit * random.uniform(0.05, 0.25), 2)
        utilized_total += draw_amount
        # Rate drifts slightly from facility rate per draw
        draw_rate = round(facility_rate * random.uniform(0.998, 1.002), 6)

        contract_ref = random.choice(
            _IMPORT_REFS if direction == "PAY" else _EXPORT_REFS
        )
        contract_type = "IMPORT" if direction == "PAY" else "EXPORT"

        # 1. OBO_TICKET — client draw against facility
        obo = _make_event(
            "OBO_TICKET",
            status="ACTIVE",
            source="CLIENT",
            actor=client["short_name"],
            desk=desk,
            product_type="FX_SPOT",
            notional=draw_amount,
            ccy=ccy,
            cpty_id=client["entity_id"],
            correlation={
                "match_type": "CORRELATION",
                "match_status": "UNMATCHED",
                "cardinality": "ONE_TO_ONE",
                "direction": "LHS",
                "actor_role": "SALES",
            },
            payload={
                "client_entity_id": client["entity_id"],
                "on_behalf_of": client["name"],
                "ticket_ref": _gen_id("event"),
                "trade_economics": {
                    "product_type": "FX_SPOT",
                    "direction": direction,
                    "notional": draw_amount,
                    "ccy": ccy,
                    "ccy_pair": ccy_pair,
                    "rate": draw_rate,
                    "value_date": _random_date(1, 60),
                    # Utilization context — visible in blotter
                    "facility_id": facility_id,
                    "facility_limit": facility_limit,
                    "utilized_amount": round(utilized_total, 2),
                    "utilization_pct": round(utilized_total / facility_limit * 100, 1),
                    "contract_ref": contract_ref,
                    "contract_type": contract_type,
                    "draw_num": draw_idx,
                    "total_draws": n_draws,
                },
            },
        )
        events.append(obo)

        # 2. SALES_BOOKING
        econ = _make_trade_economics("FX_SPOT", ccy, draw_amount, draw_rate, ccy_pair)
        legs = _make_legs_for(
            "FX_SPOT", fpml["fpml_id"], ccy, far_ccy, draw_amount, draw_rate
        )
        parties = _make_parties(client["entity_id"], bank["entity_id"])

        sb = _make_event(
            "SALES_BOOKING",
            status="ACTIVE",
            source="MANUAL",
            actor=sales,
            desk=desk,
            product_type="FX_SPOT",
            notional=draw_amount,
            ccy=ccy,
            cpty_id=client["entity_id"],
            links=[
                {"event_id": obo["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"}
            ],
            correlation={
                "match_type": "CORRELATION",
                "scenario": "OBO_BOOKING",
                "match_status": "PARTIAL",
                "cardinality": "ONE_TO_ONE",
                "direction": "LHS",
                "actor_role": "SALES",
                "breaks": [],
                "resolution": None,
                "matched_at": _random_datetime(-5, 0),
                "matched_by": "MATCHING_ENG",
            },
            payload={
                "trade_economics": {
                    **econ,
                    "facility_id": facility_id,
                    "contract_ref": contract_ref,
                    "contract_type": contract_type,
                },
                "book_id": book["book_id"],
                "portfolio": f"FX_COMPENSATION_{random.choice(REGIONS)}",
                "strategy": "Client Hedging",
                "parties": parties,
                "legs": legs,
            },
        )
        events.append(sb)

        # 3. TRADE — materialized with facility/contract context in NED
        trade = _make_event(
            "TRADE",
            status="CONFIRMED",
            source="MATCHING_ENG",
            actor="MATCHING_ENG",
            desk=desk,
            product_type="FX_SPOT",
            notional=draw_amount,
            ccy=ccy,
            cpty_id=client["entity_id"],
            links=[
                {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
                {"event_id": obo["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            ],
            correlation={
                "match_type": "CORRELATION",
                "match_status": "MATCHED",
                "cardinality": "ONE_TO_ONE",
                "direction": "PARENT",
                "actor_role": "SYSTEM",
            },
            enriched=_make_enriched(),
            payload={
                "trade_id": _gen_id("event"),
                "fpml_type": fpml["fpml_id"],
                "trade_date": econ["trade_date"],
                "parties": parties,
                "ned": {
                    "book_id": book["book_id"],
                    "portfolio": f"FX_COMPENSATION_{random.choice(REGIONS)}",
                    "strategy": "Client Hedging",
                    "clearing": None,
                    # Facility/contract tracking
                    "facility_id": facility_id,
                    "contract_ref": contract_ref,
                    "contract_type": contract_type,
                    "draw_num": draw_idx,
                    "utilization_pct": round(utilized_total / facility_limit * 100, 1),
                },
                "legs": legs,
                "uti": _uti(),
                "usi": None,
            },
        )
        events.append(trade)
        trade_events_local.append(trade)

        # 4. SETTLEMENT_INSTR per draw
        si = _make_event(
            "SETTLEMENT_INSTR",
            status="ACTIVE",
            source="MANUAL",
            product_type="FX_SPOT",
            notional=draw_amount,
            ccy=ccy,
            cpty_id=client["entity_id"],
            links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
            correlation={
                "match_type": "CORRELATION",
                "match_status": "PARTIAL",
                "cardinality": "ONE_TO_ONE",
                "direction": "CHILD",
                "actor_role": "OPS",
            },
            payload={
                "payment_direction": direction,
                "amount": draw_amount,
                "ccy": ccy,
                "value_date": econ.get("value_date", _random_date(1, 30)),
                "ssi_id": _gen_id("event"),
                "nostro": f"{random.choice(['JPMC', 'CITI', 'HSBC'])}-{random.choice(['NY', 'LDN', 'TYO'])}",
                "cpty_ssi": _gen_id("event"),
                "cpty_entity_id": client["entity_id"],
                "settlement_method": "NETTING",  # all will be compensated
            },
        )
        events.append(si)
        settlement_events_local.append(si)

    # 5. COMPENSATION — NET_SETTLEMENT across all draws
    # Import draws are PAY, export draws are RECEIVE — net them
    gross_pay = sum(
        s["notional"]
        for s in settlement_events_local
        if s["payload"]["payment_direction"] == "PAY"
    )
    gross_recv = sum(
        s["notional"]
        for s in settlement_events_local
        if s["payload"]["payment_direction"] == "RECEIVE"
    )
    net_amount = round(abs(gross_pay - gross_recv), 2)
    net_direction = "PAY" if gross_pay > gross_recv else "RECEIVE"

    compensation = _make_event(
        "NET_SETTLEMENT",
        status="ACTIVE",
        source="NETTING_ENG",
        product_type="FX_SPOT",
        notional=net_amount,
        ccy=ccy,
        cpty_id=client["entity_id"],
        links=[
            {"event_id": s["event_id"], "rel": "NETS_WITH", "role": "PARENT"}
            for s in settlement_events_local
        ],
        correlation={
            "match_type": "AGGREGATION",
            "scenario": "NETTING",
            "match_status": "MATCHED",
            "cardinality": "MANY_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-1, 0),
            "matched_by": "NETTING_ENG",
        },
        payload={
            "trade_event_ids": [t["event_id"] for t in trade_events_local],
            "net_amount": net_amount,
            "ccy": ccy,
            "value_date": _random_date(1, 10),
            "cpty_entity_id": client["entity_id"],
            "gross_pay": round(gross_pay, 2),
            "gross_receive": round(gross_recv, 2),
            "trade_count": len(trade_events_local),
            # Compensation-specific context
            "compensation_type": "IMPORT_EXPORT",
            "facility_id": facility_id,
            "net_direction": net_direction,
            "import_count": n_imports,
            "export_count": n_draws - n_imports,
            "savings_vs_gross": round(gross_pay + gross_recv - net_amount, 2),
        },
    )
    events.append(compensation)

    return events


# =============================================================================
# SCENARIO: IRS_CLEARING
# RFQ → QUOTE → SALES_BOOKING + TRADING_BOOKING → TRADE → CLEARING_MSG
#
# Real-world: IRS trades are clearing-mandated (Dodd-Frank/EMIR).
# Traded via SEF/D2C (Tradeweb, Bloomberg), cleared through LCH or CME.
# Generates realistic tenor, index, day count, and schedule events.
# =============================================================================

# Realistic IRS reference data
_IRS_BENCHMARKS = {
    "USD": {
        "index": "SOFR",
        "dc_fixed": "30/360",
        "dc_float": "ACT/360",
        "freq_fixed": "6M",
        "freq_float": "3M",
    },
    "EUR": {
        "index": "EURIBOR",
        "dc_fixed": "30/360",
        "dc_float": "ACT/360",
        "freq_fixed": "1Y",
        "freq_float": "6M",
    },
    "GBP": {
        "index": "SONIA",
        "dc_fixed": "ACT/365",
        "dc_float": "ACT/365",
        "freq_fixed": "6M",
        "freq_float": "3M",
    },
    "JPY": {
        "index": "TIBOR",
        "dc_fixed": "ACT/365",
        "dc_float": "ACT/360",
        "freq_fixed": "6M",
        "freq_float": "3M",
    },
}


def _scenario_irs_clearing(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """IRS trade with mandatory clearing — SEF execution + CCP novation.

    Generates: RFQ → QUOTE → SALES_BOOKING + TRADING_BOOKING → TRADE → CLEARING_MSG.
    Legs have realistic fixed/float economics with proper index, day count, frequency.
    Risk measures include DV01, Theta, Rho (rates-appropriate Greeks).
    Schedule events include quarterly/semi-annual resets, fixings, coupons.
    """
    events: list[dict[str, Any]] = []

    # IRS always uses FPML-IRS template
    irs_fpmls = [f for f in fpmls if f["fpml_id"] == "FPML-IRS"]
    _ = irs_fpmls[0] if irs_fpmls else fpmls[0]

    ccy = random.choice(["USD", "EUR", "GBP", "JPY"])
    benchmark = _IRS_BENCHMARKS[ccy]
    notional = round(random.uniform(10_000_000, 500_000_000), 2)
    tenor = random.choice(IRS_TENORS)
    years = int(tenor.replace("Y", ""))
    fixed_rate = round(random.uniform(2.5, 5.5), 4)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader = random.choice(SALES_NAMES), random.choice(TRADER_NAMES)
    desk = random.choice(["Rates Trading", "G10 Rates", "EM Rates"])
    sef = random.choice(["TRADEWEB", "BLOOMBERG"])
    ccp = random.choice(["LCH", "CME"])
    spread_bps = round(random.uniform(-20, 150), 1)
    start = _random_date(-5, 0)
    end = _random_date(years * 365 - 30, years * 365 + 30)

    # Build IRS-specific legs
    legs = [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FIXED",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": fixed_rate,
            "start_date": start,
            "end_date": end,
            "day_count": benchmark["dc_fixed"],
            "index": None,
            "spread_bps": None,
            "fixing_freq": benchmark["freq_fixed"],
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FLOAT",
            "direction": "RECEIVE",
            "notional": notional,
            "ccy": ccy,
            "rate": None,
            "start_date": start,
            "end_date": end,
            "day_count": benchmark["dc_float"],
            "index": benchmark["index"],
            "spread_bps": spread_bps,
            "fixing_freq": benchmark["freq_float"],
        },
    ]

    econ = {
        "product_type": "IRS",
        "trade_date": _random_date(-30, 0),
        "value_date": _random_date(1, 5),
        "direction": "PAY",
        "notional": notional,
        "ccy": ccy,
        "ccy_pair": None,
        "rate": fixed_rate,
        "spread": spread_bps,
        "tenor": tenor,
        "index": benchmark["index"],
    }
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    # RFQ on SEF
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=sef,
        actor=sales,
        desk=desk,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        raw=_make_raw_wire(sef, "FIX", "IRS"),
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": "PAY",
            "product_type": "IRS",
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": None,
            "tenor": tenor,
            "limit_price": round(fixed_rate * random.uniform(0.98, 1.02), 4),
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(3, 8),
        },
    )
    events.append(rfq)

    # QUOTE
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": fixed_rate,
            "spread": spread_bps,
            "valid_until": None,
            "quoted_by": trader,
            "status": "ACCEPTED",
        },
    )
    events.append(quote)

    # SALES_BOOKING + TRADING_BOOKING
    booking_payload = {
        "trade_economics": econ,
        "book_id": book_s["book_id"],
        "portfolio": f"IRS_{ccy}_{random.choice(REGIONS)}",
        "strategy": random.choice(["Market Making", "Flow", "Client Hedging"]),
        "parties": parties,
        "legs": legs,
    }
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": quote["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"}
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload=booking_payload,
    )
    events.append(sb)

    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
            {"event_id": quote["event_id"], "rel": "ORIGINATES_FROM", "role": "RHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={**booking_payload, "book_id": book_t["book_id"]},
    )
    events.append(tb)

    # TRADE — materialized
    trade = _make_event(
        "TRADE",
        status="CLEARED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": "FPML-IRS",
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"IRS_{ccy}_{random.choice(REGIONS)}",
                "strategy": random.choice(["Market Making", "Flow"]),
                "clearing": ccp,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20],
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": _random_datetime(-10, -5),
                "by": "MATCHING_ENG",
                "reason": "Matched",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "CLEARED",
                "at": _random_datetime(-5, 0),
                "by": ccp,
                "reason": f"Cleared by {ccp}",
                "diff": {"clearing_id": {"old": None, "new": _gen_id("event")}},
            },
        ],
        priority="NORMAL",
    )
    events.append(trade)

    # CLEARING_MSG — mandatory for IRS
    ccp_entities = [e for e in entities if e["entity_type"] == "CCP"]
    ccp_entity = (
        random.choice(ccp_entities) if ccp_entities else random.choice(entities[:5])
    )
    clr = _make_event(
        "CLEARING_MSG",
        status="CLEARED",
        source=ccp,
        product_type="IRS",
        notional=notional,
        ccy=ccy,
        cpty_id=ccp_entity["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "ccp": ccp,
            "clearing_id": _gen_id("event"),
            "original_cpty": seller["entity_id"],
            "novated_cpty": ccp_entity["entity_id"],
            "economics": {
                "product_type": "IRS",
                "notional": notional,
                "ccy": ccy,
                "trade_date": econ["trade_date"],
                "value_date": econ["value_date"],
            },
            "margin_required": round(notional * random.uniform(0.03, 0.08), 2),
            "clearing_fee": round(notional * random.uniform(0.0001, 0.0003), 2),
        },
    )
    events.append(clr)

    return events


# =============================================================================
# SCENARIO: BOND_BROKER_EXEC
# ORDER → BROKER_FILL → TRADING_BOOKING → TRADE
#
# Real-world: Corporate/government bonds traded via D2C platforms or voice.
# Settlement via DTCC/Euroclear T+1 or T+2. Fixed coupon with maturity.
# Broker commission as separate fee. Credit risk → rating-sensitive pricing.
# =============================================================================

# Realistic bond issuers and identifiers
_BOND_ISSUERS = [
    ("US Treasury 10Y", "UST", "912810TT0"),
    ("UK Gilt 5Y", "UKT", "GB00BN65R198"),
    ("German Bund 10Y", "DBR", "DE0001102580"),
    ("Japan JGB 20Y", "JGB", "JP1201551L51"),
    ("Apple Inc 3Y", "AAPL", "US037833EK68"),
    ("JP Morgan 5Y", "JPM", "US46625HRR14"),
    ("Volkswagen AG 7Y", "VW", "DE000A3E5WF8"),
    ("BNP Paribas 10Y", "BNP", "FR0014009LG2"),
    ("Goldman Sachs 5Y", "GS", "US38141GZR18"),
    ("Microsoft 10Y", "MSFT", "US594918CB81"),
]


def _scenario_bond_broker_exec(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Corporate/government bond trade via broker execution.

    Generates: ORDER → BROKER_FILL → TRADING_BOOKING → TRADE.
    Bonds have: ISIN, coupon rate, maturity, clean/dirty price, accrued interest.
    Settlement T+1 via DTCC. Risk measures focus on DV01 and credit spread.
    """
    events: list[dict[str, Any]] = []

    bond_fpmls = [f for f in fpmls if f["fpml_id"] == "FPML-BOND"]
    _ = bond_fpmls[0] if bond_fpmls else fpmls[0]

    issuer = random.choice(_BOND_ISSUERS)
    issuer_name, issuer_short, isin = issuer
    ccy = random.choice(["USD", "EUR", "GBP"])
    face_value = round(random.uniform(1_000_000, 50_000_000), 2)
    coupon_rate = round(random.uniform(2.0, 7.0), 4)
    clean_price = round(random.uniform(95.0, 105.0), 4)  # price per 100
    accrued = round(coupon_rate / 365 * random.randint(30, 180), 4)
    dirty_price = round(clean_price + accrued, 4)
    ytm = round(random.uniform(2.5, 6.5), 4)  # yield to maturity
    maturity_years = random.choice([2, 3, 5, 7, 10, 20, 30])

    brokers = [e for e in entities if e["entity_type"] == "BROKER"]
    broker = random.choice(brokers) if brokers else random.choice(entities[:5])
    buyer = random.choice(
        [e for e in entities[:10] if e["entity_id"] != broker["entity_id"]]
    )
    book = random.choice(books)
    trader = random.choice(TRADER_NAMES)
    desk = random.choice(["Credit Trading", "Rates Trading"])

    start = _random_date(-365, 0)
    maturity = _random_date(maturity_years * 365 - 60, maturity_years * 365 + 60)
    legs = [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FIXED",
            "direction": "PAY",
            "notional": face_value,
            "ccy": ccy,
            "rate": coupon_rate,
            "start_date": start,
            "end_date": maturity,
            "day_count": random.choice(["30/360", "ACT/ACT"]),
            "index": None,
            "spread_bps": None,
            "fixing_freq": random.choice(["6M", "1Y"]),
        },
    ]

    econ = {
        "product_type": "BOND",
        "trade_date": _random_date(-10, 0),
        "value_date": _random_date(1, 3),  # T+1 or T+2
        "direction": random.choice(DIRECTIONS),
        "notional": face_value,
        "ccy": ccy,
        "ccy_pair": None,
        "rate": coupon_rate,
        "spread": None,
        # Bond-specific
        "isin": isin,
        "issuer": issuer_name,
        "clean_price": clean_price,
        "dirty_price": dirty_price,
        "accrued_interest": accrued,
        "ytm": ytm,
        "maturity": maturity,
        "coupon_freq": legs[0]["fixing_freq"],
    }

    # ORDER — on D2C platform
    venue = random.choice(["TRADEWEB", "BLOOMBERG", "MARKETAXESS", "BONDPOINT"])
    fill_price = clean_price
    order = _make_event(
        "ORDER",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=face_value,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "order_type": random.choice(["LIMIT", "MARKET"]),
            "direction": econ["direction"],
            "product_type": "BOND",
            "notional": face_value,
            "ccy": ccy,
            "ccy_pair": None,
            "limit_price": round(fill_price * 1.005, 4)
            if random.random() > 0.3
            else None,
            "broker_entity_id": broker["entity_id"],
            "fills": [
                {
                    "qty": face_value,
                    "price": fill_price,
                    "venue": venue,
                    "at": _random_datetime(-3, 0),
                }
            ],
            "vwap": fill_price,
            "filled_qty": face_value,
            "remaining_qty": 0.0,
            # Bond order context
            "isin": isin,
            "issuer": issuer_short,
        },
    )
    events.append(order)

    # BROKER_FILL
    parties = _make_parties(buyer["entity_id"], broker["entity_id"])
    commission = round(face_value * random.uniform(0.0002, 0.0010), 2)
    bf = _make_event(
        "BROKER_FILL",
        status="ACTIVE",
        source="BROKER",
        actor=broker["short_name"],
        desk=desk,
        product_type="BOND",
        notional=face_value,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        links=[{"event_id": order["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "BROKER_RECON",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-2, 0),
            "matched_by": "MATCHING_ENG",
        },
        raw=_make_raw_wire("BROKER", "FIX", "BOND"),
        payload={
            "broker_entity_id": broker["entity_id"],
            "exec_id": _gen_id("event"),
            "price": fill_price,
            "qty": face_value,
            "venue": venue,
            "commission": commission,
            "commission_bps": round(commission / face_value * 10000, 2),
            "product_type": "BOND",
            "ccy": ccy,
            "exec_type": "FILL",
        },
    )
    events.append(bf)

    # TRADING_BOOKING
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=face_value,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        links=[
            {"event_id": order["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"},
            {"event_id": bf["event_id"], "rel": "CORRELATES_WITH", "role": "LHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"BOND_{ccy}_{random.choice(REGIONS)}",
            "strategy": random.choice(["Flow", "Market Making", "Prop"]),
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(tb)

    # TRADE — with bond-specific NED
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type="BOND",
        notional=face_value,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": bf["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": "FPML-BOND",
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"BOND_{ccy}_{random.choice(REGIONS)}",
                "strategy": random.choice(["Flow", "Prop"]),
                "clearing": None,  # bonds typically not centrally cleared
                # Bond-specific
                "isin": isin,
                "issuer": issuer_name,
                "clean_price": clean_price,
                "dirty_price": dirty_price,
                "accrued_interest": accrued,
                "ytm": ytm,
                "settlement_type": "DVP",  # delivery vs payment
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: FX_OPTION_HEDGE
# RFQ → QUOTE → SALES_BOOKING + TRADING_BOOKING → TRADE
#
# Real-world: Corporate client hedges FX exposure via options.
# Option leg (PAY premium for right to exercise) + fee leg (brokerage).
# Greeks: delta, vega, gamma, theta. Exercise/expiry schedule events.
# Premium settlement separate from potential exercise settlement.
# =============================================================================

# Realistic option strategy descriptions
_OPTION_STRATEGIES = [
    "Vanilla Call",
    "Vanilla Put",
    "Risk Reversal",
    "Collar",
    "Straddle",
    "Strangle",
    "Butterfly",
    "Seagull",
]


def _scenario_fx_option_hedge(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """FX Option hedging — client buys option protection.

    Generates: RFQ → QUOTE → SALES_BOOKING + TRADING_BOOKING → TRADE.
    Option leg has strike, premium, expiry, exercise style.
    Fee leg captures upfront premium payment.
    Risk measures: delta, vega, gamma, theta (FX Greeks).
    Schedule events: premium payment, potential exercise, expiry.
    """
    events: list[dict[str, Any]] = []

    opt_fpmls = [f for f in fpmls if f["fpml_id"] == "FPML-FX-OPT"]
    _ = opt_fpmls[0] if opt_fpmls else fpmls[0]

    pair = random.choice(FX_MAJOR_PAIRS)
    ccy, far_ccy = pair[:3], pair[3:]
    notional = round(random.uniform(2_000_000, 75_000_000), 2)
    spot = round(random.uniform(0.8, 1.5), 6)
    option_type = random.choice(["CALL", "PUT"])
    # Strike relative to spot — OTM, ATM, or ITM
    moneyness = random.choice(["OTM", "ATM", "ITM"])
    if moneyness == "ATM":
        strike = spot
    elif moneyness == "OTM":
        strike = round(spot * (1.03 if option_type == "CALL" else 0.97), 6)
    else:
        strike = round(spot * (0.97 if option_type == "CALL" else 1.03), 6)
    expiry_days = random.choice([30, 60, 90, 180, 365])
    expiry = _random_date(expiry_days - 5, expiry_days + 5)
    exercise_style = random.choice(["EUROPEAN", "AMERICAN"])

    # Premium — Black-Scholes-ish (higher for longer tenor, ATM, higher vol)
    base_prem_pct = random.uniform(0.005, 0.04)
    if moneyness == "ATM":
        base_prem_pct *= 1.2
    if expiry_days > 180:
        base_prem_pct *= 1.3
    premium = round(notional * base_prem_pct, 2)
    premium_bps = round(base_prem_pct * 10000, 1)

    # Implied vol
    impl_vol = round(random.uniform(5.0, 25.0), 2)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader = random.choice(SALES_NAMES), random.choice(TRADER_NAMES)
    desk = "FX Options"
    strategy = random.choice(_OPTION_STRATEGIES)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    legs = [
        {
            "leg_id": _gen_id("event"),
            "leg_type": "OPTION",
            "direction": "PAY",
            "notional": notional,
            "ccy": ccy,
            "rate": strike,
            "start_date": _random_date(-2, 0),
            "end_date": expiry,
            "day_count": "ACT/365",
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            # Option-specific
            "option_type": option_type,
            "exercise_style": exercise_style,
            "spot_ref": spot,
            "impl_vol": impl_vol,
            "moneyness": moneyness,
        },
        {
            "leg_id": _gen_id("event"),
            "leg_type": "FEE",
            "direction": "RECEIVE",
            "notional": premium,
            "ccy": far_ccy,
            "rate": None,
            "start_date": _random_date(-2, 0),
            "end_date": _random_date(1, 5),
            "day_count": None,
            "index": None,
            "spread_bps": None,
            "fixing_freq": None,
            "fee_type": "UPFRONT",
            "premium_bps": premium_bps,
        },
    ]

    econ = {
        "product_type": "FX_OPTION",
        "trade_date": _random_date(-30, 0),
        "value_date": _random_date(1, 5),
        "direction": "PAY",
        "notional": notional,
        "ccy": ccy,
        "ccy_pair": pair,
        "rate": strike,
        "spread": None,
        # Option-specific
        "option_type": option_type,
        "strike": strike,
        "spot_ref": spot,
        "premium": premium,
        "premium_ccy": far_ccy,
        "premium_bps": premium_bps,
        "expiry": expiry,
        "exercise_style": exercise_style,
        "impl_vol": impl_vol,
        "moneyness": moneyness,
        "strategy": strategy,
    }

    # RFQ — client requests option pricing
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CLIENT",
        actor=sales,
        desk=desk,
        product_type="FX_OPTION",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": "PAY",
            "product_type": "FX_OPTION",
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": pair,
            "tenor": f"{expiry_days}D",
            "limit_price": None,  # options priced by premium, not limit
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 5),
        },
    )
    events.append(rfq)

    # QUOTE — priced as premium
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="FX_OPTION",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": premium,
            "spread": premium_bps,
            "valid_until": None,
            "quoted_by": trader,
            "status": "ACCEPTED",
        },
    )
    events.append(quote)

    # SALES_BOOKING
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type="FX_OPTION",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": quote["event_id"], "rel": "ORIGINATES_FROM", "role": "LHS"}
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_s["book_id"],
            "portfolio": f"FX_OPTIONS_{random.choice(REGIONS)}",
            "strategy": strategy,
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(sb)

    # TRADING_BOOKING
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="FX_OPTION",
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
            {"event_id": quote["event_id"], "rel": "ORIGINATES_FROM", "role": "RHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-5, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_t["book_id"],
            "portfolio": f"FX_OPTIONS_{random.choice(REGIONS)}",
            "strategy": strategy,
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(tb)

    # TRADE
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type="FX_OPTION",
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": "FPML-FX-OPT",
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"FX_OPTIONS_{random.choice(REGIONS)}",
                "strategy": strategy,
                "clearing": random.choice(["LCH", "CME"])
                if random.random() > 0.7
                else None,
                # Option context
                "option_type": option_type,
                "strike": strike,
                "expiry": expiry,
                "exercise_style": exercise_style,
                "moneyness": moneyness,
                "premium": premium,
                "premium_ccy": far_ccy,
                "impl_vol": impl_vol,
                "spot_ref": spot,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# POST-TRADE EVENT GENERATORS
# =============================================================================


def _parent_scenario(trade_evt: dict, fallback: str) -> str:
    """Inherit scenario from parent trade's correlation, with fallback."""
    corr = trade_evt.get("correlation")
    if isinstance(corr, dict) and corr.get("scenario"):
        return corr["scenario"]
    return fallback


def _parent_chain_id(trade_evt: dict) -> str | None:
    """Inherit chain_id from parent trade's correlation."""
    corr = trade_evt.get("correlation")
    if isinstance(corr, dict):
        return corr.get("chain_id")
    return None


def _add_clearing(trade_evt: dict, entities: list[dict]) -> dict[str, Any]:
    ccp_entities = [e for e in entities if e["entity_type"] == "CCP"]
    ccp = random.choice(ccp_entities) if ccp_entities else random.choice(entities[:5])
    ccp_name = random.choice(CCPS)
    return _make_event(
        "CLEARING_MSG",
        status="CLEARED",
        source=ccp_name,
        product_type=trade_evt["product_type"],
        notional=trade_evt["notional"],
        ccy=trade_evt["ccy"],
        cpty_id=ccp["entity_id"],
        links=[
            {
                "event_id": trade_evt["event_id"],
                "rel": "CORRELATES_WITH",
                "role": "CHILD",
            }
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": _parent_scenario(trade_evt, "CLEARING"),
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "CCP",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-3, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "ccp": ccp_name,
            "clearing_id": _gen_id("event"),
            "original_cpty": trade_evt["cpty_id"],
            "novated_cpty": ccp["entity_id"],
            "economics": {
                "product_type": trade_evt["product_type"],
                "notional": trade_evt["notional"],
                "ccy": trade_evt["ccy"],
                "trade_date": trade_evt["payload"]["trade_date"],
                "value_date": _random_date(1, 30),
            },
            "margin_required": round(
                trade_evt["notional"] * random.uniform(0.02, 0.10), 2
            ),
            "clearing_fee": round(
                trade_evt["notional"] * random.uniform(0.0001, 0.0005), 2
            ),
        },
    )


def _add_affirm(trade_evt: dict, entities: list[dict]) -> dict[str, Any]:
    cpty = random.choice(entities[:10])
    platform = random.choice(["MARKITWIRE", "DTCC"])
    legs = trade_evt["payload"].get("legs", [])
    return _make_event(
        "AFFIRM_MSG",
        status="CONFIRMED",
        source=platform,
        product_type=trade_evt["product_type"],
        notional=trade_evt["notional"],
        ccy=trade_evt["ccy"],
        cpty_id=cpty["entity_id"],
        links=[
            {"event_id": trade_evt["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": _parent_scenario(trade_evt, "CPTY_AFFIRM"),
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "OPS",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-3, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "platform": platform,
            "affirm_id": _gen_id("event"),
            "cpty_entity_id": cpty["entity_id"],
            "affirmed_economics": {
                "product_type": trade_evt["product_type"],
                "direction": random.choice(DIRECTIONS),
                "ccy_pair": legs[0].get("ccy") if legs else None,
                "notional": trade_evt["notional"],
                "ccy": trade_evt["ccy"],
                "rate": legs[0].get("rate") if legs else None,
                "value_date": _random_date(1, 30),
                "far_leg": None,
            },
        },
    )


def _add_settlement(trade_evt: dict, entities: list[dict]) -> dict[str, Any]:
    cpty = random.choice(entities[:10])
    return _make_event(
        "SETTLEMENT_INSTR",
        status="ACTIVE",
        source="MANUAL",
        product_type=trade_evt["product_type"],
        notional=trade_evt["notional"],
        ccy=trade_evt["ccy"],
        cpty_id=cpty["entity_id"],
        links=[
            {
                "event_id": trade_evt["event_id"],
                "rel": "CORRELATES_WITH",
                "role": "CHILD",
            }
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": _parent_scenario(trade_evt, "SETTLEMENT_RECON"),
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "OPS",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-3, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "payment_direction": random.choice(DIRECTIONS),
            "amount": trade_evt["notional"],
            "ccy": trade_evt["ccy"],
            "value_date": _random_date(1, 30),
            "ssi_id": _gen_id("event"),
            "nostro": f"{random.choice(['JPMC', 'CITI', 'HSBC'])}-{random.choice(['NY', 'LDN', 'TYO'])}",
            "cpty_ssi": _gen_id("event"),
            "cpty_entity_id": cpty["entity_id"],
            "settlement_method": random.choice(["RTGS", "NETTING", "CLS", "PVP"]),
        },
    )


def _add_alloc_splits(
    trade_evt: dict, entities: list[dict], books: list[dict]
) -> list[dict[str, Any]]:
    n_splits = random.randint(2, 4)
    total = trade_evt["notional"]
    splits: list[dict[str, Any]] = []
    remaining = total
    for i in range(n_splits):
        qty = round(total / n_splits, 2) if i < n_splits - 1 else round(remaining, 2)
        remaining -= qty
        splits.append(
            _make_event(
                "ALLOC_SPLIT",
                status="ACTIVE",
                source="MANUAL",
                product_type=trade_evt["product_type"],
                notional=qty,
                ccy=trade_evt["ccy"],
                cpty_id=random.choice(entities[:10])["entity_id"],
                links=[
                    {
                        "event_id": trade_evt["event_id"],
                        "rel": "CHILD_OF",
                        "role": "CHILD",
                    }
                ],
                correlation={
                    "match_type": "ALLOCATION",
                    "scenario": _parent_scenario(trade_evt, "BLOCK_ALLOC"),
                    "match_status": "MATCHED",
                    "cardinality": "ONE_TO_MANY",
                    "direction": "CHILD",
                    "actor_role": "OPS",
                    "breaks": [],
                    "resolution": None,
                    "matched_at": _random_datetime(-3, 0),
                    "matched_by": "MATCHING_ENG",
                },
                payload={
                    "block_event_id": trade_evt["event_id"],
                    "account": f"ACC-{random.randint(100, 999)}",
                    "entity_id": random.choice(entities[:10])["entity_id"],
                    "quantity": qty,
                    "book_id": random.choice(books)["book_id"],
                    "split_num": i + 1,
                    "total_splits": n_splits,
                    "price": round(random.uniform(0.5, 5.0), 6),
                    "fees": [
                        {
                            "fee_type": random.choice(FEE_TYPES),
                            "amount": round(qty * random.uniform(0.0001, 0.001), 2),
                            "ccy": trade_evt["ccy"],
                        }
                    ],
                },
            )
        )
    return splits


def _add_amendment(trade_evt: dict) -> list[dict[str, Any]]:
    """Generate 1-3 amendment versions for a trade (multi-step workflow)."""
    amendments: list[dict[str, Any]] = []
    n_versions = random.choices([1, 2, 3], weights=[50, 35, 15])[0]
    prev_evt_id = trade_evt["event_id"]

    for v in range(1, n_versions + 1):
        amd_type = random.choice(AMENDMENT_TYPES)
        # Last version may be APPLIED; earlier ones are APPROVED or REJECTED
        if v == n_versions:
            amd_status = random.choice(["PENDING", "APPROVED", "APPLIED"])
        elif v < n_versions:
            amd_status = random.choice(["REJECTED", "APPROVED"])
        else:
            amd_status = "PENDING"

        amd = _make_event(
            "AMENDMENT",
            status="ACTIVE",
            source="MANUAL",
            product_type=trade_evt["product_type"],
            notional=trade_evt["notional"],
            ccy=trade_evt["ccy"],
            cpty_id=trade_evt["cpty_id"],
            links=[
                {"event_id": trade_evt["event_id"], "rel": "AMENDS", "role": "CHILD"},
                *(
                    []
                    if v == 1
                    else [
                        {"event_id": prev_evt_id, "rel": "SUPERSEDES", "role": "CHILD"}
                    ]
                ),
            ],
            correlation={
                "match_type": "RECONCILIATION",
                "scenario": _parent_scenario(trade_evt, "AMENDMENT_RECON"),
                "match_status": "MATCHED" if amd_status == "APPLIED" else "UNMATCHED",
                "cardinality": "ONE_TO_ONE",
                "direction": "RHS",
                "actor_role": "TRADING",
                "breaks": []
                if amd_status == "APPLIED"
                else [
                    {
                        "field": "amendment_status",
                        "lhs": "ACTIVE",
                        "rhs": amd_status,
                        "tolerance": None,
                    }
                ],
                "resolution": None,
                "matched_at": _random_datetime(-3, 0)
                if amd_status == "APPLIED"
                else None,
                "matched_by": "MATCHING_ENG" if amd_status == "APPLIED" else None,
            },
            payload={
                "target_event_id": trade_evt["event_id"],
                "amendment_type": amd_type,
                "changes": [
                    {
                        "field": random.choice(
                            [
                                "payload.notional",
                                "payload.rate",
                                "ned.book_id",
                                "ned.strategy",
                            ]
                        ),
                        "old": str(round(random.uniform(1e5, 1e7), 2)),
                        "new": str(round(random.uniform(1e5, 1e7), 2)),
                        "reason": random.choice(
                            [
                                "Client request",
                                "Booking error",
                                "Rate correction",
                                "Regulatory",
                            ]
                        ),
                    }
                ],
                "approvals": [
                    {
                        "role": role,
                        "approver": random.choice(TRADER_NAMES),
                        "status": random.choice(["APPROVED", "PENDING", "REJECTED"]),
                        "at": _random_datetime(-3, 0),
                        "comment": None,
                    }
                    for role in random.sample(
                        ["TRADER", "RISK", "OPERATIONS", "COMPLIANCE"],
                        k=random.randint(1, 3),
                    )
                ],
                "amendment_status": amd_status,
            },
            transitions=[
                {
                    "from_status": "PENDING",
                    "to_status": "ACTIVE",
                    "at": _random_datetime(-5, -3),
                    "by": random.choice(TRADER_NAMES),
                    "reason": f"Amendment v{v} submitted",
                    "diff": {},
                },
                *(
                    [
                        {
                            "from_status": "ACTIVE",
                            "to_status": "ACTIVE",
                            "at": _random_datetime(-3, 0),
                            "by": random.choice(TRADER_NAMES),
                            "reason": f"Approval: {amd_status}",
                            "diff": {
                                "amendment_status": {
                                    "old": "PENDING",
                                    "new": amd_status,
                                }
                            },
                        }
                    ]
                    if amd_status != "PENDING"
                    else []
                ),
            ],
        )
        amendments.append(amd)
        prev_evt_id = amd["event_id"]
    return amendments


def _add_risk_measures(trade_evt: dict) -> list[dict[str, Any]]:
    measures: list[dict[str, Any]] = []
    legs = trade_evt["payload"].get("legs", [])
    pt = trade_evt["product_type"]
    # Pick metrics appropriate to asset class
    if pt in ("IRS", "XCCY_SWAP", "SWAPTION", "FRA"):
        metric_pool = ["MTM", "DV01", "THETA", "GAMMA", "RHO"]
    elif pt in ("FX_SPOT", "FX_FORWARD", "FX_SWAP", "FX_NDF", "FX_OPTION"):
        metric_pool = ["MTM", "FXDELTA", "FXVEGA", "THETA", "GAMMA"]
    elif pt == "CDS":
        metric_pool = ["MTM", "CS01", "JUMP_TO_DEFAULT", "RECOVERY_RISK"]
    elif pt == "EQUITY":
        metric_pool = ["MTM", "DELTA", "BETA", "VWAP_SLIPPAGE"]
    else:
        metric_pool = ["MTM", "DV01", "THETA"]

    for _ in range(random.randint(2, 4)):
        leg = random.choice(legs) if legs else None
        measures.append(
            _make_event(
                "RISK_MEASURE",
                status="ACTIVE",
                source="MATCHING_ENG",
                actor="QUANT-ENGINE",
                product_type=pt,
                notional=None,
                ccy=trade_evt["ccy"],
                cpty_id=None,
                links=[
                    {
                        "event_id": trade_evt["event_id"],
                        "rel": "MEASURES",
                        "role": "CHILD",
                    }
                ],
                correlation={
                    "match_type": "CORRELATION",
                    "scenario": _parent_scenario(trade_evt, "RISK"),
                    "match_status": "MATCHED",
                    "cardinality": "ONE_TO_MANY",
                    "direction": "CHILD",
                    "actor_role": "SYSTEM",
                    "breaks": [],
                    "resolution": None,
                    "matched_at": None,
                    "matched_by": None,
                },
                payload={
                    "trade_event_id": trade_evt["event_id"],
                    "leg_event_id": leg["leg_id"] if leg else None,
                    "metric": random.choice(metric_pool),
                    "value": round(random.uniform(-5_000_000, 10_000_000), 2),
                    "denomination": trade_evt["ccy"],
                    "tenor_bucket": random.choice(TENOR_BUCKETS),
                    "curve": f"{trade_evt['ccy']}-{random.choice(INDICES)}-{random.choice(['3M', '6M'])}",
                    "as_of_date": _random_date(-3, 0),
                    "scenario": None,
                },
            )
        )
    return measures


def _add_schedule_events(trade_evt: dict) -> list[dict[str, Any]]:
    schedules: list[dict[str, Any]] = []
    legs = trade_evt["payload"].get("legs", [])
    pt = trade_evt["product_type"]
    for leg in legs[:2]:
        lt = leg.get("leg_type", "SPOT")
        n = random.randint(1, 3) if lt in ("FIXED", "FLOAT") else 1
        for _ in range(n):
            if lt == "FIXED":
                sub = random.choice(["PAYMENT", "COUPON"])
            elif lt == "FLOAT":
                sub = random.choice(["RESET", "FIXING", "PAYMENT"])
            elif lt == "OPTION":
                sub = random.choice(["EXERCISE", "PAYMENT"])
            else:
                sub = "PAYMENT"

            schedules.append(
                _make_event(
                    "SCHEDULE_EVENT",
                    status="ACTIVE",
                    source="MATCHING_ENG",
                    actor="SCHEDULE-SVC",
                    product_type=pt,
                    notional=None,
                    ccy=trade_evt["ccy"],
                    cpty_id=None,
                    links=[
                        {
                            "event_id": trade_evt["event_id"],
                            "rel": "SCHEDULES",
                            "role": "CHILD",
                        }
                    ],
                    correlation={
                        "match_type": "CORRELATION",
                        "scenario": _parent_scenario(trade_evt, "SCHEDULE"),
                        "match_status": "MATCHED",
                        "cardinality": "ONE_TO_MANY",
                        "direction": "CHILD",
                        "actor_role": "SYSTEM",
                        "breaks": [],
                        "resolution": None,
                        "matched_at": None,
                        "matched_by": None,
                    },
                    payload={
                        "trade_event_id": trade_evt["event_id"],
                        "leg_id": leg.get("leg_id", _gen_id("event")),
                        "event_subtype": sub,
                        "date": _random_date(1, 365),
                        "amount": round(random.uniform(10_000, 5_000_000), 2)
                        if sub in ("PAYMENT", "COUPON")
                        else None,
                        "ccy": trade_evt["ccy"],
                        "index": random.choice(INDICES)
                        if sub in ("RESET", "FIXING")
                        else None,
                        "fixing_rate": round(random.uniform(0.5, 6.0), 4)
                        if sub == "FIXING"
                        else None,
                        "fixing_source": random.choice(["REUTERS", "BLOOMBERG", "ICE"])
                        if sub == "FIXING"
                        else None,
                        "schedule_status": random.choice(
                            ["SCHEDULED", "FIXED", "PAID"]
                        ),
                    },
                )
            )
    return schedules


def _add_margin_call(trade_evt: dict, entities: list[dict]) -> dict[str, Any]:
    cpty = random.choice(entities[:10])
    vm = round(random.uniform(100_000, 5_000_000), 2)
    ia = round(random.uniform(50_000, 2_000_000), 2)
    return _make_event(
        "MARGIN_CALL",
        status="ACTIVE",
        source=random.choice(["LCH", "CME", "ICE"]),
        product_type=trade_evt["product_type"],
        notional=vm + ia,
        ccy=trade_evt["ccy"],
        cpty_id=cpty["entity_id"],
        priority="HIGH",
        links=[
            {
                "event_id": trade_evt["event_id"],
                "rel": "CORRELATES_WITH",
                "role": "CHILD",
            }
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": _parent_scenario(trade_evt, "MARGIN_RECON"),
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CCP",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-1, 0),
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "vm_amount": vm,
            "ia_amount": ia,
            "ccy": trade_evt["ccy"],
            "calculation_date": _random_date(-3, 0),
            "cpty_entity_id": cpty["entity_id"],
            "margin_type": random.choice(["VM", "IA", "BOTH"]),
            "collateral_type": random.choice(["CASH", "GOVT_BOND"]),
            "deadline": _random_datetime(0, 2),
        },
    )


def _add_net_settlement(
    settlement_evts: list[dict], entities: list[dict]
) -> dict[str, Any]:
    cpty = random.choice(entities[:10])
    gross_pay = sum(
        s["notional"] or 0
        for s in settlement_evts
        if s["payload"]["payment_direction"] == "PAY"
    )
    gross_recv = sum(
        s["notional"] or 0
        for s in settlement_evts
        if s["payload"]["payment_direction"] == "RECEIVE"
    )
    return _make_event(
        "NET_SETTLEMENT",
        status="ACTIVE",
        source="NETTING_ENG",
        product_type=None,
        notional=abs(gross_pay - gross_recv),
        ccy=settlement_evts[0]["ccy"],
        cpty_id=cpty["entity_id"],
        links=[
            {"event_id": s["event_id"], "rel": "NETS_WITH", "role": "PARENT"}
            for s in settlement_evts
        ],
        correlation={
            "match_type": "AGGREGATION",
            "scenario": _parent_scenario(settlement_evts[0], "NETTING"),
            "match_status": "MATCHED",
            "cardinality": "MANY_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-1, 0),
            "matched_by": "NETTING_ENG",
        },
        payload={
            "trade_event_ids": [s["event_id"] for s in settlement_evts],
            "net_amount": round(abs(gross_pay - gross_recv), 2),
            "ccy": settlement_evts[0]["ccy"],
            "value_date": _random_date(1, 10),
            "cpty_entity_id": cpty["entity_id"],
            "gross_pay": round(gross_pay, 2),
            "gross_receive": round(gross_recv, 2),
            "trade_count": len(settlement_evts),
        },
    )


def _add_position_snapshots(
    books: list[dict], trade_events: list[dict]
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    book_ids_with_trades: set[str] = set()
    for t in trade_events:
        bid = t["payload"].get("ned", {}).get("book_id")
        if bid:
            book_ids_with_trades.add(bid)

    sampled = (
        random.sample(list(book_ids_with_trades), k=min(4, len(book_ids_with_trades)))
        if book_ids_with_trades
        else []
    )
    for book_id in sampled:
        book_trades = [
            t
            for t in trade_events
            if t["payload"].get("ned", {}).get("book_id") == book_id
        ]
        positions = []
        for t in book_trades[:6]:
            positions.append(
                {
                    "product_type": t["product_type"],
                    "ccy": t["ccy"],
                    "ccy_pair": random.choice(FX_MAJOR_PAIRS)
                    if t["product_type"]
                    in ("FX_SPOT", "FX_FORWARD", "FX_SWAP", "FX_NDF", "FX_OPTION")
                    else None,
                    "net_notional": t["notional"],
                    "mtm": round(random.uniform(-2_000_000, 5_000_000), 2),
                    "trade_count": 1,
                    "cpty_id": t["cpty_id"],
                }
            )
        total_mtm = sum(p["mtm"] for p in positions)
        sources = random.sample(
            ["OUR_BOOK", "CPTY_STATEMENT"], k=random.randint(1, 2)
        )
        # MATCHED only when both sides present; UNMATCHED if only one side
        snap_status = "MATCHED" if len(sources) == 2 else "UNMATCHED"
        for source in sources:
            snapshots.append(
                _make_event(
                    "POSITION_SNAPSHOT",
                    status="ACTIVE",
                    source="MATCHING_ENG",
                    actor="RECON-SVC",
                    product_type=None,
                    notional=None,
                    ccy=None,
                    cpty_id=None,
                    correlation={
                        "match_type": "RECONCILIATION",
                        "scenario": "EOD_POSITION",
                        "match_status": snap_status,
                        "cardinality": "ONE_TO_ONE",
                        "direction": "LHS" if source == "OUR_BOOK" else "RHS",
                        "actor_role": "SYSTEM",
                        "breaks": [],
                        "resolution": None,
                        "matched_at": _random_datetime(-1, 0) if snap_status == "MATCHED" else None,
                        "matched_by": "MATCHING_ENG" if snap_status == "MATCHED" else None,
                    },
                    payload={
                        "book_id": book_id,
                        "as_of_date": _random_date(-1, 0),
                        "source": source,
                        "positions": positions,
                        "total_mtm": round(total_mtm, 2),
                    },
                )
            )
    return snapshots


# =============================================================================
# SCENARIO: BACK_TO_BACK
# SALES_BOOKING (sales desk) + TRADING_BOOKING (trading desk) → TRADE
# =============================================================================


def _scenario_back_to_back(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Back-to-back IRS: sales earns spread on client trade, trading hedges with street.

    Flow:
      1. CLIENT_TRADE — client facing, at client rate (sales book)
      2. INTERNAL_TRANSFER — sales book → trading book (sales earns spread)
      3. STREET_HEDGE x2-3 — trading hedges with different counterparties
    """
    events: list[dict[str, Any]] = []
    pt = "IRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    client_rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    fpml_irs = next((f for f in fpmls if f["product_type"] == "IRS"), fpmls[0])

    # Sales earns spread: client rate vs mid-market rate
    sales_spread_bps = round(random.uniform(2.0, 8.0), 2)
    mid_rate = round(client_rate - sales_spread_bps / 10_000, 6)

    client_econ = _make_trade_economics(pt, ccy, notional, client_rate, ccy_pair)
    client_legs = _make_legs_for(
        pt, fpml_irs["fpml_id"], ccy, far_ccy, notional, client_rate
    )
    client_parties = _make_parties(
        buyer["entity_id"], random.choice(entities[:10])["entity_id"]
    )

    # 1. CLIENT_TRADE — client facing, at client rate (sales book)
    client_trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "SALES",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_irs["fpml_id"],
            "trade_date": client_econ["trade_date"],
            "parties": client_parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Client Hedging",
                "clearing": random.choice(CCPS) if random.random() > 0.3 else None,
            },
            "legs": client_legs,
            "uti": _uti(),
            "usi": _uti()[:20],
            "trade_type": "CLIENT",
            "sales_spread_bps": sales_spread_bps,
        },
    )
    events.append(client_trade)

    # 2. INTERNAL_TRANSFER — sales book → trading book (sales earns spread)
    transfer = _make_event(
        "INTERNAL_TRANSFER",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "CORRELATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "TRADING",
        },
        links=[
            {
                "event_id": client_trade["event_id"],
                "rel": "ORIGINATES_FROM",
                "role": "LHS",
            }
        ],
        payload={
            "from_book": book_s["book_id"],
            "to_book": book_t["book_id"],
            "from_desk": "SALES_DESK",
            "to_desk": "TRADING_DESK",
            "transfer_rate": mid_rate,
            "client_rate": client_rate,
            "sales_spread_bps": sales_spread_bps,
            "sales_pnl": round(notional * sales_spread_bps / 10_000, 2),
            "trade_economics": _make_trade_economics(
                pt, ccy, notional, mid_rate, ccy_pair
            ),
        },
    )
    events.append(transfer)

    # 3. STREET_HEDGE trades — trading hedges with different counterparties
    n_hedges = random.randint(2, 3)
    hedge_notionals = []
    remaining = notional
    for i in range(n_hedges):
        if i < n_hedges - 1:
            hedge_not = round(notional * random.uniform(0.3, 0.5), 2)
            hedge_not = min(
                hedge_not, remaining - 1_000_000
            )  # leave room for last hedge
        else:
            hedge_not = round(remaining, 2)
        hedge_notionals.append(hedge_not)
        remaining -= hedge_not

    for i, hedge_not in enumerate(hedge_notionals):
        street_cpty = random.choice(
            [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
        )
        hedge_rate = round(mid_rate + random.uniform(-0.5, 0.5) / 10_000, 6)
        trading_spread_bps = round((mid_rate - hedge_rate) * 10_000, 2)
        hedge_legs = _make_legs_for(
            pt, fpml_irs["fpml_id"], ccy, far_ccy, hedge_not, hedge_rate
        )
        hedge_parties = _make_parties(
            street_cpty["entity_id"], random.choice(entities[:10])["entity_id"]
        )

        hedge = _make_event(
            "TRADE",
            status="CONFIRMED",
            source="MANUAL",
            actor=trader,
            desk=desk,
            product_type=pt,
            notional=hedge_not,
            ccy=ccy,
            cpty_id=street_cpty["entity_id"],
            links=[
                {
                    "event_id": transfer["event_id"],
                    "rel": "ORIGINATES_FROM",
                    "role": "HEDGE",
                },
                {
                    "event_id": client_trade["event_id"],
                    "rel": "HEDGES",
                    "role": "STREET",
                },
            ],
            correlation={
                "match_type": "CORRELATION",
                "match_status": "MATCHED",
                "cardinality": "MANY_TO_ONE",
                "direction": "RHS",
                "actor_role": "TRADING",
            },
            enriched=_make_enriched(),
            payload={
                "trade_id": _gen_id("event"),
                "fpml_type": fpml_irs["fpml_id"],
                "trade_date": client_econ["trade_date"],
                "parties": hedge_parties,
                "ned": {
                    "book_id": book_t["book_id"],
                    "portfolio": f"{pt}_{random.choice(REGIONS)}",
                    "strategy": "Market Making",
                    "clearing": random.choice(CCPS) if random.random() > 0.3 else None,
                },
                "legs": hedge_legs,
                "uti": _uti(),
                "usi": _uti()[:20],
                "trade_type": "STREET_HEDGE",
                "hedge_number": i + 1,
                "total_hedges": n_hedges,
                "trading_spread_bps": trading_spread_bps,
            },
        )
        events.append(hedge)

    return events


# =============================================================================
# SCENARIO: TRADE_CONFIRM
# SALES_BOOKING → AFFIRM_MSG from counterparty (always matched)
# =============================================================================


def _scenario_trade_confirm(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Sales booking directly confirmed by counterparty — always matched."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    sales, desk = random.choice(SALES_NAMES), random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    match_time = _random_datetime(-3, 0)

    # SALES_BOOKING (LHS)
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "TRADE_CONFIRM",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(sb)

    # AFFIRM_MSG from counterparty (RHS)
    platform = random.choice(["MARKITWIRE", "DTCC"])
    affirm = _make_event(
        "AFFIRM_MSG",
        status="CONFIRMED",
        source=platform,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "TRADE_CONFIRM",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "OPS",
            "breaks": [],
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "platform": platform,
            "affirm_id": _gen_id("event"),
            "cpty_entity_id": seller["entity_id"],
            "affirmed_economics": {
                "product_type": pt,
                "direction": random.choice(DIRECTIONS),
                "ccy_pair": ccy_pair,
                "notional": notional,
                "ccy": ccy,
                "rate": rate,
                "value_date": _random_date(1, 30),
                "far_leg": None,
            },
        },
    )
    events.append(affirm)
    return events


# =============================================================================
# SCENARIO: EOD_POSITION
# Two position snapshots from different sources
# =============================================================================


def _scenario_eod_position(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """EOD position recon — OUR_BOOK vs CPTY_STATEMENT snapshots."""
    events: list[dict[str, Any]] = []
    book = random.choice(books)
    is_matched = random.random() < 0.5
    match_status = "MATCHED" if is_matched else "UNMATCHED"
    match_time = _random_datetime(-1, 0)

    # Build shared positions
    n_pos = random.randint(2, 5)
    positions = []
    for _ in range(n_pos):
        pt = random.choice(PRODUCT_TYPES)
        positions.append(
            {
                "product_type": pt,
                "ccy": random.choice(CURRENCIES[:5]),
                "ccy_pair": random.choice(FX_MAJOR_PAIRS)
                if pt in ("FX_SPOT", "FX_FORWARD", "FX_SWAP", "FX_NDF", "FX_OPTION")
                else None,
                "net_notional": round(random.uniform(500_000, 50_000_000), 2),
                "mtm": round(random.uniform(-2_000_000, 5_000_000), 2),
                "trade_count": random.randint(1, 10),
                "cpty_id": random.choice(entities[:10])["entity_id"],
            }
        )
    total_mtm = sum(p["mtm"] for p in positions)

    breaks: list[dict[str, Any]] = []
    if not is_matched:
        breaks = [
            {
                "field": random.choice(["mtm", "net_notional"]),
                "lhs": str(round(total_mtm, 2)),
                "rhs": str(round(total_mtm * random.uniform(0.98, 1.02), 2)),
                "tolerance": "1000",
            },
        ]

    # POSITION_SNAPSHOT from OUR_BOOK (LHS)
    snap_lhs = _make_event(
        "POSITION_SNAPSHOT",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="RECON-SVC",
        product_type=None,
        notional=None,
        ccy=None,
        cpty_id=None,
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "EOD_POSITION",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "book_id": book["book_id"],
            "as_of_date": _random_date(-1, 0),
            "source": "OUR_BOOK",
            "positions": positions,
            "total_mtm": round(total_mtm, 2),
        },
    )
    events.append(snap_lhs)

    # POSITION_SNAPSHOT from CPTY_STATEMENT (RHS)
    snap_rhs = _make_event(
        "POSITION_SNAPSHOT",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="RECON-SVC",
        product_type=None,
        notional=None,
        ccy=None,
        cpty_id=None,
        links=[
            {"event_id": snap_lhs["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "EOD_POSITION",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "book_id": book["book_id"],
            "as_of_date": _random_date(-1, 0),
            "source": "CPTY_STATEMENT",
            "positions": positions,
            "total_mtm": round(
                total_mtm * (1 if is_matched else random.uniform(0.98, 1.02)), 2
            ),
        },
    )
    events.append(snap_rhs)
    return events


# =============================================================================
# SCENARIO: SETTLEMENT_RECON
# Settlement instruction vs cleared trade
# =============================================================================


def _scenario_settlement_recon(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Settlement instruction vs cleared trade — 60% matched, 40% partial."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    desk = random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    is_matched = random.random() < 0.6
    match_status = "MATCHED" if is_matched else "UNMATCHED"
    match_time = _random_datetime(-3, 0)
    breaks: list[dict[str, Any]] = []
    if not is_matched:
        breaks = [
            {
                "field": "amount",
                "lhs": str(notional),
                "rhs": str(round(notional * random.uniform(0.99, 1.01), 2)),
                "tolerance": "100",
            }
        ]

    # TRADE (LHS, status=CLEARED)
    trade = _make_event(
        "TRADE",
        status="CLEARED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "SETTLEMENT_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS),
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20] if pt == "IRS" else None,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": _random_datetime(-10, -5),
                "by": "MATCHING_ENG",
                "reason": "Matched",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "CLEARED",
                "at": _random_datetime(-5, -2),
                "by": random.choice(CCPS),
                "reason": "Cleared",
                "diff": {},
            },
        ],
    )
    events.append(trade)

    # SETTLEMENT_INSTR (RHS)
    si = _make_event(
        "SETTLEMENT_INSTR",
        status="ACTIVE",
        source="MANUAL",
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": trade["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "SETTLEMENT_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "OPS",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "payment_direction": random.choice(DIRECTIONS),
            "amount": notional
            if is_matched
            else round(notional * random.uniform(0.99, 1.01), 2),
            "ccy": ccy,
            "value_date": _random_date(1, 30),
            "ssi_id": _gen_id("event"),
            "nostro": f"{random.choice(['JPMC', 'CITI', 'HSBC'])}-{random.choice(['NY', 'LDN', 'TYO'])}",
            "cpty_ssi": _gen_id("event"),
            "cpty_entity_id": seller["entity_id"],
            "settlement_method": random.choice(["RTGS", "NETTING", "CLS", "PVP"]),
        },
    )
    events.append(si)
    return events


# =============================================================================
# SCENARIO: MARGIN_RECON
# Margin call vs computed exposure
# =============================================================================


def _scenario_margin_recon(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Margin call vs computed exposure — 50% matched, 50% partial."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, _far_ccy, _ccy_pair = _pick_ccy_pair(pt)
    buyer = random.choice(entities[:10])
    ccp_source = random.choice(["LCH", "CME", "ICE"])

    vm = round(random.uniform(100_000, 5_000_000), 2)
    ia = round(random.uniform(50_000, 2_000_000), 2)
    call_amount = vm + ia

    is_matched = random.random() < 0.5
    match_status = "MATCHED" if is_matched else "UNMATCHED"
    match_time = _random_datetime(-1, 0)
    breaks: list[dict[str, Any]] = []
    if not is_matched:
        breaks = [
            {
                "field": "call_amount",
                "lhs": str(call_amount),
                "rhs": str(round(call_amount * random.uniform(0.97, 1.03), 2)),
                "tolerance": "5000",
            }
        ]

    # MARGIN_CALL (LHS)
    mc = _make_event(
        "MARGIN_CALL",
        status="ACTIVE",
        source=ccp_source,
        product_type=pt,
        notional=call_amount,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        priority="HIGH",
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "MARGIN_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CCP",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "vm_amount": vm,
            "ia_amount": ia,
            "ccy": ccy,
            "calculation_date": _random_date(-3, 0),
            "cpty_entity_id": buyer["entity_id"],
            "margin_type": random.choice(["VM", "IA", "BOTH"]),
            "collateral_type": random.choice(["CASH", "GOVT_BOND"]),
            "deadline": _random_datetime(0, 2),
        },
    )
    events.append(mc)

    # Synthetic RISK_MEASURE representing computed exposure (RHS)
    computed_exposure = (
        call_amount
        if is_matched
        else round(call_amount * random.uniform(0.97, 1.03), 2)
    )
    rm = _make_event(
        "RISK_MEASURE",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="QUANT-ENGINE",
        product_type=pt,
        notional=None,
        ccy=ccy,
        cpty_id=None,
        links=[
            {"event_id": mc["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "MARGIN_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_event_id": None,
            "leg_event_id": None,
            "metric": "EXPOSURE",
            "value": computed_exposure,
            "denomination": ccy,
            "tenor_bucket": None,
            "curve": None,
            "as_of_date": _random_date(-1, 0),
            "scenario": "MARGIN_RECON",
        },
    )
    events.append(rm)
    return events


# =============================================================================
# SCENARIO: REGULATORY_RECON
# Regulatory vs internal position snapshots
# =============================================================================


def _scenario_regulatory_recon(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Regulatory snapshot vs internal — 40% matched, 60% partial."""
    events: list[dict[str, Any]] = []
    book = random.choice(books)
    is_matched = random.random() < 0.4
    match_status = "MATCHED" if is_matched else "UNMATCHED"
    match_time = _random_datetime(-1, 0)

    # Build shared positions
    n_pos = random.randint(2, 4)
    positions = []
    for _ in range(n_pos):
        pt = random.choice(PRODUCT_TYPES)
        positions.append(
            {
                "product_type": pt,
                "ccy": random.choice(CURRENCIES[:5]),
                "ccy_pair": random.choice(FX_MAJOR_PAIRS)
                if pt in ("FX_SPOT", "FX_FORWARD", "FX_SWAP", "FX_NDF", "FX_OPTION")
                else None,
                "net_notional": round(random.uniform(500_000, 50_000_000), 2),
                "mtm": round(random.uniform(-2_000_000, 5_000_000), 2),
                "trade_count": random.randint(1, 10),
                "cpty_id": random.choice(entities[:10])["entity_id"],
            }
        )
    total_mtm = sum(p["mtm"] for p in positions)

    breaks: list[dict[str, Any]] = []
    if not is_matched:
        break_field = random.choice(["mtm", "net_notional", "trade_count"])
        breaks = [
            {
                "field": break_field,
                "lhs": str(round(total_mtm, 2)),
                "rhs": str(round(total_mtm * random.uniform(0.95, 1.05), 2)),
                "tolerance": "5000",
            },
        ]

    # POSITION_SNAPSHOT from REGULATORY (LHS)
    snap_lhs = _make_event(
        "POSITION_SNAPSHOT",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="RECON-SVC",
        product_type=None,
        notional=None,
        ccy=None,
        cpty_id=None,
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "REGULATORY_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "book_id": book["book_id"],
            "as_of_date": _random_date(-1, 0),
            "source": "REGULATORY",
            "positions": positions,
            "total_mtm": round(total_mtm, 2),
        },
    )
    events.append(snap_lhs)

    # POSITION_SNAPSHOT from INTERNAL (RHS)
    snap_rhs = _make_event(
        "POSITION_SNAPSHOT",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="RECON-SVC",
        product_type=None,
        notional=None,
        ccy=None,
        cpty_id=None,
        links=[
            {"event_id": snap_lhs["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "scenario": "REGULATORY_RECON",
            "match_status": match_status,
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "book_id": book["book_id"],
            "as_of_date": _random_date(-1, 0),
            "source": "INTERNAL",
            "positions": positions,
            "total_mtm": round(
                total_mtm * (1 if is_matched else random.uniform(0.95, 1.05)), 2
            ),
        },
    )
    events.append(snap_rhs)
    return events


# =============================================================================
# SCENARIO: COMPRESSION
# Trade compression (N→1) — 3 source trades compressed into 1
# =============================================================================


def _scenario_compression(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Trade compression — 3 TRADE events compressed into 1 replacement trade."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    desk = random.choice(DESKS)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    # 3 source trades — same product/ccy/cpty
    source_trades: list[dict[str, Any]] = []
    total_notional = 0.0
    for _ in range(3):
        notional = _notional_for(pt)
        total_notional += notional
        rate = _rate_for(pt)
        econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
        legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
        trade = _make_event(
            "TRADE",
            status="CONFIRMED",
            source="MATCHING_ENG",
            actor="MATCHING_ENG",
            desk=desk,
            product_type=pt,
            notional=notional,
            ccy=ccy,
            cpty_id=buyer["entity_id"],
            enriched=_make_enriched(),
            payload={
                "trade_id": _gen_id("event"),
                "fpml_type": fpml["fpml_id"],
                "trade_date": econ["trade_date"],
                "parties": parties,
                "ned": {
                    "book_id": book["book_id"],
                    "portfolio": f"{pt}_{random.choice(REGIONS)}",
                    "strategy": random.choice(STRATEGIES),
                    "clearing": random.choice(CCPS) if random.random() > 0.4 else None,
                },
                "legs": legs,
                "uti": _uti(),
                "usi": _uti()[:20] if pt == "IRS" else None,
            },
        )
        events.append(trade)
        source_trades.append(trade)

    # Compressed replacement trade (PARENT) — notional = sum of sources
    compressed_notional = round(total_notional, 2)
    compressed_rate = _rate_for(pt)
    compressed_legs = _make_legs_for(
        pt, fpml["fpml_id"], ccy, far_ccy, compressed_notional, compressed_rate
    )
    compressed_econ = _make_trade_economics(
        pt, ccy, compressed_notional, compressed_rate, ccy_pair
    )

    compressed = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="COMPRESSION-SVC",
        desk=desk,
        product_type=pt,
        notional=compressed_notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": t["event_id"], "rel": "COMPRESSES_TO", "role": "PARENT"}
            for t in source_trades
        ],
        correlation={
            "match_type": "AGGREGATION",
            "scenario": "COMPRESSION",
            "match_status": "MATCHED",
            "cardinality": "MANY_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
            "breaks": [],
            "resolution": None,
            "matched_at": _random_datetime(-1, 0),
            "matched_by": "COMPRESSION-SVC",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": compressed_econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.3 else None,
            },
            "legs": compressed_legs,
            "uti": _uti(),
            "usi": _uti()[:20] if pt == "IRS" else None,
            "compression_context": {
                "source_trade_count": 3,
                "source_trade_ids": [t["event_id"] for t in source_trades],
                "gross_notional": compressed_notional,
                "compression_ratio": round(
                    compressed_notional / max(compressed_notional, 1), 2
                ),
            },
        },
    )
    events.append(compressed)
    return events


# =============================================================================
# SCENARIO: DISPUTE
# SALES_BOOKING + TRADING_BOOKING initially matched, then disputed
# =============================================================================


def _scenario_dispute(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Disputed matched pair — bookings matched then moved to DISPUTED status."""
    events: list[dict[str, Any]] = []
    pt = "EQUITY"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    fpml_eq = next((f for f in fpmls if f["product_type"] == "EQUITY"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_eq["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    # 1-2 field mismatches for the dispute
    break_fields = random.sample(
        ["notional", "rate", "value_date", "ccy"], k=random.randint(1, 2)
    )
    breaks = [
        {
            "field": f,
            "lhs": str(round(random.uniform(1e5, 1e7), 2)),
            "rhs": str(round(random.uniform(1e5, 1e7), 2)),
            "tolerance": "100",
        }
        for f in break_fields
    ]
    match_time = _random_datetime(-10, -5)
    dispute_time = _random_datetime(-5, 0)

    # SALES_BOOKING (LHS) — status reflects dispute
    sb = _make_event(
        "SALES_BOOKING",
        status="PENDING",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_s["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "MATCHED",
                "at": match_time,
                "by": "MATCHING_ENG",
                "reason": "Auto-matched",
                "diff": {},
            },
            {
                "from_status": "MATCHED",
                "to_status": "DISPUTED",
                "at": dispute_time,
                "by": random.choice(TRADER_NAMES),
                "reason": "Break detected — under review",
                "diff": {"match_status": {"old": "MATCHED", "new": "DISPUTED"}},
            },
        ],
        priority="HIGH",
    )
    events.append(sb)

    # TRADING_BOOKING (RHS) — status reflects dispute
    tb = _make_event(
        "TRADING_BOOKING",
        status="PENDING",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_TRADER",
            "match_status": "BREAK",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": breaks,
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "MATCHED",
                "at": match_time,
                "by": "MATCHING_ENG",
                "reason": "Auto-matched",
                "diff": {},
            },
            {
                "from_status": "MATCHED",
                "to_status": "DISPUTED",
                "at": dispute_time,
                "by": random.choice(TRADER_NAMES),
                "reason": "Break detected — under review",
                "diff": {"match_status": {"old": "MATCHED", "new": "DISPUTED"}},
            },
        ],
        priority="HIGH",
    )
    events.append(tb)
    return events


# =============================================================================
# SCENARIO: RFQ_MISS
# CLIENT_RFQ v1 → QUOTE v1 → CLIENT_RFQ v2 (revised) → QUOTE v2 → CLIENT_RFQ v3 (TRADED_AWAY)
# =============================================================================


def _scenario_rfq_miss(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """RFQ negotiation that ends with the client going elsewhere (TRADED_AWAY)."""
    events: list[dict[str, Any]] = []
    pt = "FX_FORWARD"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    direction = random.choice(DIRECTIONS)

    # ~30% of RFQ chains originate from chat
    _chat_src = random.choice(["BLOOMBERG_CHAT", "SYMPHONY"]) if random.random() < 0.3 else None
    _thr_id = f"THR-{uuid.uuid4().hex[:12].upper()}" if _chat_src else None

    # RFQ v1 — initial request
    rfq_v1 = _make_event(
        "RFQ",
        status="ACTIVE",
        source=_chat_src or "CLIENT",
        actor=sales,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": round(rate * 0.99, 6),
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 5),
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq_v1)

    # QUOTE v1 — indicative response
    quote_v1 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v1["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq_v1["event_id"],
            "price": round(rate * 1.005, 6),
            "spread": round(random.uniform(1.0, 5.0), 2),
            "valid_until": None,
            "quoted_by": trader,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(quote_v1)

    # RFQ v2 — client revises (tighter notional or better limit)
    revised_notional = round(notional * 0.8, 2)
    rfq_v2 = _make_event(
        "RFQ",
        status="ACTIVE",
        source=_chat_src or "CLIENT",
        actor=sales,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=revised_notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": revised_notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": round(rate * 1.001, 6),
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 5),
            "revision": 2,
            "negotiation_status": "REVISED",
            "revision_reason": "Client adjusted notional",
        },
    )
    events.append(rfq_v2)

    # QUOTE v2 — firm quote
    quote_v2 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=revised_notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_v2["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
            {"event_id": quote_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq_v2["event_id"],
            "price": round(rate * 1.002, 6),
            "spread": round(random.uniform(0.5, 3.0), 2),
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 2,
        },
    )
    events.append(quote_v2)

    # RFQ v3 — TRADED_AWAY (client went with another dealer)
    rfq_v3 = _make_event(
        "RFQ",
        status="TRADED_AWAY",
        source=_chat_src or "CLIENT",
        actor=sales,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=revised_notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq_v2["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "EXPIRED",
            "cardinality": "ONE_TO_ONE",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": revised_notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 5),
            "revision": 3,
            "negotiation_status": "TRADED_AWAY",
            "revision_reason": random.choice(
                [
                    "Better price from competitor",
                    "Client preferred alternate dealer",
                    "Tighter spread elsewhere",
                ]
            ),
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "TRADED_AWAY",
                "at": _random_datetime(-3, 0),
                "by": "CLIENT",
                "reason": "Client traded with another dealer",
                "diff": {},
            },
        ],
    )
    events.append(rfq_v3)
    return events


# =============================================================================
# SCENARIO: COMPETITIVE_RFQ
# 1 CLIENT_RFQ → N DEALER_QUOTEs → CLIENT_ACCEPT best → TRADE (losers TRADED_AWAY)
# Bloomberg ALLQ pattern: multi-dealer competitive quoting
# =============================================================================


def _scenario_competitive_rfq(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Multi-dealer RFQ: client sends to 3 dealers, best quote wins."""
    events: list[dict[str, Any]] = []
    pt = "IRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    buyer = random.choice(entities[:10])
    # Pick 3 distinct dealers
    dealer_pool = [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    dealers = random.sample(dealer_pool, min(3, len(dealer_pool)))
    dealer_ids = [d["entity_id"] for d in dealers]
    book = random.choice(books)
    sales = random.choice(SALES_NAMES)
    desk = random.choice(DESKS)
    direction = random.choice(DIRECTIONS)

    # ~30% from chat
    _chat_src = (
        random.choice(["BLOOMBERG_CHAT", "SYMPHONY"]) if random.random() < 0.3 else None
    )
    _thr_id = f"THR-{uuid.uuid4().hex[:12].upper()}" if _chat_src else None

    # ── RFQ (COMPETITIVE mode, sent to 3 dealers) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=_chat_src or "CLIENT",
        actor=sales,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_MANY",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": random.choice(["2Y", "5Y", "10Y"]),
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": len(dealers),
            "dealer_entity_ids": dealer_ids,
            "rfq_mode": "COMPETITIVE",
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── 3 COMPETING QUOTEs (one per dealer, different prices) ──
    quotes = []
    base_rate = _rate_for(pt)
    for i, dealer in enumerate(dealers):
        # Each dealer quotes a slightly different rate
        dealer_rate = round(base_rate * random.uniform(0.995, 1.005), 6)
        dealer_spread = round(random.uniform(0.5, 5.0), 2)
        trader = random.choice(TRADER_NAMES)

        quote_links: list[dict[str, Any]] = [
            {"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
        ]
        # Link to prior quotes with COMPETES_WITH
        for prior_q in quotes:
            quote_links.append(
                {"event_id": prior_q["event_id"], "rel": "COMPETES_WITH", "role": "RHS"}
            )

        q = _make_event(
            "QUOTE",
            status="ACTIVE",
            source="MANUAL",
            actor=trader,
            desk=desk,
            thread_id=_thr_id,
            product_type=pt,
            notional=notional,
            ccy=ccy,
            cpty_id=buyer["entity_id"],
            links=quote_links,
            correlation={
                "match_type": "NEGOTIATION",
                "match_status": "QUOTED",
                "cardinality": "ONE_TO_MANY",
                "actor_role": "TRADING",
            },
            payload={
                "rfq_event_id": rfq["event_id"],
                "price": dealer_rate,
                "spread": dealer_spread,
                "valid_until": None,
                "quoted_by": trader,
                "status": "FIRM",
                "dealer_entity_id": dealer["entity_id"],
                "dealer_rank": None,  # ranked after all quotes received
                "is_winner": None,
            },
        )
        quotes.append(q)
        events.append(q)

    # ── Rank quotes by price (best = lowest for PAY, highest for RECEIVE) ──
    if direction == "PAY":
        ranked = sorted(quotes, key=lambda q: q["payload"]["price"])
    else:
        ranked = sorted(quotes, key=lambda q: q["payload"]["price"], reverse=True)

    for rank, q in enumerate(ranked, 1):
        q["payload"]["dealer_rank"] = rank
        q["payload"]["is_winner"] = rank == 1

    winner = ranked[0]

    # ── Mark losing quotes as TRADED_AWAY ──
    for q in ranked[1:]:
        q["status"] = "TRADED_AWAY"
        q["payload"]["status"] = "TRADED_AWAY"

    # ── RFQ v2 — CLIENT ACCEPTS best quote ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source=_chat_src or "CLIENT",
        actor=sales,
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_MANY",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": rfq["payload"]["tenor"],
            "limit_price": winner["payload"]["price"],
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": len(dealers),
            "dealer_entity_ids": dealer_ids,
            "rfq_mode": "COMPETITIVE",
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": winner["event_id"],
        },
    )
    events.append(rfq_accept)

    # ── TRADE (materialized from winning quote) ──
    fpml = next((f for f in fpmls if f["product_type"] == pt), fpmls[0])
    rate = winner["payload"]["price"]
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    winning_dealer = next(
        (d for d in dealers if d["entity_id"] == winner["payload"]["dealer_entity_id"]),
        dealers[0],
    )
    parties = _make_parties(buyer["entity_id"], winning_dealer["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        thread_id=_thr_id,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": winner["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_MANY",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": "LCH",
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
        priority=random.choice(["NORMAL", "HIGH"]),
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: SALES_DIRECT
# SALES_BOOKING → TRADING_ACCEPT → TRADE
# =============================================================================


def _scenario_sales_direct(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Sales books directly, trader reviews and accepts — no separate trading booking."""
    events: list[dict[str, Any]] = []
    pt = "FRA"
    fpml_id = "FPML-FRA"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    accept_time = _random_datetime(-5, 0)

    # SALES_BOOKING — sales enters the deal
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "SALES_DIRECT",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": accept_time,
            "matched_by": trader,
        },
        payload={
            "trade_economics": econ,
            "book_id": book["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(sb)

    # TRADING_ACCEPT — trader reviews and approves
    ta = _make_event(
        "TRADING_ACCEPT",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": sb["event_id"], "rel": "APPROVES", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "sales_booking_id": sb["event_id"],
            "reviewed_by": trader,
            "accepted_at": accept_time,
            "comments": random.choice(
                [
                    "Price within tolerance",
                    "Good client flow",
                    "Acceptable risk",
                ]
            ),
            "risk_check": random.choice(["PASS", "PASS", "REVIEW"]),
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "ACTIVE",
                "at": accept_time,
                "by": trader,
                "reason": "Trader accepted sales booking",
                "diff": {},
            },
        ],
    )
    events.append(ta)

    # TRADE (materialized)
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": ta["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: TRADER_FIRST
# TRADING_BOOKING (UNMATCHED) → [time passes] → SALES_BOOKING → MATCH → TRADE
# =============================================================================


def _scenario_trader_first(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Trader books first (sales missed window), sales catches up, then matched."""
    events: list[dict[str, Any]] = []
    pt = "REPO"
    fpml_id = "FPML-REPO"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    match_time = _random_datetime(-2, 0)
    trading_time = _random_datetime(-15, -10)
    sales_time = _random_datetime(-5, -3)

    # TRADING_BOOKING — trader books first, sits unmatched
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        created_at=trading_time,
        correlation={
            "match_type": "CORRELATION",
            "scenario": "TRADER_FIRST",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
            "breaks": [],
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "UNMATCHED",
                "at": trading_time,
                "by": "SYSTEM",
                "reason": "Created — no matching sales booking",
                "diff": {},
            },
            {
                "from_status": "UNMATCHED",
                "to_status": "MATCHED",
                "at": match_time,
                "by": "MATCHING_ENG",
                "reason": "Sales booking arrived — auto-matched",
                "diff": {},
            },
        ],
    )
    events.append(tb)

    # SALES_BOOKING — sales catches up later
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=sales_time,
        links=[{"event_id": tb["event_id"], "rel": "CORRELATES_WITH", "role": "LHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "TRADER_FIRST",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": match_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_s["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(sb)

    # MATCH — explicit match event linking both bookings
    match_evt = _make_event(
        "MATCH",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=match_time,
        links=[
            {"event_id": tb["event_id"], "rel": "MATCHES", "role": "RHS"},
            {"event_id": sb["event_id"], "rel": "MATCHES", "role": "LHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        payload={
            "match_type": "EXACT",
            "confidence": 1.0,
            "lhs_event_id": sb["event_id"],
            "rhs_event_id": tb["event_id"],
            "matched_fields": ["product_type", "notional", "ccy", "rate", "value_date"],
            "break_fields": [],
        },
    )
    events.append(match_evt)

    # TRADE (materialized)
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {
                "event_id": match_evt["event_id"],
                "rel": "CREATED_FROM",
                "role": "PARENT",
            },
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: REMATCH
# SALES_BOOKING (force-matched) → UNMATCH → TRADING_BOOKING (corrected) → MATCH → TRADE
# =============================================================================


def _scenario_rematch(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Standalone unmatch/rematch — undo a previous force match with a corrected booking."""
    events: list[dict[str, Any]] = []
    pt = "IRS"
    fpml_id = "FPML-IRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book_s, book_t = random.choice(books), random.choice(books)
    sales, trader, desk = (
        random.choice(SALES_NAMES),
        random.choice(TRADER_NAMES),
        random.choice(DESKS),
    )
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    ops_user = random.choice(TRADER_NAMES)
    force_time = _random_datetime(-15, -10)
    unmatch_time = _random_datetime(-8, -5)
    rematch_time = _random_datetime(-3, 0)

    # SALES_BOOKING — previously force-matched, now being corrected
    sb = _make_event(
        "SALES_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "REMATCH",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "SALES",
            "breaks": [],
            "resolution": None,
            "matched_at": rematch_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": econ,
            "book_id": book_s["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "MATCHED",
                "at": force_time,
                "by": ops_user,
                "reason": "Force-matched by operations",
                "diff": {},
            },
            {
                "from_status": "MATCHED",
                "to_status": "UNMATCHED",
                "at": unmatch_time,
                "by": ops_user,
                "reason": "Unmatched — original trading booking had errors",
                "diff": {"match_status": {"old": "FORCED", "new": "UNMATCHED"}},
            },
            {
                "from_status": "UNMATCHED",
                "to_status": "MATCHED",
                "at": rematch_time,
                "by": "MATCHING_ENG",
                "reason": "Rematched with corrected trading booking",
                "diff": {"match_status": {"old": "UNMATCHED", "new": "MATCHED"}},
            },
        ],
    )
    events.append(sb)

    # UNMATCH — explicit unmatch event
    unmatch_evt = _make_event(
        "UNMATCH",
        status="ACTIVE",
        source="MANUAL",
        actor=ops_user,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=unmatch_time,
        links=[{"event_id": sb["event_id"], "rel": "UNMATCHES", "role": "PARENT"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        payload={
            "reason": "Original trading booking had rate error",
            "unmatched_by": ops_user,
            "original_match_type": "FORCE_MATCH",
            "original_force_time": force_time,
        },
    )
    events.append(unmatch_evt)

    # TRADING_BOOKING — corrected version
    corrected_rate = round(rate * 1.001, 6)  # slight correction
    corrected_econ = {**econ, "rate": corrected_rate}
    tb = _make_event(
        "TRADING_BOOKING",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        created_at=_random_datetime(-5, -3),
        links=[{"event_id": sb["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"}],
        correlation={
            "match_type": "CORRELATION",
            "scenario": "REMATCH",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
            "breaks": [],
            "resolution": None,
            "matched_at": rematch_time,
            "matched_by": "MATCHING_ENG",
        },
        payload={
            "trade_economics": corrected_econ,
            "book_id": book_t["book_id"],
            "portfolio": f"{pt}_{random.choice(REGIONS)}",
            "strategy": random.choice(STRATEGIES),
            "parties": parties,
            "legs": legs,
        },
    )
    events.append(tb)

    # MATCH — rematch event linking both
    match_evt = _make_event(
        "MATCH",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=rematch_time,
        links=[
            {"event_id": sb["event_id"], "rel": "MATCHES", "role": "LHS"},
            {"event_id": tb["event_id"], "rel": "MATCHES", "role": "RHS"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        payload={
            "match_type": "EXACT",
            "confidence": 1.0,
            "lhs_event_id": sb["event_id"],
            "rhs_event_id": tb["event_id"],
            "matched_fields": ["product_type", "notional", "ccy", "value_date"],
            "break_fields": [],
            "is_rematch": True,
            "previous_unmatch_id": unmatch_evt["event_id"],
        },
    )
    events.append(match_evt)

    # TRADE (materialized)
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": sb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": tb["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {
                "event_id": match_evt["event_id"],
                "rel": "CREATED_FROM",
                "role": "PARENT",
            },
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book_s["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20],
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: ALLOCATION
# TRADE (block) → ALLOC_SPLIT (2-4 child allocations)
# =============================================================================


def _scenario_allocation(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Block trade followed by allocation splits across accounts."""
    events: list[dict[str, Any]] = []
    pt = "TRS"
    fpml_id = "FPML-TRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    desk = random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    # TRADE (block)
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "is_block": True,
        },
        priority=random.choice(["NORMAL", "HIGH"]),
    )
    events.append(trade)

    # ALLOC_SPLITs via helper
    allocs = _add_alloc_splits(trade, entities, books)
    events.extend(allocs)
    return events


# =============================================================================
# SCENARIO: CANCEL
# TRADE (CONFIRMED) → CANCEL_REQUEST → CANCEL_CONFIRM
# =============================================================================


def _scenario_cancel(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Trade cancellation — confirmed trade voided via request/confirm flow."""
    events: list[dict[str, Any]] = []
    pt = "FX_SPOT"
    fpml_id = "FPML-FX-SPOT"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    trade_time = _random_datetime(-20, -10)
    cancel_req_time = _random_datetime(-8, -4)
    cancel_confirm_time = _random_datetime(-3, 0)

    # TRADE — original confirmed trade
    trade = _make_event(
        "TRADE",
        status="CANCELLED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=trade_time,
        correlation={
            "match_type": "CORRELATION",
            "match_status": "CANCELLED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": trade_time,
                "by": "MATCHING_ENG",
                "reason": "Trade materialized",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "CANCEL_PENDING",
                "at": cancel_req_time,
                "by": trader,
                "reason": "Cancel requested",
                "diff": {},
            },
            {
                "from_status": "CANCEL_PENDING",
                "to_status": "CANCELLED",
                "at": cancel_confirm_time,
                "by": "SYSTEM",
                "reason": "Cancel confirmed — trade voided",
                "diff": {},
            },
        ],
    )
    events.append(trade)

    # CANCEL_REQUEST
    requestor = random.choice(TRADER_NAMES)
    cancel_req = _make_event(
        "CANCEL_REQUEST",
        status="ACTIVE",
        source="MANUAL",
        actor=requestor,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=cancel_req_time,
        links=[{"event_id": trade["event_id"], "rel": "CANCELS", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "CANCELLED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "TRADING",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "reason": random.choice(
                [
                    "Duplicate trade",
                    "Client error",
                    "Wrong counterparty",
                    "Incorrect notional",
                    "Booking mistake",
                ]
            ),
            "requestor": requestor,
            "requested_at": cancel_req_time,
            "urgency": random.choice(["NORMAL", "HIGH", "URGENT"]),
        },
    )
    events.append(cancel_req)

    # CANCEL_CONFIRM — voids the trade
    cancel_confirm = _make_event(
        "CANCEL_CONFIRM",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="SYSTEM",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=cancel_confirm_time,
        links=[
            {"event_id": trade["event_id"], "rel": "CANCELS", "role": "CHILD"},
            {"event_id": cancel_req["event_id"], "rel": "CONFIRMS", "role": "CHILD"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "CANCELLED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "SYSTEM",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "cancel_request_id": cancel_req["event_id"],
            "confirmed_at": cancel_confirm_time,
            "confirmed_by": "SYSTEM",
            "settlement_impact": random.choice(
                ["NONE", "REVERSAL_PENDING", "SETTLED_REVERSAL"]
            ),
            "pnl_impact": round(random.uniform(-50000, 50000), 2),
        },
    )
    events.append(cancel_confirm)
    return events


# =============================================================================
# SCENARIO: NOVATION
# TRADE (A↔B) → NOVATION_REQUEST (A→C) → NOVATION_ACCEPT (B consents) → TRADE (C↔B)
# =============================================================================


def _scenario_novation(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Novation — original party transfers obligation to a new counterparty."""
    events: list[dict[str, Any]] = []
    pt = "XCCY_SWAP"
    fpml_id = "FPML-XCCY"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    # Three entities: A (transferor), B (remaining), C (transferee)
    pool = random.sample(entities[:10], k=min(3, len(entities[:10])))
    entity_a = pool[0]
    entity_b = pool[1] if len(pool) > 1 else entities[0]
    entity_c = pool[2] if len(pool) > 2 else entities[-1]
    book_orig, book_new = random.choice(books), random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties_orig = _make_parties(entity_a["entity_id"], entity_b["entity_id"])
    trade_time = _random_datetime(-30, -20)
    nov_req_time = _random_datetime(-15, -10)
    nov_accept_time = _random_datetime(-8, -5)
    new_trade_time = _random_datetime(-4, 0)

    # TRADE — original (A ↔ B)
    trade_orig = _make_event(
        "TRADE",
        status="NOVATED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=entity_a["entity_id"],
        created_at=trade_time,
        correlation={
            "match_type": "CORRELATION",
            "match_status": "NOVATED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties_orig,
            "ned": {
                "book_id": book_orig["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": trade_time,
                "by": "MATCHING_ENG",
                "reason": "Trade materialized",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "NOVATED",
                "at": new_trade_time,
                "by": "SYSTEM",
                "reason": "Novated — obligation transferred",
                "diff": {},
            },
        ],
    )
    events.append(trade_orig)

    # NOVATION_REQUEST — A wants to transfer to C
    nov_req = _make_event(
        "NOVATION_REQUEST",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=entity_a["entity_id"],
        created_at=nov_req_time,
        links=[{"event_id": trade_orig["event_id"], "rel": "NOVATES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "TRADING",
        },
        payload={
            "original_trade_id": trade_orig["event_id"],
            "transferor_id": entity_a["entity_id"],
            "transferee_id": entity_c["entity_id"],
            "remaining_party_id": entity_b["entity_id"],
            "novation_date": _random_date(-5, 5),
            "novation_type": random.choice(["FULL", "PARTIAL"]),
            "novation_amount": notional,
            "reason": random.choice(
                [
                    "Portfolio transfer",
                    "Credit limit optimization",
                    "Regulatory capital relief",
                    "Client restructuring",
                ]
            ),
            "fees": round(random.uniform(0, notional * 0.001), 2),
        },
    )
    events.append(nov_req)

    # NOVATION_ACCEPT — B (remaining party) consents
    nov_accept = _make_event(
        "NOVATION_ACCEPT",
        status="ACTIVE",
        source="CLIENT",
        actor=entity_b.get("short_name", "CPTY"),
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=entity_b["entity_id"],
        created_at=nov_accept_time,
        links=[
            {"event_id": trade_orig["event_id"], "rel": "NOVATES", "role": "CHILD"},
            {"event_id": nov_req["event_id"], "rel": "CONFIRMS", "role": "CHILD"},
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "OPS",
        },
        payload={
            "novation_request_id": nov_req["event_id"],
            "consenting_party_id": entity_b["entity_id"],
            "consent_date": _random_date(-5, 0),
            "conditions": random.choice(
                [None, "Subject to CSA renegotiation", "Effective next business day"]
            ),
        },
    )
    events.append(nov_accept)

    # TRADE — new (C ↔ B)
    parties_new = _make_parties(entity_c["entity_id"], entity_b["entity_id"])
    trade_new = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=entity_c["entity_id"],
        created_at=new_trade_time,
        links=[
            {
                "event_id": trade_orig["event_id"],
                "rel": "NOVATED_FROM",
                "role": "CHILD",
            },
            {"event_id": nov_req["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {
                "event_id": nov_accept["event_id"],
                "rel": "CREATED_FROM",
                "role": "PARENT",
            },
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": _random_date(-5, 0),
            "parties": parties_new,
            "ned": {
                "book_id": book_new["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "is_novation": True,
            "original_trade_id": trade_orig["event_id"],
        },
    )
    events.append(trade_new)
    return events


# =============================================================================
# SCENARIO: ROLL
# TRADE (near leg, MATURED) → TRADE (far leg, CONFIRMED) linked with ROLLS_INTO
# =============================================================================


def _scenario_roll(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """FX forward roll — near leg matures, far leg opens with roll cost."""
    events: list[dict[str, Any]] = []
    pt = "FX_FORWARD"
    fpml_id = "FPML-FX-FWD"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    near_time = _random_datetime(-30, -15)
    far_time = _random_datetime(-5, 0)

    # Forward points for near and far
    near_fwd_points = round(random.uniform(-200, 200), 2)
    far_fwd_points = round(random.uniform(-200, 200), 2)
    roll_cost = round((far_fwd_points - near_fwd_points) / 10_000 * notional, 2)
    near_rate = round(rate + near_fwd_points / 10_000, 6)
    far_rate = round(rate + far_fwd_points / 10_000, 6)

    near_econ = _make_trade_economics(pt, ccy, notional, near_rate, ccy_pair)
    near_legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, near_rate)
    far_econ = _make_trade_economics(pt, ccy, notional, far_rate, ccy_pair)
    far_legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, far_rate)

    # TRADE — near leg (closing, matured)
    trade_near = _make_event(
        "TRADE",
        status="MATURED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=near_time,
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATURED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": near_econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": near_legs,
            "uti": _uti(),
            "usi": None,
            "leg_type": "NEAR",
            "forward_points": near_fwd_points,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": near_time,
                "by": "MATCHING_ENG",
                "reason": "Trade materialized",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "MATURED",
                "at": far_time,
                "by": "SYSTEM",
                "reason": "Near leg matured — rolled into far leg",
                "diff": {},
            },
        ],
    )
    events.append(trade_near)

    # TRADE — far leg (opening, confirmed)
    trade_far = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=far_time,
        links=[
            {"event_id": trade_near["event_id"], "rel": "ROLLS_INTO", "role": "CHILD"}
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": far_econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": far_legs,
            "uti": _uti(),
            "usi": None,
            "leg_type": "FAR",
            "forward_points": far_fwd_points,
            "roll_cost": roll_cost,
            "roll_from_trade_id": trade_near["event_id"],
        },
    )
    events.append(trade_far)
    return events


# =============================================================================
# SCENARIO: EXERCISE
# TRADE (swaption, CONFIRMED) → EXERCISE_NOTICE → TRADE (underlying IRS, CONFIRMED)
# =============================================================================


def _scenario_exercise(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Swaption exercise — option exercised, underlying IRS materializes (PHYSICAL) or cash settles."""
    events: list[dict[str, Any]] = []
    pt_option = "SWAPTION"
    fpml_option = "FPML-SWAPTION"
    fpml_underlying = "FPML-IRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt_option)
    notional = _notional_for(pt_option)
    rate = _rate_for(pt_option)
    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])
    option_time = _random_datetime(-60, -30)
    exercise_time = _random_datetime(-10, -5)
    underlying_time = _random_datetime(-4, 0)
    settlement_type = random.choice(["PHYSICAL", "CASH"])
    option_type = random.choice(["PAYER", "RECEIVER"])

    option_econ = _make_trade_economics(pt_option, ccy, notional, rate, ccy_pair)
    option_legs = _make_legs_for(pt_option, fpml_option, ccy, far_ccy, notional, rate)

    # TRADE — swaption (exercised)
    trade_option = _make_event(
        "TRADE",
        status="EXERCISED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt_option,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=option_time,
        correlation={
            "match_type": "CORRELATION",
            "match_status": "EXERCISED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_option,
            "trade_date": option_econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt_option}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
            },
            "legs": option_legs,
            "uti": _uti(),
            "usi": None,
            "option_type": option_type,
            "settlement_type": settlement_type,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "CONFIRMED",
                "at": option_time,
                "by": "MATCHING_ENG",
                "reason": "Swaption trade confirmed",
                "diff": {},
            },
            {
                "from_status": "CONFIRMED",
                "to_status": "EXERCISED",
                "at": exercise_time,
                "by": trader,
                "reason": f"Option exercised — {settlement_type} settlement",
                "diff": {},
            },
        ],
    )
    events.append(trade_option)

    # EXERCISE_NOTICE
    cash_amount = (
        round(notional * random.uniform(0.001, 0.015), 2)
        if settlement_type == "CASH"
        else None
    )
    exercise_notice = _make_event(
        "EXERCISE_NOTICE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt_option,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        created_at=exercise_time,
        links=[
            {"event_id": trade_option["event_id"], "rel": "EXERCISES", "role": "CHILD"}
        ],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "TRADING",
        },
        payload={
            "option_trade_id": trade_option["event_id"],
            "exercise_date": _random_date(-10, -5),
            "exercise_decision": settlement_type,
            "option_type": option_type,
            "strike_rate": rate,
            "settlement_type": settlement_type,
            "cash_settlement_amount": cash_amount,
            "cash_settlement_ccy": ccy if settlement_type == "CASH" else None,
            "exercised_by": trader,
            "notification_time": exercise_time,
        },
    )
    events.append(exercise_notice)

    # TRADE — underlying IRS (only for PHYSICAL settlement)
    if settlement_type == "PHYSICAL":
        pt_underlying = "IRS"
        underlying_rate = rate  # strike becomes the fixed rate
        underlying_legs = _make_legs_for(
            pt_underlying, fpml_underlying, ccy, ccy, notional, underlying_rate
        )

        trade_underlying = _make_event(
            "TRADE",
            status="CONFIRMED",
            source="MATCHING_ENG",
            actor="MATCHING_ENG",
            desk=desk,
            product_type=pt_underlying,
            notional=notional,
            ccy=ccy,
            cpty_id=buyer["entity_id"],
            created_at=underlying_time,
            links=[
                {
                    "event_id": trade_option["event_id"],
                    "rel": "CREATED_FROM",
                    "role": "PARENT",
                },
                {
                    "event_id": exercise_notice["event_id"],
                    "rel": "CREATED_FROM",
                    "role": "PARENT",
                },
            ],
            correlation={
                "match_type": "CORRELATION",
                "match_status": "MATCHED",
                "cardinality": "ONE_TO_ONE",
                "direction": "PARENT",
                "actor_role": "SYSTEM",
            },
            enriched=_make_enriched(),
            payload={
                "trade_id": _gen_id("event"),
                "fpml_type": fpml_underlying,
                "trade_date": _random_date(-5, 0),
                "parties": parties,
                "ned": {
                    "book_id": book["book_id"],
                    "portfolio": f"{pt_underlying}_{random.choice(REGIONS)}",
                    "strategy": random.choice(STRATEGIES),
                    "clearing": random.choice(CCPS) if random.random() > 0.5 else None,
                },
                "legs": underlying_legs,
                "uti": _uti(),
                "usi": _uti()[:20],
                "is_exercise_result": True,
                "option_trade_id": trade_option["event_id"],
                "exercise_notice_id": exercise_notice["event_id"],
            },
        )
        events.append(trade_underlying)

    return events


# =============================================================================
# SCENARIO: MARKET ABUSE — SPOOFING
# Trader places large BUY orders to inflate price → sells at the top →
# cancels BUY orders → order vs trade recon catches the pattern
# =============================================================================


def _scenario_market_abuse_spoofing(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Market abuse (spoofing): large buy orders inflate price, sell executes, buys cancelled."""
    events: list[dict[str, Any]] = []
    pt = "BOND"
    fpml_id = "FPML-BOND"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt) * 3  # Unusually large — part of the manipulation
    rate = _rate_for(pt)
    inflated_rate = round(rate * 1.025, 6)  # 2.5% above market — the spoofed price

    # Entities: spoofer is a trader, cpty is the counterparty who gets tricked
    spoofer_entity = random.choice(entities[:10])
    cpty = random.choice(
        [e for e in entities[:10] if e["entity_id"] != spoofer_entity["entity_id"]]
    )
    brokers = [e for e in entities if e["entity_type"] == "BROKER"]
    broker = random.choice(brokers) if brokers else random.choice(entities[:5])
    book = random.choice(books)
    spoofer_name = random.choice(TRADER_NAMES)
    desk = random.choice(DESKS)
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, notional, rate)
    parties = _make_parties(spoofer_entity["entity_id"], cpty["entity_id"])

    # Timeline: orders placed → sell executed → orders cancelled → flagged
    order_time_1 = _random_datetime(-50, -40)
    order_time_2 = _random_datetime(-38, -30)
    sell_order_time = _random_datetime(-28, -22)
    fill_time = _random_datetime(-20, -15)
    trade_time = _random_datetime(-14, -10)
    cancel_req_time_1 = _random_datetime(-9, -7)
    cancel_conf_time_1 = _random_datetime(-6, -5)
    cancel_req_time_2 = _random_datetime(-4, -3)
    cancel_conf_time_2 = _random_datetime(-2, -1)

    # ── Phase 1: Spoof BUY orders (never intended to execute) ──

    buy_order_1 = _make_event(
        "ORDER",
        status="CANCELLED",
        source="MANUAL",
        actor=spoofer_name,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=order_time_1,
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
            "breaks": [
                {
                    "field": "order_execution",
                    "lhs": f"{notional:,.0f} {ccy} buy order",
                    "rhs": "CANCELLED — never executed",
                    "status": "break",
                    "severity": "CRITICAL",
                },
            ],
        },
        payload={
            "order_type": "LIMIT",
            "direction": "PAY",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": inflated_rate,
            "broker_entity_id": broker["entity_id"],
            "expected_fills": 0,
            "filled_qty": 0.0,
            "remaining_qty": notional,
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "ACTIVE",
                "at": order_time_1,
                "by": spoofer_name,
                "reason": "Buy order placed",
                "diff": {},
            },
            {
                "from_status": "ACTIVE",
                "to_status": "CANCELLED",
                "at": cancel_conf_time_1,
                "by": spoofer_name,
                "reason": "Order cancelled post sell-execution — spoofing indicator",
                "diff": {},
            },
        ],
    )
    events.append(buy_order_1)

    buy_order_2 = _make_event(
        "ORDER",
        status="CANCELLED",
        source="MANUAL",
        actor=spoofer_name,
        desk=desk,
        product_type=pt,
        notional=round(notional * 0.8, 2),
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=order_time_2,
        links=[
            {"event_id": buy_order_1["event_id"], "rel": "CORRELATES_WITH", "role": "LHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
            "breaks": [
                {
                    "field": "order_execution",
                    "lhs": f"{notional * 0.8:,.0f} {ccy} buy order",
                    "rhs": "CANCELLED — never executed",
                    "status": "break",
                    "severity": "CRITICAL",
                },
            ],
        },
        payload={
            "order_type": "LIMIT",
            "direction": "PAY",
            "product_type": pt,
            "notional": round(notional * 0.8, 2),
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": round(inflated_rate * 1.005, 6),
            "broker_entity_id": broker["entity_id"],
            "expected_fills": 0,
            "filled_qty": 0.0,
            "remaining_qty": round(notional * 0.8, 2),
        },
        transitions=[
            {
                "from_status": "PENDING",
                "to_status": "ACTIVE",
                "at": order_time_2,
                "by": spoofer_name,
                "reason": "Second buy order placed — reinforcing bid side",
                "diff": {},
            },
            {
                "from_status": "ACTIVE",
                "to_status": "CANCELLED",
                "at": cancel_conf_time_2,
                "by": spoofer_name,
                "reason": "Order cancelled post sell-execution — spoofing indicator",
                "diff": {},
            },
        ],
    )
    events.append(buy_order_2)

    # ── Phase 2: SELL order placed after market moved up ──

    sell_notional = round(notional * 0.5, 2)
    sell_order = _make_event(
        "ORDER",
        status="ACTIVE",
        source="MANUAL",
        actor=spoofer_name,
        desk=desk,
        product_type=pt,
        notional=sell_notional,
        ccy=ccy,
        cpty_id=cpty["entity_id"],
        created_at=sell_order_time,
        links=[
            {"event_id": buy_order_1["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
            {"event_id": buy_order_2["event_id"], "rel": "CORRELATES_WITH", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "order_type": "LIMIT",
            "direction": "RECEIVE",
            "product_type": pt,
            "notional": sell_notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "limit_price": inflated_rate,
            "broker_entity_id": broker["entity_id"],
            "expected_fills": 1,
            "filled_qty": sell_notional,
            "remaining_qty": 0.0,
        },
    )
    events.append(sell_order)

    # ── Phase 2b: BROKER_FILL on the sell ──

    fill = _make_event(
        "BROKER_FILL",
        status="ACTIVE",
        source="BROKER",
        actor=broker["short_name"],
        desk=desk,
        product_type=pt,
        notional=sell_notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=fill_time,
        links=[
            {"event_id": sell_order["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "MATCHED",
            "cardinality": "MANY_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        raw=_make_raw_wire("BROKER", "FIX", pt),
        payload={
            "broker_entity_id": broker["entity_id"],
            "exec_id": _gen_id("event"),
            "price": inflated_rate,
            "qty": sell_notional,
            "venue": "D2C",
            "commission": round(sell_notional * 0.0005, 2),
            "commission_bps": 5.0,
            "product_type": pt,
            "ccy": ccy,
            "exec_type": "FILL",
            "fill_number": 1,
            "total_fills": 1,
            "cumulative_qty": sell_notional,
        },
    )
    events.append(fill)

    # ── Phase 2c: TRADE materialized from sell execution ──

    sell_legs = _make_legs_for(pt, fpml_id, ccy, far_ccy, sell_notional, inflated_rate)
    trade = _make_event(
        "TRADE",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=sell_notional,
        ccy=ccy,
        cpty_id=cpty["entity_id"],
        created_at=trade_time,
        links=[
            {"event_id": sell_order["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": fill["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
        },
        enriched={
            **_make_enriched(),
            "risk_flags": ["WASH_TRADE", "OFF_MARKET_PRICE", "LARGE_NOTIONAL"],
            "compliance": {
                "approved_by": None,
                "limit_check": "BREACH",
                "wash_trade_flag": True,
                "best_execution": "FAIL",
                "spoofing_score": 0.94,
                "alert_id": f"SURV-{uuid.uuid4().hex[:8].upper()}",
            },
        },
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_id,
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": random.choice(STRATEGIES),
                "clearing": None,
            },
            "legs": sell_legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)

    # ── Phase 3: Cancel the spoof BUY orders ──

    cancel_req_1 = _make_event(
        "CANCEL_REQUEST",
        status="ACTIVE",
        source="MANUAL",
        actor=spoofer_name,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=cancel_req_time_1,
        links=[{"event_id": buy_order_1["event_id"], "rel": "CANCELS", "role": "CHILD"}],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "TRADING",
        },
        payload={
            "trade_event_id": buy_order_1["event_id"],
            "reason": "No longer required",
            "requestor": spoofer_name,
            "requested_at": cancel_req_time_1,
            "urgency": "HIGH",
        },
    )
    events.append(cancel_req_1)

    cancel_conf_1 = _make_event(
        "CANCEL_CONFIRM",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="SYSTEM",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=cancel_conf_time_1,
        links=[
            {"event_id": buy_order_1["event_id"], "rel": "CANCELS", "role": "CHILD"},
            {"event_id": cancel_req_1["event_id"], "rel": "CONFIRMS", "role": "CHILD"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "SYSTEM",
        },
        payload={
            "trade_event_id": buy_order_1["event_id"],
            "cancel_request_id": cancel_req_1["event_id"],
            "confirmed_at": cancel_conf_time_1,
            "confirmed_by": "SYSTEM",
            "settlement_impact": "NONE",
            "pnl_impact": 0.0,
        },
    )
    events.append(cancel_conf_1)

    cancel_req_2 = _make_event(
        "CANCEL_REQUEST",
        status="ACTIVE",
        source="MANUAL",
        actor=spoofer_name,
        desk=desk,
        product_type=pt,
        notional=round(notional * 0.8, 2),
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=cancel_req_time_2,
        links=[{"event_id": buy_order_2["event_id"], "rel": "CANCELS", "role": "CHILD"}],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "TRADING",
        },
        payload={
            "trade_event_id": buy_order_2["event_id"],
            "reason": "No longer required",
            "requestor": spoofer_name,
            "requested_at": cancel_req_time_2,
            "urgency": "HIGH",
        },
    )
    events.append(cancel_req_2)

    cancel_conf_2 = _make_event(
        "CANCEL_CONFIRM",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="SYSTEM",
        desk=desk,
        product_type=pt,
        notional=round(notional * 0.8, 2),
        ccy=ccy,
        cpty_id=broker["entity_id"],
        created_at=cancel_conf_time_2,
        links=[
            {"event_id": buy_order_2["event_id"], "rel": "CANCELS", "role": "CHILD"},
            {"event_id": cancel_req_2["event_id"], "rel": "CONFIRMS", "role": "CHILD"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "SYSTEM",
        },
        payload={
            "trade_event_id": buy_order_2["event_id"],
            "cancel_request_id": cancel_req_2["event_id"],
            "confirmed_at": cancel_conf_time_2,
            "confirmed_by": "SYSTEM",
            "settlement_impact": "NONE",
            "pnl_impact": 0.0,
        },
    )
    events.append(cancel_conf_2)

    # ── Phase 4: Recon break — the smoking gun ──
    # The reconciliation event surfaces the abuse pattern:
    # 2 large buy orders cancelled (never filled) + 1 sell trade executed at inflated price

    recon_event = _make_event(
        "RISK_MEASURE",
        status="ACTIVE",
        source="MATCHING_ENG",
        actor="SURVEILLANCE-SVC",
        desk=desk,
        product_type=pt,
        notional=sell_notional,
        ccy=ccy,
        cpty_id=spoofer_entity["entity_id"],
        created_at=_random_datetime(0, 0),
        links=[
            {"event_id": trade["event_id"], "rel": "MEASURES", "role": "CHILD"},
            {"event_id": buy_order_1["event_id"], "rel": "MEASURES", "role": "CHILD"},
            {"event_id": buy_order_2["event_id"], "rel": "MEASURES", "role": "CHILD"},
        ],
        correlation={
            "match_type": "RECONCILIATION",
            "match_status": "PARTIAL",
            "cardinality": "MANY_TO_ONE",
            "direction": "RHS",
            "actor_role": "SYSTEM",
            "breaks": [
                {
                    "field": "order_vs_trade_recon",
                    "lhs": f"2 buy orders totalling {notional + notional * 0.8:,.0f} {ccy} — ALL CANCELLED",
                    "rhs": f"1 sell trade executed at {inflated_rate} for {sell_notional:,.0f} {ccy}",
                    "status": "break",
                    "severity": "CRITICAL",
                },
                {
                    "field": "spoofing_pattern",
                    "lhs": "Orders placed to inflate bid → market moved up 2.5%",
                    "rhs": "Sell executed at inflated price → orders cancelled",
                    "status": "break",
                    "severity": "CRITICAL",
                },
                {
                    "field": "cancellation_timing",
                    "lhs": "Buy orders cancelled within minutes of sell execution",
                    "rhs": "Pattern consistent with layering/spoofing",
                    "status": "break",
                    "severity": "CRITICAL",
                },
            ],
            "resolution": None,
            "matched_at": None,
            "matched_by": "SURVEILLANCE-SVC",
        },
        payload={
            "metric": "SPOOFING_SCORE",
            "value": 0.94,
            "currency": ccy,
            "as_of_date": _random_date(0, 0),
            "source_model": "SURVEILLANCE-SVC",
            "confidence": 0.94,
            "alert_type": "MARKET_ABUSE_SPOOFING",
            "trader": spoofer_name,
            "desk": desk,
            "buy_orders_total": round(notional + notional * 0.8, 2),
            "buy_orders_filled": 0.0,
            "sell_trade_notional": sell_notional,
            "sell_trade_price": inflated_rate,
            "market_price_before": rate,
            "market_price_during": inflated_rate,
            "price_impact_pct": 2.5,
        },
    )
    events.append(recon_event)

    return events


# =============================================================================
# SCENARIO: AXE_TO_RFQ
# AXE → RFQ → QUOTE → RFQ(accept) → TRADE
# Dealer publishes an axe/IOI, client sees it, sends RFQ, negotiation follows.
# =============================================================================

_AXE_VENUES = ["TRADEWEB", "MARKETAXESS", "BLOOMBERG_RFQ"]
_AXE_BOND_TICKERS = [
    "AAPL 4.5 03/28", "T 3.875 01/30", "GS 5.15 06/35", "MSFT 3.45 08/29",
    "JPM 4.85 12/31", "C 5.25 09/33", "BAC 4.75 07/32", "WFC 4.10 02/27",
    "AMZN 3.95 05/30", "META 4.20 11/28", "BRK 3.60 04/34", "V 4.00 06/29",
]
_AXE_VISIBILITIES = ["PUBLIC", "TARGETED", "DARK"]


def _scenario_axe_to_rfq(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Dealer publishes AXE → client RFQ → QUOTE → accept → TRADE."""
    events: list[dict[str, Any]] = []
    pt = "BOND"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    ticker = random.choice(_AXE_BOND_TICKERS)
    venue = random.choice(_AXE_VENUES)
    direction = random.choice(DIRECTIONS)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    sales = random.choice(SALES_NAMES)

    indicative_price = round(random.uniform(95.0, 105.0), 4)
    indicative_spread = round(random.uniform(50, 250), 1)
    benchmark = random.choice(["UST 5Y", "UST 10Y", "UST 30Y", "GILT 10Y"])

    # ── AXE (dealer publishes) ──
    axe = _make_event(
        "AXE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": direction,
            "product_type": pt,
            "ticker": ticker,
            "notional": notional,
            "ccy": ccy,
            "indicative_price": indicative_price,
            "indicative_spread": indicative_spread,
            "benchmark": benchmark,
            "axe_type": "NATURAL",
            "axe_status": "LIVE",
            "visibility": random.choice(_AXE_VISIBILITIES),
            "venue": venue,
        },
    )
    events.append(axe)

    # ── RFQ (client sees axe, sends request) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=venue,
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": axe["event_id"], "rel": "TRIGGERED_BY", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": "PAY" if direction == "RECEIVE" else "RECEIVE",
            "product_type": pt,
            "ticker": ticker,
            "notional": notional,
            "ccy": ccy,
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 1,
            "negotiation_status": "OPEN",
            "venue": venue,
        },
    )
    events.append(rfq)

    # ── QUOTE (dealer responds) ──
    quoted_price = round(indicative_price + random.uniform(-0.5, 0.5), 4)
    quoted_spread = round(indicative_spread + random.uniform(-10, 10), 1)
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": quoted_price,
            "spread": quoted_spread,
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── RFQ v2 (client accepts) ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source=venue,
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": "PAY" if direction == "RECEIVE" else "RECEIVE",
            "product_type": pt,
            "ticker": ticker,
            "notional": notional,
            "ccy": ccy,
            "limit_price": quoted_price,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": quote["event_id"],
            "venue": venue,
        },
    )
    events.append(rfq_accept)

    # ── TRADE (materialized) ──
    fpml_bond = next((f for f in fpmls if f["product_type"] == "BOND"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_bond["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_bond["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"BOND_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: AXE_WITHDRAW
# AXE(LIVE) → AXE(WITHDRAWN)
# =============================================================================


def _scenario_axe_withdraw(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Dealer publishes axe then withdraws it — no trade materializes."""
    events: list[dict[str, Any]] = []
    pt = "BOND"
    ccy, _far_ccy, _ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    ticker = random.choice(_AXE_BOND_TICKERS)
    venue = random.choice(_AXE_VENUES)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    indicative_price = round(random.uniform(95.0, 105.0), 4)
    indicative_spread = round(random.uniform(50, 250), 1)

    # ── AXE v1 (LIVE) ──
    axe_v1 = _make_event(
        "AXE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "ticker": ticker,
            "notional": notional,
            "ccy": ccy,
            "indicative_price": indicative_price,
            "indicative_spread": indicative_spread,
            "benchmark": random.choice(["UST 5Y", "UST 10Y"]),
            "axe_type": "NATURAL",
            "axe_status": "LIVE",
            "visibility": random.choice(_AXE_VISIBILITIES),
            "venue": venue,
            "revision": 1,
        },
    )
    events.append(axe_v1)

    # ── AXE v2 (WITHDRAWN) ──
    axe_v2 = _make_event(
        "AXE",
        status="CANCELLED",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": axe_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": axe_v1["payload"]["direction"],
            "product_type": pt,
            "ticker": ticker,
            "notional": notional,
            "ccy": ccy,
            "indicative_price": indicative_price,
            "indicative_spread": indicative_spread,
            "axe_type": "NATURAL",
            "axe_status": "WITHDRAWN",
            "withdraw_reason": random.choice([
                "Market moved", "Position filled", "Risk limit reached",
                "Client request", "End of day",
            ]),
            "venue": venue,
            "revision": 2,
        },
    )
    events.append(axe_v2)
    return events


# =============================================================================
# SCENARIO: OUTBOUND_RFQ_HIT
# RFQ(OUTBOUND) → QUOTE(from venue) → RFQ(ACCEPTED) → TRADE
# =============================================================================


def _scenario_outbound_rfq_hit(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Our desk sends outbound RFQ to venue, gets quote, accepts → TRADE."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    venue = random.choice(["TRADEWEB", "MARKETAXESS"])

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ (outbound — our desk initiates) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=venue,
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "PAY",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "rfq_direction": "OUTBOUND",
            "venue": venue,
            "initiator_desk": desk,
            "limit_price": None,
            "valid_until": None,
            "num_dealers": random.randint(3, 8),
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE (venue responds) ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source=venue,
        actor=venue,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": rate,
            "spread": round(random.uniform(0.5, 10.0), 2),
            "valid_until": None,
            "quoted_by": venue,
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── RFQ v2 (we accept) ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source=venue,
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "PAY",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "rfq_direction": "OUTBOUND",
            "venue": venue,
            "initiator_desk": desk,
            "limit_price": rate,
            "valid_until": None,
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": quote["event_id"],
        },
    )
    events.append(rfq_accept)

    # ── TRADE ──
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: OUTBOUND_RFQ_MISS
# RFQ(OUTBOUND) → QUOTE → RFQ(TRADED_AWAY)
# =============================================================================


def _scenario_outbound_rfq_miss(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Our desk sends outbound RFQ, gets quote, but we reject (traded away)."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, _far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    venue = random.choice(["TRADEWEB", "MARKETAXESS"])

    seller = random.choice(entities[:10])
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ (outbound) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=venue,
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "PAY",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "rfq_direction": "OUTBOUND",
            "venue": venue,
            "initiator_desk": desk,
            "limit_price": None,
            "valid_until": None,
            "num_dealers": random.randint(3, 8),
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE (venue responds) ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source=venue,
        actor=venue,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": rate,
            "spread": round(random.uniform(0.5, 10.0), 2),
            "valid_until": None,
            "quoted_by": venue,
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── RFQ v2 (TRADED_AWAY — we reject) ──
    rfq_reject = _make_event(
        "RFQ",
        status="CANCELLED",
        source=venue,
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "PAY",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "rfq_direction": "OUTBOUND",
            "venue": venue,
            "initiator_desk": desk,
            "revision": 2,
            "negotiation_status": "TRADED_AWAY",
            "reject_reason": random.choice([
                "Price not competitive", "Spread too wide",
                "Executed elsewhere", "Market moved",
            ]),
        },
    )
    events.append(rfq_reject)
    return events


# =============================================================================
# SCENARIO: STREAMING_QUOTE
# QUOTE(stream v1) → QUOTE(v2) → QUOTE(v3 expired)
# =============================================================================


def _scenario_streaming_quote(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Three streaming QUOTE updates — v1→v2(price tick)→v3(expired)."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, _far_ccy, _ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    stream_id = f"STRM-{uuid.uuid4().hex[:12].upper()}"

    mid_price = round(random.uniform(0.5, 5.0), 6)
    half_spread = round(random.uniform(0.0005, 0.01), 6)
    bid_size = round(random.uniform(1_000_000, 50_000_000), 2)
    ask_size = round(random.uniform(1_000_000, 50_000_000), 2)

    # ── v1: INDICATIVE ──
    q_v1 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "STREAMING",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "quote_mode": "TWO_WAY",
            "stream_id": stream_id,
            "bid_price": round(mid_price - half_spread, 6),
            "ask_price": round(mid_price + half_spread, 6),
            "mid_price": mid_price,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(q_v1)

    # ── v2: INDICATIVE (price ticked) ──
    tick = round(random.uniform(-0.003, 0.003), 6)
    mid_v2 = round(mid_price + tick, 6)
    q_v2 = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": q_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "STREAMING",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "quote_mode": "TWO_WAY",
            "stream_id": stream_id,
            "bid_price": round(mid_v2 - half_spread, 6),
            "ask_price": round(mid_v2 + half_spread, 6),
            "mid_price": mid_v2,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "status": "INDICATIVE",
            "revision": 2,
        },
    )
    events.append(q_v2)

    # ── v3: EXPIRED ──
    q_v3 = _make_event(
        "QUOTE",
        status="CANCELLED",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": q_v2["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_MANY",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "quote_mode": "TWO_WAY",
            "stream_id": stream_id,
            "bid_price": q_v2["payload"]["bid_price"],
            "ask_price": q_v2["payload"]["ask_price"],
            "mid_price": mid_v2,
            "bid_size": 0,
            "ask_size": 0,
            "status": "EXPIRED",
            "revision": 3,
        },
    )
    events.append(q_v3)
    return events


# =============================================================================
# SCENARIO: STREAM_TO_TRADE
# QUOTE(stream, INDICATIVE) → RFQ(client hits) → TRADE
# =============================================================================


def _scenario_stream_to_trade(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Client hits a streaming indicative quote — immediate trade."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    stream_id = f"STRM-{uuid.uuid4().hex[:12].upper()}"

    mid_price = rate
    half_spread = round(random.uniform(0.0005, 0.01), 6)
    bid_price = round(mid_price - half_spread, 6)
    ask_price = round(mid_price + half_spread, 6)
    hit_side = random.choice(["BID", "ASK"])
    hit_price = bid_price if hit_side == "BID" else ask_price

    # ── QUOTE (streaming indicative) ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "STREAMING",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "quote_mode": "TWO_WAY",
            "stream_id": stream_id,
            "bid_price": bid_price,
            "ask_price": ask_price,
            "mid_price": mid_price,
            "bid_size": notional,
            "ask_size": notional,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── RFQ (client hits the stream) ──
    rfq = _make_event(
        "RFQ",
        status="ACCEPTED",
        source="CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": quote["event_id"], "rel": "TRIGGERED_BY", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": "PAY" if hit_side == "ASK" else "RECEIVE",
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "hit_side": hit_side,
            "hit_price": hit_price,
            "stream_id": stream_id,
            "client_entity_id": buyer["entity_id"],
            "revision": 1,
            "negotiation_status": "ACCEPTED",
        },
    )
    events.append(rfq)

    # ── TRADE (instant materialization) ──
    econ = _make_trade_economics(pt, ccy, notional, hit_price, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, hit_price)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: STREAM_TO_RFQ
# QUOTE(stream) → RFQ(client requests firm) → QUOTE(FIRM) → RFQ(ACCEPTED) → TRADE
# =============================================================================


def _scenario_stream_to_rfq(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Client sees indicative stream, requests firm price — full negotiation."""
    events: list[dict[str, Any]] = []
    fpml = random.choice(fpmls)
    pt = fpml["product_type"]
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    stream_id = f"STRM-{uuid.uuid4().hex[:12].upper()}"

    mid_price = rate
    half_spread = round(random.uniform(0.0005, 0.01), 6)

    # ── QUOTE v1 (streaming indicative) ──
    q_stream = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "STREAMING",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "quote_mode": "TWO_WAY",
            "stream_id": stream_id,
            "bid_price": round(mid_price - half_spread, 6),
            "ask_price": round(mid_price + half_spread, 6),
            "mid_price": mid_price,
            "bid_size": notional,
            "ask_size": notional,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(q_stream)

    # ── RFQ (client requests firm price) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": q_stream["event_id"], "rel": "TRIGGERED_BY", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "stream_id": stream_id,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": 1,
            "revision": 1,
            "negotiation_status": "OPEN",
            "request_type": "FIRM_FROM_STREAM",
        },
    )
    events.append(rfq)

    # ── QUOTE v2 (FIRM — trader firms up the price) ──
    firm_price = round(mid_price + random.uniform(-0.002, 0.002), 6)
    q_firm = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
            {"event_id": q_stream["event_id"], "rel": "SUPERSEDES", "role": "LHS"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": firm_price,
            "spread": round(random.uniform(0.5, 10.0), 2),
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 2,
            "stream_id": stream_id,
        },
    )
    events.append(q_firm)

    # ── RFQ v2 (client accepts) ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source="CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": rfq["payload"]["direction"],
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "client_entity_id": buyer["entity_id"],
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": q_firm["event_id"],
        },
    )
    events.append(rfq_accept)

    # ── TRADE ──
    econ = _make_trade_economics(pt, ccy, notional, firm_price, ccy_pair)
    legs = _make_legs_for(pt, fpml["fpml_id"], ccy, far_ccy, notional, firm_price)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": q_firm["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: SPREAD_RFQ
# RFQ(IRS, benchmark+spread) → QUOTE(all_in_rate) → RFQ(accept) → TRADE
# =============================================================================

_SPREAD_BENCHMARKS = {
    "USD": ["USD_MID_SWAP_2Y", "USD_MID_SWAP_5Y", "USD_MID_SWAP_10Y", "USD_MID_SWAP_30Y"],
    "EUR": ["EUR_MID_SWAP_5Y", "EUR_MID_SWAP_10Y", "EUR_MID_SWAP_30Y"],
    "GBP": ["GBP_MID_SWAP_5Y", "GBP_MID_SWAP_10Y"],
}


def _scenario_spread_rfq(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """IRS/XCCY RFQ quoted as spread over benchmark — all_in_rate = benchmark + spread."""
    events: list[dict[str, Any]] = []
    pt = random.choice(["IRS", "XCCY_SWAP"])
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    tenor = random.choice(IRS_TENORS)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    sales = random.choice(SALES_NAMES)

    bm_list = _SPREAD_BENCHMARKS.get(ccy, _SPREAD_BENCHMARKS["USD"])
    benchmark = random.choice(bm_list)
    spread_bps = round(random.uniform(-15, 120), 1)
    benchmark_rate = round(random.uniform(2.5, 5.5), 4)
    all_in_rate = round(benchmark_rate + spread_bps / 100, 4)

    # ── RFQ (with benchmark + spread) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=random.choice(["TRADEWEB", "BLOOMBERG"]),
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "ccy_pair": ccy_pair,
            "tenor": tenor,
            "benchmark": benchmark,
            "spread_bps": spread_bps,
            "fixing_status": "FIXED",
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 6),
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE (with benchmark_rate + all_in_rate) ──
    bid_spread = round(spread_bps - random.uniform(1, 5), 1)
    ask_spread = round(spread_bps + random.uniform(1, 5), 1)
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "benchmark": benchmark,
            "benchmark_rate": benchmark_rate,
            "bid_spread": bid_spread,
            "ask_spread": ask_spread,
            "spread": spread_bps,
            "all_in_rate": all_in_rate,
            "price": all_in_rate,
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── RFQ v2 (accept) ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source="CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": rfq["payload"]["direction"],
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "tenor": tenor,
            "benchmark": benchmark,
            "spread_bps": spread_bps,
            "all_in_rate": all_in_rate,
            "client_entity_id": buyer["entity_id"],
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": quote["event_id"],
        },
    )
    events.append(rfq_accept)

    # ── TRADE ──
    fpml_irs = next((f for f in fpmls if f["product_type"] == pt), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, all_in_rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_irs["fpml_id"], ccy, far_ccy, notional, all_in_rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_irs["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{ccy}_{random.choice(REGIONS)}",
                "strategy": random.choice(["Market Making", "Flow"]),
                "clearing": random.choice(["LCH", "CME"]),
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20],
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: IMM_FIXING_RFQ
# RFQ → QUOTE(INDICATIVE, fixing=PENDING) → QUOTE(FIRM, fixing=FIXED) → TRADE
# =============================================================================

_IMM_DATES = ["IMM_H6", "IMM_M6", "IMM_U6", "IMM_Z6", "IMM_H7", "IMM_M7"]


def _scenario_imm_fixing_rfq(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """IRS RFQ with IMM date — two-stage quoting: PENDING fixing then FIXED."""
    events: list[dict[str, Any]] = []
    pt = "IRS"
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    tenor = random.choice(IRS_TENORS)
    benchmark_info = _IRS_BENCHMARKS[ccy]
    imm_date = random.choice(_IMM_DATES)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)
    sales = random.choice(SALES_NAMES)

    spread_bps = round(random.uniform(-10, 80), 1)
    benchmark_rate = round(random.uniform(2.5, 5.5), 4)
    all_in_rate = round(benchmark_rate + spread_bps / 100, 4)

    # ── RFQ (IRS with IMM date) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source=random.choice(["TRADEWEB", "BLOOMBERG"]),
        actor=sales,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "tenor": tenor,
            "imm_date": imm_date,
            "index": benchmark_info["index"],
            "limit_price": None,
            "valid_until": None,
            "client_entity_id": buyer["entity_id"],
            "num_dealers": random.randint(2, 5),
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE v1 (INDICATIVE — fixing PENDING) ──
    q_pending = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "spread": spread_bps,
            "benchmark_rate": None,
            "all_in_rate": None,
            "fixing_status": "PENDING",
            "imm_date": imm_date,
            "index": benchmark_info["index"],
            "valid_until": None,
            "quoted_by": trader,
            "status": "INDICATIVE",
            "revision": 1,
        },
    )
    events.append(q_pending)

    # ── QUOTE v2 (FIRM — fixing FIXED, benchmark rate now known) ──
    q_fixed = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": q_pending["event_id"], "rel": "SUPERSEDES", "role": "LHS"},
            {"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "spread": spread_bps,
            "benchmark_rate": benchmark_rate,
            "all_in_rate": all_in_rate,
            "fixing_status": "FIXED",
            "imm_date": imm_date,
            "index": benchmark_info["index"],
            "price": all_in_rate,
            "valid_until": None,
            "quoted_by": trader,
            "status": "FIRM",
            "revision": 2,
        },
    )
    events.append(q_fixed)

    # ── RFQ v2 (client accepts) ──
    rfq_accept = _make_event(
        "RFQ",
        status="ACCEPTED",
        source="CLIENT",
        actor=buyer["short_name"],
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "ACCEPTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "CLIENT",
        },
        payload={
            "direction": rfq["payload"]["direction"],
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "tenor": tenor,
            "imm_date": imm_date,
            "all_in_rate": all_in_rate,
            "client_entity_id": buyer["entity_id"],
            "revision": 2,
            "negotiation_status": "ACCEPTED",
            "accepted_quote_id": q_fixed["event_id"],
        },
    )
    events.append(rfq_accept)

    # ── TRADE ──
    fpml_irs = next((f for f in fpmls if f["product_type"] == "IRS"), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, all_in_rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_irs["fpml_id"], ccy, far_ccy, notional, all_in_rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq_accept["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": q_fixed["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_irs["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"IRS_{ccy}_{random.choice(REGIONS)}",
                "strategy": random.choice(["Market Making", "Flow"]),
                "clearing": random.choice(["LCH", "CME"]),
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20],
        },
    )
    events.append(trade)
    return events


# =============================================================================
# SCENARIO: DIRECT_CLEARING
# TRADE → CLEARING_SUBMISSION(PENDING) → CLEARING_SUBMISSION(ACCEPTED) →
# CLEARING_MSG(novation) → MARGIN_CALL
# =============================================================================


def _scenario_direct_clearing(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Trade followed by clearing submission, CCP novation, and margin call."""
    events: list[dict[str, Any]] = []
    pt = random.choice(["IRS", "CDS"])
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    ccp = random.choice(["LCH", "CME"])
    middleware = random.choice(["MarkitWire", "Traiana"])

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    fpml_tmpl = next((f for f in fpmls if f["product_type"] == pt), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_tmpl["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    submission_ref = f"CLR-{uuid.uuid4().hex[:10].upper()}"

    # ── TRADE ──
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_tmpl["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{ccy}_{random.choice(REGIONS)}",
                "strategy": random.choice(["Market Making", "Flow"]),
                "clearing": ccp,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20] if pt == "IRS" else None,
        },
    )
    events.append(trade)

    # ── CLEARING_SUBMISSION v1 (PENDING) ──
    cs_pending = _make_event(
        "CLEARING_SUBMISSION",
        status="ACTIVE",
        source=middleware,
        actor=middleware,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "OPS",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": ccp,
            "submission_ref": submission_ref,
            "middleware": middleware,
            "clearing_category": "HOUSE",
            "submission_status": "PENDING",
            "submitted_at": _random_datetime(-1, 0),
            "revision": 1,
        },
    )
    events.append(cs_pending)

    # ── CLEARING_SUBMISSION v2 (ACCEPTED) ──
    cs_accepted = _make_event(
        "CLEARING_SUBMISSION",
        status="ACTIVE",
        source=ccp,
        actor=ccp,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": cs_pending["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": ccp,
            "submission_ref": submission_ref,
            "middleware": middleware,
            "clearing_category": "HOUSE",
            "submission_status": "ACCEPTED",
            "clearing_id": _gen_id("event"),
            "accepted_at": _random_datetime(0, 0),
            "revision": 2,
        },
    )
    events.append(cs_accepted)

    # ── CLEARING_MSG (CCP novation) ──
    ccp_entities = [e for e in entities if e["entity_type"] == "CCP"]
    ccp_entity = random.choice(ccp_entities) if ccp_entities else random.choice(entities[:5])

    clr = _make_event(
        "CLEARING_MSG",
        status="CLEARED",
        source=ccp,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=ccp_entity["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "ccp": ccp,
            "clearing_id": cs_accepted["payload"]["clearing_id"],
            "original_cpty": seller["entity_id"],
            "novated_cpty": ccp_entity["entity_id"],
            "economics": {
                "product_type": pt,
                "notional": notional,
                "ccy": ccy,
                "trade_date": econ["trade_date"],
                "value_date": econ["value_date"],
            },
            "margin_required": round(notional * random.uniform(0.03, 0.08), 2),
            "clearing_fee": round(notional * random.uniform(0.0001, 0.0003), 2),
        },
    )
    events.append(clr)

    # ── MARGIN_CALL ──
    vm = round(notional * random.uniform(0.02, 0.06), 2)
    ia = round(notional * random.uniform(0.01, 0.03), 2)
    mc = _make_event(
        "MARGIN_CALL",
        status="ACTIVE",
        source=ccp,
        product_type=pt,
        notional=vm + ia,
        ccy=ccy,
        cpty_id=ccp_entity["entity_id"],
        priority="HIGH",
        links=[{"event_id": clr["event_id"], "rel": "ORIGINATES_FROM", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "vm_amount": vm,
            "ia_amount": ia,
            "ccy": ccy,
            "calculation_date": _random_date(-1, 0),
            "cpty_entity_id": buyer["entity_id"],
            "margin_type": "BOTH",
            "collateral_type": random.choice(["CASH", "GOVT_BOND"]),
            "deadline": _random_datetime(0, 1),
        },
    )
    events.append(mc)
    return events


# =============================================================================
# SCENARIO: CLEARING_REJECTED
# TRADE → CLEARING_SUBMISSION(PENDING) → CLEARING_SUBMISSION(REJECTED)
# =============================================================================


def _scenario_clearing_rejected(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Trade submitted for clearing but rejected by CCP."""
    events: list[dict[str, Any]] = []
    pt = random.choice(["IRS", "CDS"])
    ccy, far_ccy, ccy_pair = _pick_ccy_pair(pt)
    notional = _notional_for(pt)
    rate = _rate_for(pt)
    ccp = random.choice(["LCH", "CME"])
    middleware = random.choice(["MarkitWire", "Traiana"])

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    fpml_tmpl = next((f for f in fpmls if f["product_type"] == pt), fpmls[0])
    econ = _make_trade_economics(pt, ccy, notional, rate, ccy_pair)
    legs = _make_legs_for(pt, fpml_tmpl["fpml_id"], ccy, far_ccy, notional, rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    submission_ref = f"CLR-{uuid.uuid4().hex[:10].upper()}"

    # ── TRADE ──
    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="MATCHING_ENG",
        actor="MATCHING_ENG",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_tmpl["fpml_id"],
            "trade_date": econ["trade_date"],
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"{pt}_{ccy}_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": ccp,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": _uti()[:20] if pt == "IRS" else None,
        },
    )
    events.append(trade)

    # ── CLEARING_SUBMISSION v1 (PENDING) ──
    cs_pending = _make_event(
        "CLEARING_SUBMISSION",
        status="ACTIVE",
        source=middleware,
        actor=middleware,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "OPS",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": ccp,
            "submission_ref": submission_ref,
            "middleware": middleware,
            "clearing_category": "HOUSE",
            "submission_status": "PENDING",
            "submitted_at": _random_datetime(-1, 0),
            "revision": 1,
        },
    )
    events.append(cs_pending)

    # ── CLEARING_SUBMISSION v2 (REJECTED) ──
    cs_rejected = _make_event(
        "CLEARING_SUBMISSION",
        status="CANCELLED",
        source=ccp,
        actor=ccp,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": cs_pending["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": ccp,
            "submission_ref": submission_ref,
            "middleware": middleware,
            "clearing_category": "HOUSE",
            "submission_status": "REJECTED",
            "rejection_reason": random.choice([
                "Margin threshold exceeded",
                "Counterparty not eligible",
                "Product not clearable",
                "Duplicate submission",
                "Credit limit exceeded",
            ]),
            "revision": 2,
        },
    )
    events.append(cs_rejected)
    return events


# =============================================================================
# SCENARIO: BOND_AUCTION_FULL
# AUCTION_BID(OPEN) → AUCTION_BID(AWARDED 100%) → SETTLEMENT_INSTR
# =============================================================================

_AUCTION_SECURITIES = [
    ("912810TV0", "US Treasury", "10Y UST 4.25% 02/35", "USD"),
    ("912810TW8", "US Treasury", "30Y UST 4.50% 08/54", "USD"),
    ("912828ZP6", "US Treasury", "5Y UST 3.875% 11/29", "USD"),
    ("GB00BN65R198", "UK DMO", "10Y Gilt 4.00% 01/35", "GBP"),
    ("GB00BNNGFT35", "UK DMO", "30Y Gilt 4.375% 10/54", "GBP"),
    ("DE0001102580", "German FA", "10Y Bund 2.50% 02/35", "EUR"),
]


def _scenario_bond_auction_full(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Bond auction with full allotment (100% awarded)."""
    events: list[dict[str, Any]] = []
    auction = random.choice(_AUCTION_SECURITIES)
    auction_id, issuer, security_desc, ccy = auction
    bid_amount = round(random.uniform(50_000_000, 500_000_000), 2)
    bid_yield = round(random.uniform(2.5, 5.5), 4)
    bid_price = round(100 - (bid_yield * random.uniform(0.8, 1.2)), 4)
    stop_yield = round(bid_yield - random.uniform(0.01, 0.05), 4)
    bid_to_cover = round(random.uniform(2.0, 3.5), 2)

    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )

    # ── AUCTION_BID v1 (OPEN) ──
    bid_v1 = _make_event(
        "AUCTION_BID",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=bid_amount,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "ccy": ccy,
            "auction_status": "OPEN",
            "revision": 1,
        },
    )
    events.append(bid_v1)

    # ── AUCTION_BID v2 (AWARDED — 100%) ──
    bid_v2 = _make_event(
        "AUCTION_BID",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=bid_amount,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": bid_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "awarded_amount": bid_amount,
            "allotment_pct": 100,
            "stop_yield": stop_yield,
            "bid_to_cover": bid_to_cover,
            "ccy": ccy,
            "auction_status": "AWARDED",
            "revision": 2,
        },
    )
    events.append(bid_v2)

    # ── SETTLEMENT_INSTR ──
    si = _make_event(
        "SETTLEMENT_INSTR",
        status="ACTIVE",
        source="MANUAL",
        product_type="BOND",
        notional=bid_amount,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": bid_v2["event_id"], "rel": "ORIGINATES_FROM", "role": "CHILD"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "OPS",
        },
        payload={
            "payment_direction": "PAY",
            "amount": bid_amount,
            "ccy": ccy,
            "value_date": _random_date(1, 3),
            "ssi_id": _gen_id("event"),
            "nostro": f"{random.choice(['JPMC', 'CITI', 'HSBC'])}-{random.choice(['NY', 'LDN'])}",
            "cpty_ssi": _gen_id("event"),
            "cpty_entity_id": issuer,
            "settlement_method": "DVP",
            "auction_id": auction_id,
        },
    )
    events.append(si)
    return events


# =============================================================================
# SCENARIO: BOND_AUCTION_PARTIAL
# AUCTION_BID(OPEN) → AUCTION_BID(AWARDED <100%)
# =============================================================================


def _scenario_bond_auction_partial(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Bond auction with partial allotment (20-80% awarded)."""
    events: list[dict[str, Any]] = []
    auction = random.choice(_AUCTION_SECURITIES)
    auction_id, issuer, security_desc, ccy = auction
    bid_amount = round(random.uniform(50_000_000, 500_000_000), 2)
    bid_yield = round(random.uniform(2.5, 5.5), 4)
    bid_price = round(100 - (bid_yield * random.uniform(0.8, 1.2)), 4)
    allotment_pct = random.randint(20, 80)
    awarded_amount = round(bid_amount * allotment_pct / 100, 2)
    bid_to_cover = round(random.uniform(2.0, 3.5), 2)

    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── AUCTION_BID v1 (OPEN) ──
    bid_v1 = _make_event(
        "AUCTION_BID",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=bid_amount,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "ccy": ccy,
            "auction_status": "OPEN",
            "revision": 1,
        },
    )
    events.append(bid_v1)

    # ── AUCTION_BID v2 (AWARDED — partial) ──
    bid_v2 = _make_event(
        "AUCTION_BID",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=awarded_amount,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": bid_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "awarded_amount": awarded_amount,
            "allotment_pct": allotment_pct,
            "stop_yield": bid_yield,
            "bid_to_cover": bid_to_cover,
            "ccy": ccy,
            "auction_status": "AWARDED",
            "revision": 2,
        },
    )
    events.append(bid_v2)
    return events


# =============================================================================
# SCENARIO: BOND_AUCTION_MISS
# AUCTION_BID(OPEN) → AUCTION_BID(MISSED — 0% allotment)
# =============================================================================


def _scenario_bond_auction_miss(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Bond auction where we bid too aggressively (low yield) and miss entirely."""
    events: list[dict[str, Any]] = []
    auction = random.choice(_AUCTION_SECURITIES)
    auction_id, issuer, security_desc, ccy = auction
    bid_amount = round(random.uniform(50_000_000, 500_000_000), 2)
    bid_yield = round(random.uniform(2.5, 4.0), 4)
    bid_price = round(100 - (bid_yield * random.uniform(0.8, 1.2)), 4)
    stop_yield = round(bid_yield + random.uniform(0.05, 0.20), 4)
    bid_to_cover = round(random.uniform(2.0, 3.5), 2)

    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── AUCTION_BID v1 (OPEN) ──
    bid_v1 = _make_event(
        "AUCTION_BID",
        status="ACTIVE",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=bid_amount,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "ccy": ccy,
            "auction_status": "OPEN",
            "revision": 1,
        },
    )
    events.append(bid_v1)

    # ── AUCTION_BID v2 (MISSED — 0%) ──
    bid_v2 = _make_event(
        "AUCTION_BID",
        status="CANCELLED",
        source="MANUAL",
        actor=trader,
        desk=desk,
        product_type="BOND",
        notional=0,
        ccy=ccy,
        cpty_id=None,
        links=[{"event_id": bid_v1["event_id"], "rel": "SUPERSEDES", "role": "LHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "LHS",
            "actor_role": "TRADING",
        },
        payload={
            "auction_id": auction_id,
            "issuer": issuer,
            "security_desc": security_desc,
            "bid_type": "COMPETITIVE",
            "bid_yield": bid_yield,
            "bid_price": bid_price,
            "bid_amount": bid_amount,
            "awarded_amount": 0,
            "allotment_pct": 0,
            "stop_yield": stop_yield,
            "bid_to_cover": bid_to_cover,
            "ccy": ccy,
            "auction_status": "MISSED",
            "revision": 2,
        },
    )
    events.append(bid_v2)
    return events


# =============================================================================
# SCENARIO: BOND_CONNECT_BUY
# RFQ(OUTBOUND, BOND_CONNECT) → QUOTE(CNY) → TRADE → CLEARING_MSG(SHCH)
# =============================================================================

_CNY_BONDS = [
    ("CGB 2.85 11/30", "CGB", "China Government Bond"),
    ("CGB 3.05 06/33", "CGB", "China Government Bond"),
    ("CGB 2.48 09/28", "CGB", "China Government Bond"),
    ("CDB 3.15 06/28", "CDB", "China Development Bank"),
    ("CDB 3.40 03/32", "CDB", "China Development Bank"),
    ("ADBC 3.25 12/29", "ADBC", "Agricultural Dev Bank of China"),
    ("EXIM 3.10 08/30", "EXIM", "Export-Import Bank of China"),
]


def _scenario_bond_connect_buy(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Buy CNY bond via Bond Connect — RFQ → QUOTE → TRADE → CLEARING_MSG(SHCH)."""
    events: list[dict[str, Any]] = []
    pt = "BOND"
    ccy = "CNY"
    bond = random.choice(_CNY_BONDS)
    ticker, issuer_code, issuer_name = bond
    notional = round(random.uniform(10_000_000, 200_000_000), 2)
    price = round(random.uniform(95.0, 105.0), 4)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ (outbound via Bond Connect) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CFETS",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "PAY",
            "product_type": pt,
            "ticker": ticker,
            "issuer_code": issuer_code,
            "issuer_name": issuer_name,
            "notional": notional,
            "ccy": ccy,
            "rfq_direction": "OUTBOUND",
            "venue": "BOND_CONNECT",
            "initiator_desk": desk,
            "limit_price": None,
            "valid_until": None,
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": price,
            "spread": round(random.uniform(1.0, 15.0), 2),
            "valid_until": None,
            "quoted_by": "CFETS",
            "status": "FIRM",
            "ticker": ticker,
            "revision": 1,
        },
    )
    events.append(quote)

    # ── TRADE ──
    fpml_bond = next((f for f in fpmls if f["product_type"] == "BOND"), fpmls[0])
    legs = _make_legs_for(pt, fpml_bond["fpml_id"], ccy, ccy, notional, price)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_bond["fpml_id"],
            "trade_date": _random_date(-5, 0),
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"BOND_CNY_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": "SHCH",
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "venue": "BOND_CONNECT",
            "ticker": ticker,
        },
    )
    events.append(trade)

    # ── CLEARING_MSG (SHCH) ──
    ccp_entities = [e for e in entities if e["entity_type"] == "CCP"]
    ccp_entity = random.choice(ccp_entities) if ccp_entities else random.choice(entities[:5])

    clr = _make_event(
        "CLEARING_MSG",
        status="CLEARED",
        source="SHCH",
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=ccp_entity["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "ccp": "SHCH",
            "clearing_id": _gen_id("event"),
            "original_cpty": seller["entity_id"],
            "novated_cpty": ccp_entity["entity_id"],
            "economics": {
                "product_type": pt,
                "notional": notional,
                "ccy": ccy,
                "trade_date": trade["payload"]["trade_date"],
                "value_date": _random_date(1, 3),
            },
            "margin_required": round(notional * random.uniform(0.02, 0.05), 2),
            "clearing_fee": round(notional * random.uniform(0.0001, 0.0002), 2),
        },
    )
    events.append(clr)
    return events


# =============================================================================
# SCENARIO: BOND_CONNECT_SELL
# RFQ(OUTBOUND, BOND_CONNECT) → QUOTE → TRADE → SETTLEMENT_INSTR(DVP via CMU)
# =============================================================================


def _scenario_bond_connect_sell(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """Sell CNY bond back via Bond Connect — settlement via CMU (Hong Kong)."""
    events: list[dict[str, Any]] = []
    pt = "BOND"
    ccy = "CNY"
    bond = random.choice(_CNY_BONDS)
    ticker, issuer_code, issuer_name = bond
    notional = round(random.uniform(10_000_000, 200_000_000), 2)
    price = round(random.uniform(95.0, 105.0), 4)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ (outbound sell) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CFETS",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": "RECEIVE",
            "product_type": pt,
            "ticker": ticker,
            "issuer_code": issuer_code,
            "issuer_name": issuer_name,
            "notional": notional,
            "ccy": ccy,
            "rfq_direction": "OUTBOUND",
            "venue": "BOND_CONNECT",
            "initiator_desk": desk,
            "limit_price": None,
            "valid_until": None,
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": price,
            "spread": round(random.uniform(1.0, 15.0), 2),
            "valid_until": None,
            "quoted_by": "CFETS",
            "status": "FIRM",
            "ticker": ticker,
            "revision": 1,
        },
    )
    events.append(quote)

    # ── TRADE ──
    fpml_bond = next((f for f in fpmls if f["product_type"] == "BOND"), fpmls[0])
    legs = _make_legs_for(pt, fpml_bond["fpml_id"], ccy, ccy, notional, price)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_bond["fpml_id"],
            "trade_date": _random_date(-5, 0),
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"BOND_CNY_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": None,
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "venue": "BOND_CONNECT",
            "ticker": ticker,
        },
    )
    events.append(trade)

    # ── SETTLEMENT_INSTR (DVP via CMU) ──
    si = _make_event(
        "SETTLEMENT_INSTR",
        status="ACTIVE",
        source="CMU",
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=buyer["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "OPS",
        },
        payload={
            "payment_direction": "RECEIVE",
            "amount": notional,
            "ccy": ccy,
            "value_date": _random_date(1, 3),
            "ssi_id": _gen_id("event"),
            "nostro": f"CMU-HK",
            "cpty_ssi": _gen_id("event"),
            "cpty_entity_id": buyer["entity_id"],
            "settlement_method": "DVP",
            "venue": "BOND_CONNECT",
            "custodian": "CMU",
        },
    )
    events.append(si)
    return events


# =============================================================================
# SCENARIO: SWAP_CONNECT
# RFQ(SWAP_CONNECT, IRS) → QUOTE(CNY IRS, FR007/LPR) → TRADE →
# CLEARING_SUBMISSION(SHCH) → CLEARING_MSG
# =============================================================================

_CNY_IRS_BENCHMARKS = [
    {"index": "FR007", "dc_fixed": "ACT/365", "dc_float": "ACT/365", "freq": "3M"},
    {"index": "LPR_1Y", "dc_fixed": "ACT/365", "dc_float": "ACT/365", "freq": "3M"},
]


def _scenario_swap_connect(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """CNY IRS via Swap Connect — mandatory clearing at SHCH."""
    events: list[dict[str, Any]] = []
    pt = "IRS"
    ccy = "CNY"
    bm = random.choice(_CNY_IRS_BENCHMARKS)
    notional = round(random.uniform(50_000_000, 500_000_000), 2)
    tenor = random.choice(["1Y", "2Y", "3Y", "5Y"])
    fixed_rate = round(random.uniform(1.5, 3.5), 4)
    spread_bps = round(random.uniform(-5, 30), 1)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ (Swap Connect) ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CFETS",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "tenor": tenor,
            "index": bm["index"],
            "rfq_direction": "OUTBOUND",
            "venue": "SWAP_CONNECT",
            "initiator_desk": desk,
            "limit_price": None,
            "valid_until": None,
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE (CNY IRS spread over FR007/LPR) ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": fixed_rate,
            "spread": spread_bps,
            "benchmark": bm["index"],
            "valid_until": None,
            "quoted_by": "CFETS",
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── TRADE ──
    fpml_irs = next((f for f in fpmls if f["product_type"] == "IRS"), fpmls[0])
    legs = _make_legs_for(pt, fpml_irs["fpml_id"], ccy, ccy, notional, fixed_rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_irs["fpml_id"],
            "trade_date": _random_date(-5, 0),
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"IRS_CNY_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": "SHCH",
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "venue": "SWAP_CONNECT",
        },
    )
    events.append(trade)

    # ── CLEARING_SUBMISSION (mandatory at SHCH) ──
    submission_ref = f"CLR-{uuid.uuid4().hex[:10].upper()}"
    cs = _make_event(
        "CLEARING_SUBMISSION",
        status="ACTIVE",
        source="SHCH",
        actor="SHCH",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": "SHCH",
            "submission_ref": submission_ref,
            "middleware": "CFETS",
            "clearing_category": "HOUSE",
            "submission_status": "ACCEPTED",
            "clearing_id": _gen_id("event"),
            "accepted_at": _random_datetime(0, 0),
            "revision": 1,
        },
    )
    events.append(cs)

    # ── CLEARING_MSG ──
    ccp_entities = [e for e in entities if e["entity_type"] == "CCP"]
    ccp_entity = random.choice(ccp_entities) if ccp_entities else random.choice(entities[:5])

    clr = _make_event(
        "CLEARING_MSG",
        status="CLEARED",
        source="SHCH",
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=ccp_entity["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "ccp": "SHCH",
            "clearing_id": cs["payload"]["clearing_id"],
            "original_cpty": seller["entity_id"],
            "novated_cpty": ccp_entity["entity_id"],
            "economics": {
                "product_type": pt,
                "notional": notional,
                "ccy": ccy,
                "trade_date": trade["payload"]["trade_date"],
                "value_date": _random_date(1, 3),
            },
            "margin_required": round(notional * random.uniform(0.02, 0.05), 2),
            "clearing_fee": round(notional * random.uniform(0.0001, 0.0002), 2),
        },
    )
    events.append(clr)
    return events


# =============================================================================
# SCENARIO: SWAP_CONNECT_REJECT
# RFQ → QUOTE → TRADE → CLEARING_SUBMISSION(REJECTED by SHCH)
# =============================================================================


def _scenario_swap_connect_reject(
    entities: list[dict], books: list[dict], fpmls: list[dict]
) -> list[dict[str, Any]]:
    """CNY IRS via Swap Connect — clearing rejected by SHCH."""
    events: list[dict[str, Any]] = []
    pt = "IRS"
    ccy = "CNY"
    bm = random.choice(_CNY_IRS_BENCHMARKS)
    notional = round(random.uniform(50_000_000, 500_000_000), 2)
    tenor = random.choice(["1Y", "2Y", "3Y", "5Y"])
    fixed_rate = round(random.uniform(1.5, 3.5), 4)

    buyer = random.choice(entities[:10])
    seller = random.choice(
        [e for e in entities[:10] if e["entity_id"] != buyer["entity_id"]]
    )
    book = random.choice(books)
    trader, desk = random.choice(TRADER_NAMES), random.choice(DESKS)

    # ── RFQ ──
    rfq = _make_event(
        "RFQ",
        status="ACTIVE",
        source="CFETS",
        actor=trader,
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=None,
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "OPEN",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "TRADING",
        },
        payload={
            "direction": random.choice(DIRECTIONS),
            "product_type": pt,
            "notional": notional,
            "ccy": ccy,
            "tenor": tenor,
            "index": bm["index"],
            "rfq_direction": "OUTBOUND",
            "venue": "SWAP_CONNECT",
            "initiator_desk": desk,
            "revision": 1,
            "negotiation_status": "OPEN",
        },
    )
    events.append(rfq)

    # ── QUOTE ──
    quote = _make_event(
        "QUOTE",
        status="ACTIVE",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": rfq["event_id"], "rel": "RESPONDS_TO", "role": "RHS"}],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "QUOTED",
            "cardinality": "ONE_TO_ONE",
            "direction": "RHS",
            "actor_role": "BROKER",
        },
        payload={
            "rfq_event_id": rfq["event_id"],
            "price": fixed_rate,
            "spread": round(random.uniform(-5, 30), 1),
            "benchmark": bm["index"],
            "valid_until": None,
            "quoted_by": "CFETS",
            "status": "FIRM",
            "revision": 1,
        },
    )
    events.append(quote)

    # ── TRADE ──
    fpml_irs = next((f for f in fpmls if f["product_type"] == "IRS"), fpmls[0])
    legs = _make_legs_for(pt, fpml_irs["fpml_id"], ccy, ccy, notional, fixed_rate)
    parties = _make_parties(buyer["entity_id"], seller["entity_id"])

    trade = _make_event(
        "TRADE",
        status="CONFIRMED",
        source="CFETS",
        actor="CFETS",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[
            {"event_id": rfq["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
            {"event_id": quote["event_id"], "rel": "CREATED_FROM", "role": "PARENT"},
        ],
        correlation={
            "match_type": "NEGOTIATION",
            "match_status": "MATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "PARENT",
            "actor_role": "SYSTEM",
        },
        enriched=_make_enriched(),
        payload={
            "trade_id": _gen_id("event"),
            "fpml_type": fpml_irs["fpml_id"],
            "trade_date": _random_date(-5, 0),
            "parties": parties,
            "ned": {
                "book_id": book["book_id"],
                "portfolio": f"IRS_CNY_{random.choice(REGIONS)}",
                "strategy": "Flow",
                "clearing": "SHCH",
            },
            "legs": legs,
            "uti": _uti(),
            "usi": None,
            "venue": "SWAP_CONNECT",
        },
    )
    events.append(trade)

    # ── CLEARING_SUBMISSION (REJECTED by SHCH) ──
    submission_ref = f"CLR-{uuid.uuid4().hex[:10].upper()}"
    cs_rejected = _make_event(
        "CLEARING_SUBMISSION",
        status="CANCELLED",
        source="SHCH",
        actor="SHCH",
        desk=desk,
        product_type=pt,
        notional=notional,
        ccy=ccy,
        cpty_id=seller["entity_id"],
        links=[{"event_id": trade["event_id"], "rel": "SETTLES", "role": "CHILD"}],
        correlation={
            "match_type": "CORRELATION",
            "match_status": "UNMATCHED",
            "cardinality": "ONE_TO_ONE",
            "direction": "CHILD",
            "actor_role": "CCP",
        },
        payload={
            "trade_event_id": trade["event_id"],
            "ccp": "SHCH",
            "submission_ref": submission_ref,
            "middleware": "CFETS",
            "clearing_category": "HOUSE",
            "submission_status": "REJECTED",
            "rejection_reason": random.choice([
                "Position limit exceeded",
                "Product not eligible for Swap Connect",
                "Counterparty not registered",
            ]),
            "revision": 1,
        },
    )
    events.append(cs_rejected)
    return events


# =============================================================================
# BATCH GENERATION
# =============================================================================

SCENARIO_WEIGHTS = [
    # Price Discovery
    (_scenario_rfq_hit, 10),
    (_scenario_rfq_miss, 5),
    (_scenario_competitive_rfq, 5),
    # Execution
    (_scenario_back_to_back, 6),
    (_scenario_stp_auto, 7),
    (_scenario_broker_exec, 6),
    (_scenario_obo_client, 5),
    # Booking
    (_scenario_sales_direct, 5),
    (_scenario_trader_first, 4),
    # Prime Brokerage
    (_scenario_giveup, 4),
    # Matching/Breaks
    (_scenario_unmatched_booking, 4),
    (_scenario_partial_match, 3),
    (_scenario_failed_stp, 3),
    (_scenario_force_match, 4),
    (_scenario_rematch, 3),
    (_scenario_dispute, 3),
    # Product-Specific
    (_scenario_fx_compensation, 8),
    (_scenario_irs_clearing, 7),
    (_scenario_bond_broker_exec, 6),
    (_scenario_fx_option_hedge, 5),
    # Post-Trade
    (_scenario_allocation, 4),
    (_scenario_trade_confirm, 3),
    # Lifecycle
    (_scenario_cancel, 4),
    (_scenario_novation, 3),
    (_scenario_roll, 3),
    (_scenario_exercise, 3),
    # Recon
    (_scenario_settlement_recon, 3),
    (_scenario_eod_position, 3),
    (_scenario_margin_recon, 2),
    (_scenario_regulatory_recon, 2),
    # Surveillance
    (_scenario_market_abuse_spoofing, 3),
    # Ops
    (_scenario_compression, 3),
    # ── Pre-Trade Expansion ──
    # AXE / IOI
    (_scenario_axe_to_rfq, 5),
    (_scenario_axe_withdraw, 3),
    # Outbound RFQ
    (_scenario_outbound_rfq_hit, 5),
    (_scenario_outbound_rfq_miss, 3),
    # Streaming / Two-Way
    (_scenario_streaming_quote, 8),
    (_scenario_stream_to_trade, 5),
    (_scenario_stream_to_rfq, 5),
    # Spread / Benchmark
    (_scenario_spread_rfq, 5),
    (_scenario_imm_fixing_rfq, 3),
    # Direct Clearing
    (_scenario_direct_clearing, 5),
    (_scenario_clearing_rejected, 2),
    # Bond Auction
    (_scenario_bond_auction_full, 3),
    (_scenario_bond_auction_partial, 3),
    (_scenario_bond_auction_miss, 2),
    # China Connect
    (_scenario_bond_connect_buy, 3),
    (_scenario_bond_connect_sell, 2),
    (_scenario_swap_connect, 3),
    (_scenario_swap_connect_reject, 1),
]


# =============================================================================
# DENORMALIZE ECONOMICS — extract flat convenience fields from nested payloads
# =============================================================================
# Templates in xftws.yaml reference simple top-level fields: direction, rate,
# ccy_pair, tenor, index, spread_bps, reference_entity, issuer, security_desc,
# option_type. This function extracts them from the polymorphic payload structure
# (RFQ vs TRADE vs BOOKING payloads differ) so the frontend doesn't have to.


def _compute_tenor(start: str | None, end: str | None) -> str | None:
    """Compute human-readable tenor from ISO date strings (e.g. '5Y', '3M')."""
    if not start or not end:
        return None
    try:
        s = datetime.strptime(start[:10], "%Y-%m-%d")
        e = datetime.strptime(end[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    days = (e - s).days
    if days <= 0:
        return None
    if days >= 365:
        years = round(days / 365.25)
        return f"{years}Y"
    if days >= 28:
        months = round(days / 30.44)
        return f"{months}M"
    return f"{days}D"


def _denormalize_economics(evt: dict[str, Any]) -> None:
    """Extract flat convenience fields from event payload onto top-level.

    Tries payload-level fields first (RFQ/ORDER), then leg-level (TRADE/BOOKING),
    then trade_economics (FX bookings). Sets None for missing fields.
    """
    payload = evt.get("payload") or {}
    legs = payload.get("legs") or []
    te = payload.get("trade_economics") or {}
    leg0 = legs[0] if len(legs) > 0 else {}
    leg1 = legs[1] if len(legs) > 1 else {}

    # direction: payload → leg[0] → trade_economics
    evt["direction"] = (
        payload.get("direction")
        or payload.get("rfq_direction")
        or leg0.get("direction")
        or te.get("direction")
    )

    # ccy_pair: payload → trade_economics
    evt["ccy_pair"] = payload.get("ccy_pair") or te.get("ccy_pair")

    # rate: leg[0].rate → trade_economics.rate → limit_price → bid_price → mid_price
    evt["rate"] = (
        leg0.get("rate")
        or te.get("rate")
        or payload.get("limit_price")
        or payload.get("bid_price")
        or payload.get("mid_price")
    )

    # tenor: computed from leg[0] start/end dates
    evt["tenor"] = _compute_tenor(leg0.get("start_date"), leg0.get("end_date"))

    # index: float leg index (leg[1] for IRS/XCCY, leg[0] fallback)
    evt["index"] = leg1.get("index") or leg0.get("index")

    # spread_bps: float leg spread or CDS premium
    evt["spread_bps"] = leg1.get("spread_bps") or leg0.get("spread_bps")

    # reference_entity: CDS
    evt["reference_entity"] = leg0.get("reference_entity") or payload.get("reference_entity")

    # issuer: bonds/auctions
    evt["issuer"] = payload.get("issuer")

    # security_desc: bonds/auctions
    evt["security_desc"] = payload.get("security_desc")

    # option_type: swaptions, FX options
    evt["option_type"] = payload.get("option_type")


def gen_fixtures(count: int = 30) -> dict[str, list[dict[str, Any]]]:
    """Generate all xftws fixtures with proper FK relationships.

    Produces 4 datasets: entities, books, fpmls, events.
    Events are generated as scenario chains with post-trade enrichment.

    count=30 produces ~30 trade scenarios × ~8 events/scenario ≈ 300+ events.
    Includes: matched, unmatched, partial, force-matched, failed STP,
    multi-version amendments, and full settlement/netting workflows.
    """
    _EventSeq.reset()

    # ── Reference data ──
    entities: list[dict[str, Any]] = []
    for i, (name, short) in enumerate(ENTITY_NAMES[:count]):
        e = EntityFactory(name=name, short_name=short)
        if i >= 5:
            e["parent_entity_id"] = entities[random.randint(0, 4)]["entity_id"]
        entities.append(e)

    n_books = max(count, 10)
    books: list[dict[str, Any]] = []
    for _ in range(n_books):
        entity = random.choice(entities[: min(10, len(entities))])
        books.append(BookFactory(entity_id=entity["entity_id"]))

    fpml_defs = [
        ("FPML-FX-SPOT", "FX_SPOT", "FX Spot — T+2 delivery", ["SPOT"]),
        ("FPML-FX-FWD", "FX_FORWARD", "FX Forward — future delivery", ["FORWARD"]),
        ("FPML-FX-SWAP", "FX_SWAP", "FX Swap — near + far legs", ["NEAR", "FAR"]),
        ("FPML-FX-NDF", "FX_NDF", "FX NDF — non-deliverable forward", ["FORWARD"]),
        ("FPML-FX-OPT", "FX_OPTION", "FX Option — vanilla", ["OPTION", "FEE"]),
        ("FPML-IRS", "IRS", "Interest Rate Swap — fixed vs float", ["FIXED", "FLOAT"]),
        ("FPML-XCCY", "XCCY_SWAP", "Cross Currency Swap", ["FIXED", "FLOAT"]),
        ("FPML-SWAPTION", "SWAPTION", "Swaption — option on IRS", ["OPTION", "FEE"]),
        ("FPML-FRA", "FRA", "Forward Rate Agreement", ["FRA"]),
        ("FPML-BOND", "BOND", "Bond — fixed coupon", ["FIXED"]),
        ("FPML-BOND-FUT", "BOND_FUTURE", "Bond Future", ["FUTURE"]),
        ("FPML-REPO", "REPO", "Repurchase Agreement", ["REPO", "COLLATERAL"]),
        ("FPML-CDS", "CDS", "Credit Default Swap", ["PROTECTION", "PREMIUM"]),
        ("FPML-TRS", "TRS", "Total Return Swap", ["TOTAL_RETURN", "FINANCING"]),
        ("FPML-EQUITY", "EQUITY", "Cash Equity", ["CASH"]),
    ]
    fpmls: list[dict[str, Any]] = [
        FPMLFactory(fpml_id=fid, product_type=pt, description=desc, leg_types=lt)
        for fid, pt, desc, lt in fpml_defs
    ]

    # ── Generate scenario chains ──
    all_events: list[dict[str, Any]] = []
    trade_events: list[dict[str, Any]] = []

    scenario_pool = []
    for fn, weight in SCENARIO_WEIGHTS:
        scenario_pool.extend([fn] * weight)

    # Guarantee at least one instance of every scenario, then fill remaining
    # slots with weighted random picks. This prevents demo picker blanks.
    guaranteed = [fn for fn, _w in SCENARIO_WEIGHTS]
    remaining = max(0, count - len(guaranteed))
    picks = guaranteed + [random.choice(scenario_pool) for _ in range(remaining)]
    random.shuffle(picks)

    for scenario_fn in picks:
        chain = scenario_fn(entities, books, fpmls)

        # Derive canonical scenario name from function name
        # e.g. _scenario_rfq_hit -> RFQ_HIT — matches YAML lifecycle keys
        scenario_name = scenario_fn.__name__.removeprefix("_scenario_").upper()

        # Shared chain_id ties all events in this scenario instance together
        chain_id = f"CHN-{uuid.uuid4().hex[:12].upper()}"

        # Stamp every event in the chain with correct scenario + chain_id.
        # Preserves custom correlation fields (match_type, breaks, etc.)
        for evt in chain:
            corr = evt.get("correlation")
            if corr is None:
                evt["correlation"] = {
                    "chain_id": chain_id,
                    "match_type": "CORRELATION",
                    "scenario": scenario_name,
                    "match_status": "PENDING",
                    "cardinality": "ONE_TO_MANY",
                    "direction": None,
                    "actor_role": None,
                    "breaks": [],
                    "resolution": None,
                    "matched_at": None,
                    "matched_by": None,
                }
            else:
                corr["scenario"] = scenario_name
                corr["chain_id"] = chain_id
                if "actor_role" not in corr:
                    corr["actor_role"] = None

            # Infer actor_role from event_type when still None
            corr = evt["correlation"]
            if corr.get("actor_role") is None:
                et = evt.get("event_type", "")
                corr["actor_role"] = _ACTOR_ROLE_FALLBACK.get(et, "SYSTEM")

            # Infer direction from actor_role when still None
            if corr.get("direction") is None:
                role = corr.get("actor_role", "")
                if role in ("CLIENT", "SALES"):
                    corr["direction"] = "LHS"
                elif role in ("TRADING", "BROKER"):
                    corr["direction"] = "RHS"
                elif role == "SYSTEM":
                    corr["direction"] = "PARENT"
                elif role in ("CCP", "OPS"):
                    corr["direction"] = "CHILD"
                else:
                    corr["direction"] = "LHS"

        # Fix timestamps: sequential with realistic delays per event_type.
        # Base time spreads chains across a business day window.
        base = datetime.now() - timedelta(
            hours=random.randint(0, 8),
            minutes=random.randint(0, 59),
        )
        _chain_timestamps(chain, base)
        _apply_sla_deadlines(chain, scenario_name)

        all_events.extend(chain)
        for evt in chain:
            if evt["event_type"] == "TRADE":
                trade_events.append(evt)

    # ── Post-trade enrichment ──
    # Each enrichment event inherits chain_id from its parent trade and gets
    # realistic timestamps sequentially after the trade's created_at.
    settlement_events: list[dict[str, Any]] = []

    for trade in trade_events:
        chain_id = _parent_chain_id(trade)
        # Collect enrichment events for this trade, then timestamp them
        enrichments: list[dict[str, Any]] = []

        if random.random() < 0.60:
            enrichments.append(_add_clearing(trade, entities))
        if random.random() < 0.50:
            enrichments.append(_add_affirm(trade, entities))
        if random.random() < 0.25:
            enrichments.extend(_add_alloc_splits(trade, entities, books))
        if random.random() < 0.35:
            enrichments.extend(_add_amendment(trade))
        if random.random() < 0.50:
            si = _add_settlement(trade, entities)
            enrichments.append(si)
            settlement_events.append(si)
        # enrichments.extend(_add_risk_measures(trade))  # removed — noise in demo/fixture
        enrichments.extend(_add_schedule_events(trade))
        if random.random() < 0.20:
            enrichments.append(_add_margin_call(trade, entities))

        # Stamp chain_id + sequential timestamps from trade time
        trade_time = datetime.strptime(trade["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        _chain_timestamps(enrichments, trade_time)
        parent_scenario = _parent_scenario(trade, "")
        _apply_sla_deadlines(enrichments, parent_scenario)
        for evt in enrichments:
            corr = evt.get("correlation")
            if isinstance(corr, dict) and chain_id:
                corr["chain_id"] = chain_id
        all_events.extend(enrichments)

    # Net settlement — group settlement instructions into netting sets
    if len(settlement_events) >= 2:
        remaining_si = list(settlement_events)
        random.shuffle(remaining_si)
        while len(remaining_si) >= 2:
            group_size = min(random.randint(2, 3), len(remaining_si))
            group = remaining_si[:group_size]
            remaining_si = remaining_si[group_size:]
            ns = _add_net_settlement(group, entities)
            # Inherit chain_id from first settlement in group
            ns_chain = _parent_chain_id(group[0])
            if ns_chain and isinstance(ns.get("correlation"), dict):
                ns["correlation"]["chain_id"] = ns_chain
            all_events.append(ns)

    # Position snapshots (EOD) — cross-trade, own chain_id
    snapshots = _add_position_snapshots(books, trade_events)
    eod_chain_id = f"CHN-{uuid.uuid4().hex[:12].upper()}"
    for snap in snapshots:
        corr = snap.get("correlation")
        if isinstance(corr, dict):
            corr["chain_id"] = eod_chain_id
    all_events.extend(snapshots)

    # Denormalize economics: extract flat convenience fields from nested payloads
    for evt in all_events:
        _denormalize_economics(evt)

    return {
        "entities": entities,
        "books": books,
        "fpmls": fpmls,
        "events": all_events,
    }


# =============================================================================
# ASYNC INTERFACE (required by gen_fixtures.py)
# =============================================================================


async def generate_fixtures(
    ctx: FixtureContext,
) -> AsyncIterator[tuple[str, list[dict[str, Any]]]]:
    """Async generator yielding (dataset_name, records) tuples."""
    data = gen_fixtures()
    for name, records in data.items():
        yield name, records
