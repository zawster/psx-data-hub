# Architecture

## Design goals

- Delay-first: expose only delayed market data in API responses.
- Source isolation: all external calls are in provider modules.
- Caching over live reads: user requests read DB-backed cached rows.
- Reliability: retrying, pruning, and background polling.

## Runtime components

- API (`psx_data_hub.main`)
  - FastAPI app
  - Rate limiting middleware
  - Read-only endpoints for quote/market/history/eod/indices
- Worker (`psx_data_hub.worker`)
  - Polls market + configured watchlist
  - Persists snapshots to SQLite/Postgres
- Provider (`psx_data_hub.providers`)
  - Scrape/parsing abstraction with configurable endpoints
- Storage (`psx_data_hub.storage`)
  - SQLAlchemy tables for symbols, quotes, market snapshot, history, EOD

## Flow

1. Worker calls provider
2. Provider normalizes raw payload into internal snapshot objects
3. Repo writes rows to DB
4. API reads rows and adds delay metadata

## Extension points

- Add alternate provider by implementing `StockMarketDataProvider`
- Add cache layer (Redis) in front of DB reads without changing providers
- Add auth or API keys per plan tiers
