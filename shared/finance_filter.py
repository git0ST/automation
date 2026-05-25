"""Multi-signal market-relevance classifier.

Combines 5 signal layers to decide if an article matters to a trader:
  1. Direct finance — tickers, earnings, FOMC, macro keywords
  2. Macro event — geopolitics, policy, supply chain, disasters
  3. Influencer — high-value people whose statements move markets
  4. High-value entity — orgs whose actions move markets (SpaceX, OpenAI, etc.)
  5. Innovation — tech/science breakthroughs with market spillover potential

Each layer contributes evidence; total score determines KEEP/DROP.
Designed to catch second-order effects (research → product → market shift,
launch → public reaction → emotional sentiment → price action).
"""
from __future__ import annotations
import re

# ── Layer 1: Ticker universe ────────────────────────────────────────────────
TICKERS = frozenset({
    # Mega caps
    "NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AVGO",
    "ORCL", "BRK.B", "BRK-B", "BRKB",
    # Semis
    "AMD", "INTC", "QCOM", "ARM", "SMCI", "TSM", "MU", "MRVL", "ASML", "LRCX",
    "AMAT", "KLAC", "NXPI", "ON",
    # Software
    "CRM", "ADBE", "NOW", "SNOW", "PLTR", "DDOG", "MDB", "NET", "CRWD", "ZS",
    "PANW", "FTNT", "OKTA", "SHOP", "TEAM", "WDAY",
    # Financials
    "JPM", "GS", "MS", "BAC", "WFC", "C", "BLK", "V", "MA", "AXP", "SCHW",
    "USB", "PNC", "TFC", "COF", "SPGI", "MCO", "CB", "AIG", "PYPL",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "PSX", "VLO", "MPC", "PXD",
    # Healthcare
    "UNH", "LLY", "JNJ", "MRK", "PFE", "ABBV", "TMO", "ABT", "DHR", "AMGN",
    "BMY", "GILD", "MDT", "ISRG", "SYK",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "DIS", "NFLX",
    "BKNG", "ABNB", "CMG", "LULU",
    # Communication / industrials
    "VZ", "T", "TMUS", "CMCSA", "CHTR", "EA", "TTWO", "RBLX",
    "BA", "CAT", "GE", "RTX", "HON", "UPS", "FDX", "DE", "LMT", "NOC",
    # ETFs + indices
    "SPY", "QQQ", "IWM", "DIA", "VTI", "GLD", "SLV", "TLT", "HYG", "LQD",
    "EEM", "VEA", "VWO", "ARKK", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "MATIC", "AVAX", "DOT",
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^FTSE", "^N225", "^HSI",
    "^STOXX50E", "^TNX", "^FVX",
})


# ── Layer 1: Strong finance keywords (auto-keep) ────────────────────────────
STRONG_KEYWORDS = frozenset({
    "earnings", "cpi", "ppi", "pce", "fomc", "fed", "vix", "ipo", "nasdaq",
    "s&p", "sp500", "djia", "nikkei", "ftse", "tariff", "tariffs", "treasury",
    "powell", "yellen", "etf", "options flow", "hedge fund", "wallstreet",
    "wall street",
})


# ── Layer 1: Finance keywords ────────────────────────────────────────────────
FINANCE_KEYWORDS = frozenset({
    "stock", "stocks", "equity", "equities", "market", "markets", "index",
    "indices", "etf", "etfs", "futures", "options", "derivative", "bond",
    "bonds", "treasury", "treasuries", "yield", "yields",
    "inflation", "cpi", "ppi", "pce", "gdp", "unemployment", "jobless",
    "payrolls", "nfp", "fomc", "fed", "interest rate", "rate cut", "rate hike",
    "hawkish", "dovish", "tightening", "easing", "stimulus", "qe", "qt",
    "trading", "trader", "investor", "hedge fund", "institutional", "retail",
    "volume", "volatility", "vix", "rally", "selloff", "correction", "bear",
    "bull", "bullish", "bearish", "long", "short", "squeeze", "liquidity",
    "leverage", "margin",
    "earnings", "revenue", "guidance", "outlook", "forecast", "beat", "miss",
    "merger", "acquisition", "ipo", "spinoff", "buyback", "dividend",
    "insider", "10-k", "10-q", "8-k", "sec filing", "proxy",
    "semiconductor", "semiconductors", "chip", "chips", "biotech",
    "pharmaceutical", "ev", "electric vehicle", "renewable", "fintech",
    "saas", "cloud", "cybersecurity",
    "recession", "soft landing", "hard landing", "deflation", "stagflation",
    "goldilocks", "reflation", "yield curve", "inversion", "credit spread",
    "junk bond", "high yield", "investment grade",
    "oil", "crude", "wti", "brent", "natural gas", "gold", "silver", "copper",
    "wheat", "corn", "soybean", "opec",
    "forex", "fx", "dollar", "dxy", "euro", "yen", "yuan", "renminbi",
    "currency", "exchange rate", "crypto", "cryptocurrency", "bitcoin",
    "ethereum", "stablecoin", "defi",
})


