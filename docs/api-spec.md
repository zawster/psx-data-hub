# psx-data-hub API specification

Version: `0.2.0`

The complete human-readable API and operations manual is the GitHub Pages-ready
site in [`index.html`](index.html). This Markdown file provides a compact endpoint
index for repository readers.

## Core v1

| Method | Path | Purpose |
|---|---|---|
| GET/HEAD | `/v1/health` | Database readiness and worker freshness |
| GET/HEAD | `/v1/status` | Lightweight service status |
| GET/HEAD | `/v1/market` | Latest market snapshot and parsed indices |
| GET/HEAD | `/v1/stocks` | Active symbol list |
| GET/HEAD | `/v1/stocks/symbols` | Alias of the symbol list |
| GET/HEAD | `/v1/stocks/{symbol}` | Latest cached quote |
| GET/HEAD | `/v1/stocks/{symbol}/description` | Identity, sector, and source metadata |
| GET/HEAD | `/v1/stocks/{symbol}/history` | Intraday or EOD time series |
| GET/HEAD | `/v1/stocks/{symbol}/eod` | Dedicated EOD records |
| GET/HEAD | `/v1/indices` | Latest index payload |

History accepts only `interval=int` or `interval=eod`. The optional `from` and
`to` values are ISO datetimes, and `limit` must be between 1 and 5000. EOD date
filters use `YYYY-MM-DD`.

## Compatibility API

| Method | Path | Purpose |
|---|---|---|
| GET/HEAD | `/` | Welcome response |
| POST | `/token` | OAuth2 password-form JWT issuance |
| GET/HEAD | `/token-check` | Bearer-token verification |
| GET/HEAD | `/volume` | Regular-market volume |
| GET/HEAD | `/status` | Regular-market state |
| GET/HEAD | `/tradesinstockmarket` | Regular-market trade count |
| GET/HEAD | `/totalcompanies` | Active symbol count |
| GET/HEAD | `/companiesinloss` | Negative-change company count |
| GET/HEAD | `/companiesinprofit` | Positive-change company count |
| GET/HEAD | `/sectors` | Company count by sector |
| GET/HEAD | `/sectorgraph` | Average change by sector |
| GET/HEAD | `/allindices` | Raw indices and delay metadata |
| GET/HEAD | `/getindex?symbol=KSE100` | One index by symbol |
| GET/HEAD | `/{company}/getalldata` | Compatibility quote view |
| GET/HEAD | `/{company}/description` | Compatibility identity view |
| GET/HEAD | `/{company}/equitydata` | Compatibility OHLCV view |

## Shared rules

- Symbols are uppercased and must match `[A-Z0-9._-]{1,20}`.
- Market-data routes honor `AUTH_MODE`: `off`, `api_key`, `jwt`, or `hybrid`.
- `/v1/health`, `/v1/status`, `/`, and `/token` are public.
- `/token-check` always requires a bearer token.
- GET routes support HEAD with an empty body and GET-equivalent headers.
- Cache-backed responses can be empty before the first successful worker cycle.
- Consumers should inspect `delay.is_stale`, `delay.cache_age_seconds`, and the
  configured data-source notice.

See [`index.html`](index.html) for parameters, examples, response fields,
authentication setup, errors, configuration, deployment, and GitHub Pages setup.
