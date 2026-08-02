# API Spec (v1)

## Base path

`/v1`

## GET /health

Simple service check.

## GET /status

Service is running status payload.

## GET /market

Returns latest market snapshot with delayed metadata.

Response fields:
- `fetched_at`: timestamp when API wrote last snapshot
- `source_timestamp`: source update time if available
- `delay`: shared delay metadata
- `payload`: raw parsed payload from provider
- `indices`: parsed index points

## GET /stocks or /stocks/symbols

Returns symbols managed by the system.

## GET /stocks/{symbol}

Returns latest delayed quote for symbol.

## GET /stocks/{symbol}/history

Query params:
- `interval` (`5m`, `1d`, etc)
- `from` and `to` timestamps for range

## GET /stocks/{symbol}/eod

Query params:
- `from` date
- `to` date

## GET /indices

Returns last seen index payload.

## Legacy/compatibility endpoints (root)

`/`  
Welcome message

`POST /token`  
OAuth2 token endpoint (`application/x-www-form-urlencoded`, fields: `username`, `password`)

`GET /token-check`  
Protected endpoint to verify bearer token

`GET /volume`  
Total market volume snapshot

`GET /status`  
Market status snapshot

`GET /tradesinstockmarket`  
Trade count snapshot

`GET /totalcompanies`  
Total active listed companies/symbols

`GET /companiesinloss`  
Number of latest quotes with negative change

`GET /companiesinprofit`  
Number of latest quotes with positive change

`GET /sectors`  
Sector summaries

`GET /sectorgraph`  
Sector-level aggregate metrics

`GET /allindices`  
All index points from latest market payload

`GET /getindex?symbol=`  
Get index by symbol

`{company}` endpoints  
`GET/POST /{company}/getalldata`, `/{company}/description`, `/{company}/equitydata`
