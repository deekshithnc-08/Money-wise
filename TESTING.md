# Verification record

Verified locally on 29 October 2026:

- Seven isolated Python integration tests passed (`python3 -m unittest discover -s tests -v`).
- Browser: generated a name-only referral link, opened that link with flyer attribution, submitted a booking, signed into admin, verified the participant/referrer mapping, recorded a synthetic INR 2,500 payment and confirmed updated revenue and paid-referral metrics.
- Desktop: reviewed landing page and populated dashboard.
- Mobile: reviewed at 390 × 844; landing page document width equals viewport width (no horizontal page overflow). Admin layout stacks; data tables scroll horizontally.
- Test records and local preview administrator removed after testing.
- Twilio delivery was mocked, not exercised against a live account.
- Docker deployment was documented but not run locally; no Docker host/domain was provisioned.
- No online payment gateway is included or tested; payments are offline records.

Screenshot evidence is in the local, Git-ignored `previews/` directory.

## Vercel verification — 29 October 2026

- 15 integration tests passed with Python 3.12: original SQLite tests, the same tests through the libSQL adapter, and rejection of ephemeral storage on Vercel.
- Live Turso test verified persistence across independent connections and transaction rollback.
- Live Vercel domain returned HTTP 200 for the landing page and configuration endpoint.
- Live end-to-end test passed: unauthenticated admin denial, unique referral generation with the production domain, booking creation, admin sign-in, participant/referrer/source mapping, recorded payment and referral revenue, and logout.
- Synthetic production test records were removed by their exact IDs; real data was not modified.
- Browser confirmed the public landing page renders correctly. Evidence: local `previews/vercel-live.jpg`.
