# Compliance and risk notes

This project is explicitly delayed-only by default. The following behavior is
required to reduce legal and operational risk:

1. Never claim live data status.
2. Keep `data_source_notice` explicit in all responses.
3. Require clear API terms for consumers (cache age, delay, source constraints).
4. Avoid exposing unauthenticated or abuse-friendly public endpoints.
5. Add monitoring for source page changes and parser failures.

## Known legal tension

Data redistribution rules can change. If you do not hold a licensed agreement,
assume you are in a restricted posture and:
- keep the data clearly delayed,
- avoid premium/guaranteed SLA claims,
- add strict usage policy terms to client onboarding.