# ── Layer 2: Macro events (geopolitics/policy/supply chain) ─────────────────
MACRO_EVENT_KEYWORDS = frozenset({
    # Conflict / military
    "war", "warfare", "military", "conflict", "invasion", "missile", "strike",
    "drone strike", "sanctions", "embargo", "ceasefire", "geopolitical",
    "nato", "putin", "zelensky", "kremlin", "pentagon", "white house",
    # Market-moving regions
    "russia", "ukraine", "china", "taiwan", "iran", "israel", "gaza",
    "north korea", "middle east", "south china sea", "strait of hormuz",
    # Supply chain
    "supply chain", "pipeline", "port strike", "shipping", "container",
    "logistics", "shortage", "tariff", "trade war", "export ban",
    "chip act", "chips act", "huawei", "tsmc",
    # Energy events
    "opec", "saudi", "uae", "shale", "lng", "rare earth", "lithium", "cobalt",
    # Policy / elections
    "election", "fed chair", "treasury secretary", "rate decision",
    "tax cut", "tax hike", "regulation", "antitrust", "doj", "ftc",
    # Health / disaster
    "pandemic", "outbreak", "vaccine", "recall", "fda approval",
    "hurricane", "earthquake", "tsunami", "wildfire", "natural disaster",
    # Cyber / infrastructure
    "cyberattack", "ransomware", "breach", "data leak", "swift",
    "infrastructure attack", "grid attack", "major outage",
})


# ── Layer 3: Influential people (statements/actions move markets) ──────────
INFLUENCERS = frozenset({
    # Tech CEOs (every word/move moves their tickers + sector)
    "elon musk", "jensen huang", "tim cook", "satya nadella", "sundar pichai",
    "mark zuckerberg", "andy jassy", "sam altman", "dario amodei",
    "demis hassabis", "lisa su", "pat gelsinger", "larry ellison",
    "marc benioff", "shantanu narayen",
    # Investors / fund managers
    "warren buffett", "charlie munger", "ray dalio", "stanley druckenmiller",
    "bill ackman", "carl icahn", "michael burry", "cathie wood",
    "ken griffin", "steve cohen", "david tepper", "paul tudor jones",
    "george soros", "howard marks", "jim simons", "seth klarman",
    # Central bankers
    "jerome powell", "janet yellen", "christine lagarde", "kazuo ueda",
    "andrew bailey", "tiff macklem",
    # Regulators / officials
    "gary gensler", "lina khan", "scott bessent",
    # AI/tech research leaders (shape sector moves)
    "yann lecun", "geoffrey hinton", "andrej karpathy", "ilya sutskever",
})


