from .hackernews import fetch_hackernews
from .arxiv import fetch_arxiv
from .reddit import fetch_reddit
from .github_trending import fetch_github_trending
from .rss import fetch_rss
from .finance import fetch_finance
from .stackoverflow import fetch_stackoverflow
from .fred import fetch_fred
from .fear_greed import fetch_fear_greed
from .edgar import fetch_edgar
from .gdelt import fetch_gdelt
from .stocktwits import fetch_stocktwits
from .options import fetch_options
from .coingecko import fetch_coingecko
from .congress import fetch_congress
from .finra_short import fetch_finra_short
from .credit_spreads import fetch_credit_spreads
from .forex import fetch_forex
from .commodities import fetch_commodities
from .finnhub_news import fetch_finnhub_news

SOURCE_FETCHERS = {
    "hackernews":    fetch_hackernews,
    "arxiv":         fetch_arxiv,
    "reddit":        fetch_reddit,
    "github":        fetch_github_trending,
    "rss":           fetch_rss,
    "finance":       fetch_finance,
    "stackoverflow": fetch_stackoverflow,
    "fred":          fetch_fred,
    "fear_greed":    fetch_fear_greed,
    "edgar":         fetch_edgar,
    "gdelt":         fetch_gdelt,
    "stocktwits":    fetch_stocktwits,
    "options":       fetch_options,
    "coingecko":     fetch_coingecko,
    "congress":      fetch_congress,
    "finra":         fetch_finra_short,
    "credit":        fetch_credit_spreads,
    "forex":         fetch_forex,
    "commodity":     fetch_commodities,
    "finnhub":       fetch_finnhub_news,
}

# Finance-focused sources only — Bloomberg terminal scope
# Removed: stackoverflow (dev Q&A), github (general code repos)
# Kept (with finance filter): hackernews, reddit (only finance subs), arxiv (q-fin only)
ALL_SOURCES = [
    # Regulatory / primary sources (highest signal)
    "edgar", "congress", "finra", "fred", "credit",
    # Real-time finance news (Finnhub API)
    "finnhub",
    # Wire services + financial media
    "rss", "gdelt",
    # Market data (prices, snapshots, indicators)
    "finance", "forex", "commodity", "coingecko", "fear_greed",
    # Trading signals
    "options",
    # Community (with finance-only filtering)
    "reddit", "stocktwits", "hackernews",
    # Research
    "arxiv",
]

# Sources excluded from default but still callable explicitly
LEGACY_SOURCES = ["stackoverflow", "github"]

# Sources that produce actionable trade signals (not news)
SIGNAL_SOURCES = {"edgar", "options", "congress", "finra"}

# Sources that produce crypto market data
CRYPTO_SOURCES = {"coingecko"}

# Sources that produce institutional macro / credit data (not news)
MACRO_SOURCES = {"fred", "macro", "credit", "forex", "commodity"}

# Sources excluded from the main news feed
NON_FEED_SOURCES = {"finance", "fear_greed"} | MACRO_SOURCES | SIGNAL_SOURCES | CRYPTO_SOURCES
