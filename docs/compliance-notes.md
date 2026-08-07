# Compliance and risk notes

This project uses a cache-backed public-data model. The following behavior is
required to reduce legal and operational risk:

1. Never claim exchange-grade real-time data status.
2. Keep `data_source_notice` explicit in all responses.
3. Require clear API terms for consumers (cache age, delay, source constraints).
4. Avoid exposing unauthenticated or abuse-friendly public endpoints.
5. Monitor source page changes, parser failures, and worker freshness.

## Known legal tension

Data redistribution rules can change. If you do not hold a licensed agreement,
assume you are in a restricted posture and:
- state data timing and freshness clearly,
- avoid premium/guaranteed SLA claims,
- add strict usage policy terms to client onboarding,
- obtain independent legal review before commercial redistribution.

The repository is licensed under the MIT License. That software license does
not grant rights to third-party market data or PSX trademarks.