# ── Layer 4: High-value organizations (their actions move markets) ──────────
HIGH_VALUE_ORGS = frozenset({
    # Big tech (public + private with IPO/M&A potential)
    "apple", "microsoft", "google", "alphabet", "amazon", "meta", "facebook",
    "nvidia", "tesla", "openai", "anthropic", "spacex", "stripe", "databricks",
    "scale ai", "perplexity", "xai", "mistral", "cohere",
    "broadcom", "oracle", "intel", "amd", "arm", "qualcomm", "tsmc", "asml",
    "samsung", "sony", "softbank",
    # Finance
    "berkshire", "berkshire hathaway", "blackrock", "vanguard", "fidelity",
    "jpmorgan", "goldman sachs", "morgan stanley", "bank of america",
    "wells fargo", "citi", "citigroup", "deutsche bank", "ubs", "barclays",
    "hsbc", "credit suisse",
    "renaissance", "citadel", "bridgewater", "two sigma", "millennium",
    "elliott management", "pershing square", "ark invest",
    # Other market-movers
    "saudi aramco", "exxon", "exxonmobil", "chevron", "shell", "bp",
    "boeing", "lockheed", "raytheon",
    "pfizer", "moderna", "merck", "novo nordisk", "eli lilly",
    "walmart", "costco", "home depot",
    "netflix", "disney", "warner",
    # Regulatory / central
    "federal reserve", "ecb", "european central bank", "bank of japan",
    "bank of england", "people's bank of china", "rbi",
    "sec", "cftc", "finra", "doj", "ftc", "treasury department",
    "european commission", "imf", "world bank",
    # Crypto / web3 (volatile but market-relevant)
    "binance", "coinbase", "kraken", "tether",
    # Government / regulators (actions move sectors)
    "white house", "congress", "senate", "house of representatives",
    "fbi", "cia", "nsa", "epa", "faa", "cisa", "uspto", "nih",
    "european union", "european parliament", "uk parliament",
    # Research labs / institutions with market spillover
    "mit", "stanford", "carnegie mellon", "caltech",
    "darpa", "doe", "lawrence livermore", "los alamos", "argonne",
    "cern", "iter", "nasa", "esa",
    "google deepmind", "google research", "microsoft research",
    "meta ai", "fair", "amazon science",
})


# ── Layer 5: Innovation/research with market spillover potential ────────────
INNOVATION_KEYWORDS = frozenset({
    # AI / ML breakthroughs (affect NVDA, MSFT, GOOGL, semis sector)
    "ai breakthrough", "agi", "frontier model", "foundation model", "llm",
    "large language model", "gpt", "claude", "gemini", "transformer",
    "diffusion model", "ai chip", "ai accelerator", "ai infrastructure",
    "ai agent", "agentic ai", "ai safety", "reinforcement learning",
    # Hardware / semis (affect entire sector)
    "quantum computing", "quantum supremacy", "neuromorphic", "photonic",
    "3nm chip", "2nm chip", "1nm chip", "euv lithography", "asml machine",
    "tsmc fab", "foundry", "advanced packaging", "hbm memory",
    # Biotech / pharma
    "gene therapy", "crispr", "mrna", "clinical trial", "phase 3 trial",
    "fda fast track", "alzheimer drug", "cancer breakthrough", "obesity drug",
    "weight loss drug", "glp-1", "ozempic", "wegovy",
    # Energy / climate
    "fusion energy", "fusion breakthrough", "nuclear fusion", "solid-state battery",
    "battery breakthrough", "carbon capture", "hydrogen", "ev battery",
    "autonomous driving", "robotaxi", "self-driving",
    # Space / aerospace (SpaceX, etc.)
    "space launch", "rocket launch", "starship", "satellite constellation",
    "starlink", "mars mission", "lunar mission", "space station",
    # Robotics / automation
    "humanoid robot", "optimus robot", "industrial robot", "robotic arm",
    "autonomous robot",
    # Cyber / infra
    "post-quantum crypto", "ai security", "deepfake detection",
    # Future-tech
    "neural interface", "brain computer", "neuralink", "augmented reality",
    "ar glasses", "vision pro", "metaverse",
    # Connectivity / hardware (5G→6G, WiFi → IoT, surveillance, sensor industries)
    "wifi", "wi-fi", "5g", "6g", "wireless", "starlink", "broadband", "fiber optic",
    "satellite internet", "iot", "internet of things", "edge computing",
    "sensor breakthrough", "lidar", "radar", "imaging",
    # Vision / robotics / automation
    "computer vision", "image recognition", "speech recognition",
    "facial recognition", "biometric", "surveillance technology",
    "warehouse automation", "industrial automation", "drone delivery",
    # Bio / med-tech
    "medical device", "fda clearance", "fda approval", "drug approval",
    "clinical phase", "phase 1 trial", "phase 2 trial", "biomarker",
    # Generic breakthrough markers — paired with org/entity boosts score
    "breakthrough", "research breakthrough", "scientific breakthrough",
    "first ever", "world first", "patent granted",
})


