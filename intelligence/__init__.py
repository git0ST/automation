"""Intelligence layer — market routing, regime/risk classification.

Marks `intelligence` as a proper package so `from intelligence.market_router
import classify_ticker` resolves reliably under the pipeline's sys.path (it was
a namespace package before, which failed to import in the cron runtime).
"""
