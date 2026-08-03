# psx-data-hub

A public, open-source **Pakistan Stock Exchange** API with explicit **5-minute delayed** data.

## What it does

- Cached market data for delayed real-time usage.
- Stock endpoints: quote, company view, history, and EOD.
- Index endpoints.
- Optional legacy-style compatibility endpoints.
- Configurable auth: public/off, API key, JWT, or hybrid.

## Quick run

```bash
cd psx-data-hub
cp .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
uvicorn psx_data_hub.main:app --reload
```

```bash
psx-data-hub-worker
```

```bash
docker compose up --build
```

## API endpoints

### Core v1 (`/v1`)

- `GET /v1/health`
- `GET /v1/status`
- `GET /v1/market`
- `GET /v1/stocks`
- `GET /v1/stocks/symbols`
- `GET /v1/stocks/{symbol}`
- `GET /v1/stocks/{symbol}/history?interval=5m&from=...&to=...`
- `GET /v1/stocks/{symbol}/eod?from=...&to=...`
- `GET /v1/indices`

### Compatibility endpoints

- `GET /`
- `POST /token`
- `GET /token-check`
- `GET /volume`
- `GET /status`
- `GET /tradesinstockmarket`
- `GET /totalcompanies`
- `GET /companiesinloss`
- `GET /companiesinprofit`
- `GET /sectors`
- `GET /sectorgraph`
- `GET /{company}/getalldata`
- `GET/POST /{company}/description`
- `GET/POST /{company}/equitydata`
- `GET /allindices`
- `GET /getindex?symbol=KSE100`

## Delay metadata in responses

All delay-aware responses include:

- `delay.delay_minutes`
- `delay.source`
- `delay.source_timestamp`
- `delay.fetched_at`
- `delay.cache_age_seconds`
- `delay.is_stale`

## Auth

Set `AUTH_MODE`:

- `off`: no auth
- `api_key`: API key based
- `jwt`: token based
- `hybrid`: both

### JWT login example

```bash
curl -X POST "http://127.0.0.1:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo&password=demo"
```

Use `Authorization: Bearer <token>` for protected compatibility endpoints.

## Environment highlights

- `DATABASE_URL`
- `MARKET_WATCHLIST`
- `DELAY_MINUTES` (default: `5`)
- `POLL_INTERVAL_SECONDS`
- `PROVIDER_*`
- `AUTH_MODE`
- `API_KEYS`
- `LEGACY_USERS`
- `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_BURST`

## QA

```bash
$env:PYTHONPATH='src'
python -m pytest -q
```

### Development workflow

- `main` is production.
- Make all changes in `dev`.
- Open PRs from `dev` to `main`.

Docker smoke profile:

```bash
docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from smoke-check
```

## Notes

- No PSX license is shipped with this project.
- Endpoint parsing and formats may need adjustments if upstream pages change.
- This is designed for delayed/public-safe consumption patterns.

## License

MIT