# ── Anti-spam: hard-drop on these in title ──────────────────────────────────
BAD_KEYWORDS = frozenset({
    "encyclical", "vatican", "pope", "papal", "monastery", "prayer",
    "kardashian", "taylor swift", "kpop", "anime", "manga",
    "league of legends", "minecraft", "fortnite", "video game launch",
    "esports tournament",
    "vegan diet", "yoga retreat", "marathon training", "gardening tutorial",
    "knitting",
    "kubernetes tutorial", "rust crate", "javascript framework",
    "css trick", "react hook tutorial",
    "world cup match", "olympics medal ceremony", "super bowl halftime",
})


# ── Compiled patterns ────────────────────────────────────────────────────────
_TICKER_PATTERN = re.compile(r"\b\$?([A-Z]{1,5}(?:\.[A-Z])?|\^[A-Z]{2,5})\b")
_DOLLAR_TICKER_PATTERN = re.compile(r"\$([A-Z]{1,5})\b")


def extract_tickers(text: str) -> list[str]:
    """Extract validated ticker symbols from text."""
    if not text:
        return []
    found = set()
    for m in _DOLLAR_TICKER_PATTERN.finditer(text):
        sym = m.group(1).upper()
        if sym in TICKERS:
            found.add(sym)
    for m in _TICKER_PATTERN.finditer(text):
        sym = m.group(1).upper()
        if sym in TICKERS:
            found.add(sym)
    return sorted(found)


