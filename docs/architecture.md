# Architecture

## Design goals

- Delay-first responses with explicit source, cache age, and staleness metadata.
- Provider isolation: external PSX requests do not occur in API request handlers.
- Cache-backed reads: clients read normalized database records.
- Bulk collection: one market-watch request supplies all listed quotes.
- Failure isolation: retries and per-operation worker error handling.

## Runtime components

### API

The FastAPI application exposes typed `/v1` routes and compatibility routes. It
applies configured authentication, proxy-aware rate limiting, CORS, HEAD support,
input validation, and delay metadata. Health checks include a database probe and
latest market-fetch age.

### Worker

Each worker cycle fetches market-watch, indices, Regular-market totals, and sector
names. It persists the market snapshot and every parsed ticker. Symbols in
`MARKET_WATCHLIST` additionally receive intraday and EOD polling. Old quote rows
are pruned after each cycle.

### Provider

`PsxDpsProvider` normalizes public PSX Data Portal HTML and JSON into quote,
market, index, timeseries, and EOD objects. Temporary and parse errors are retried.
Sector names are a soft dependency and do not block quote refreshes.

### Storage

Async SQLAlchemy repositories store symbols, stock quotes, market snapshots,
history points, and EOD records. SQLite writes are batched. Initialization removes
duplicate quote timestamps and creates an idempotent unique index on
`stock_quotes(symbol, source_timestamp)`.

## Data flow

1. The worker requests public provider pages.
2. The provider validates and normalizes source payloads.
3. The service persists market, quote, history, and EOD records.
4. API routes query the database and attach delay metadata.
5. Consumers use `is_stale` and `cache_age_seconds` to evaluate freshness.

## Extension points

- Implement `StockMarketDataProvider` to support another upstream source.
- Add PostgreSQL for deployments requiring higher write concurrency.
- Add a cache in front of repository reads without coupling it to provider code.
- Add scoped authorization rules on top of the shared authentication dependency.