def _word_match(needle: str, haystack: str) -> bool:
    """True if needle appears as a whole word (or phrase) in haystack.
    Avoids 'putin' matching inside 'computing'."""
    return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract named entities (people/orgs/tickers) from text."""
    if not text:
        return {"people": [], "orgs": [], "tickers": []}
    text_l = text.lower()
    return {
        "people":  sorted({p for p in INFLUENCERS      if _word_match(p, text_l)}),
        "orgs":    sorted({o for o in HIGH_VALUE_ORGS  if _word_match(o, text_l)}),
        "tickers": extract_tickers(text),
    }


def finance_relevance(title: str, preview: str = "") -> tuple[bool, float, list[str]]:
    """Multi-signal relevance score. Returns (is_relevant, score 0-1, evidence).

    Scoring tiers:
      1. BAD keyword in title           → DROP   (0.00)
      2. Strong finance keyword         → KEEP   (0.70-1.00)
      3. Valid ticker symbol            → KEEP   (0.60-1.00)
      4. ≥2 finance keywords            → KEEP   (0.45-0.80)
      5. Influencer mentioned           → KEEP   (0.55-0.85)
      6. High-value org mentioned       → KEEP   (0.50-0.80)
      7. Innovation keyword             → KEEP   (0.45-0.75)
      8. Macro event                    → KEEP   (0.40-0.70)
      9. None of the above              → DROP   (0.00-0.30)

    Multi-signal bonus: if 2+ tiers match, add +0.10 (cap 1.0).
    """
    text = f"{title or ''} {preview or ''}".lower()
    title_l = (title or "").lower()

    # 1. Hard-fail on bad keywords (word-boundary match)
    for bad in BAD_KEYWORDS:
        if _word_match(bad, title_l):
            return (False, 0.0, [f"bad:{bad}"])

    evidence: list[str] = []
    score = 0.0
    tier_count = 0

    # 2. Strong finance keyword in title
    strong_matches = [kw for kw in STRONG_KEYWORDS if _word_match(kw, title_l)]
    if strong_matches:
        evidence.extend(f"strong:{kw}" for kw in strong_matches[:3])
        score = max(score, min(1.0, 0.70 + 0.10 * len(strong_matches)))
        tier_count += 1

    # 3. Ticker in title or preview
    tickers = extract_tickers(f"{title or ''} {preview or ''}")
    if tickers:
        evidence.extend(f"ticker:{t}" for t in tickers[:3])
        score = max(score, min(1.0, 0.60 + 0.10 * len(tickers)))
        tier_count += 1

    # 4. Finance keyword count
    fin_matches = []
    for kw in FINANCE_KEYWORDS:
        if _word_match(kw, text):
            fin_matches.append(kw)
            if len(fin_matches) >= 5:
                break
    if len(fin_matches) >= 2:
        evidence.extend(f"kw:{kw}" for kw in fin_matches[:5])
        score = max(score, min(0.80, 0.45 + 0.08 * len(fin_matches)))
        tier_count += 1

    # 5. Influencer mentioned
    inf_matches = [p for p in INFLUENCERS if _word_match(p, text)]
    if inf_matches:
        evidence.extend(f"person:{p}" for p in inf_matches[:3])
        score = max(score, min(0.85, 0.55 + 0.10 * len(inf_matches)))
        tier_count += 1

    # 6. High-value organization
    org_matches = [o for o in HIGH_VALUE_ORGS if _word_match(o, text)]
    if org_matches:
        evidence.extend(f"org:{o}" for o in org_matches[:3])
        score = max(score, min(0.80, 0.50 + 0.08 * len(org_matches)))
        tier_count += 1

    # 7. Innovation keyword
    inn_matches = [kw for kw in INNOVATION_KEYWORDS if _word_match(kw, text)]
    if inn_matches:
        evidence.extend(f"innov:{kw}" for kw in inn_matches[:3])
        score = max(score, min(0.75, 0.45 + 0.07 * len(inn_matches)))
        tier_count += 1

    # 8. Macro event
    macro_matches = [kw for kw in MACRO_EVENT_KEYWORDS if _word_match(kw, text)]
    if macro_matches:
        evidence.extend(f"macro:{kw}" for kw in macro_matches[:3])
        score = max(score, min(0.70, 0.40 + 0.05 * len(macro_matches)))
        tier_count += 1

    # Multi-signal bonus: corroborating evidence across tiers
    if tier_count >= 2:
        score = min(1.0, score + 0.10)
    if tier_count >= 3:
        score = min(1.0, score + 0.05)

    # Decision threshold
    if score >= 0.40:
        return (True, round(score, 3), evidence[:8])

    # Single weak match — drop
    if score > 0:
        return (False, round(score, 3), evidence[:3])
    return (False, 0.0, [])


def filter_items(items: list[dict], min_score: float = 0.40) -> list[dict]:
    """Filter pipeline items by relevance. Annotates with finance_score + entities."""
    kept = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = it.get("title", "")
        preview = it.get("preview", "")
        is_rel, score, evidence = finance_relevance(title, preview)
        if not is_rel or score < min_score:
            continue
        it["finance_score"] = score
        it["entities"]      = extract_tickers(f"{title} {preview}")
        kept.append(it)
    return kept


def cross_source_amplify(items: list[dict], boost_per_match: float = 0.05,
                          max_boost: float = 0.25) -> list[dict]:
    """When multiple sources mention the same entity, amplify all related items.

    If 3+ sources reference 'NVIDIA' in titles/previews, NVDA-related items
    across all sources get +0.15 to finance_score. Captures cross-source
    consensus = signal worth elevating.
    """
    from collections import defaultdict

    entity_sources: dict[str, set] = defaultdict(set)
    item_entities:  list[list[str]] = []

    for it in items:
        if not isinstance(it, dict):
            item_entities.append([])
            continue
        text = f"{it.get('title','')} {it.get('preview','')}".lower()
        ents = set()
        for o in HIGH_VALUE_ORGS:
            if _word_match(o, text):
                ents.add(f"org:{o}")
        for p in INFLUENCERS:
            if _word_match(p, text):
                ents.add(f"person:{p}")
        for t in extract_tickers(text):
            ents.add(f"ticker:{t}")
        item_entities.append(list(ents))
        src = it.get("source", "")
        for e in ents:
            entity_sources[e].add(src)

    # Entities mentioned by 3+ sources are amplified
    hot_entities = {e for e, srcs in entity_sources.items() if len(srcs) >= 3}

    for it, ents in zip(items, item_entities):
        if not isinstance(it, dict):
            continue
        hot_count = sum(1 for e in ents if e in hot_entities)
        if hot_count:
            boost = min(max_boost, boost_per_match * hot_count)
            it["finance_score"] = min(1.0, (it.get("finance_score") or 0.5) + boost)
            it["cross_source_boost"] = round(boost, 3)
            it["hot_entities"] = sorted(e for e in ents if e in hot_entities)[:5]

    return items
