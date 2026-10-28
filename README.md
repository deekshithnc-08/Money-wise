# Money Wise Women · myPAL

A working, responsive programme landing page and private booking/referral dashboard. The supplied programme poster is included unchanged as the design and content reference. No repository has been pushed and no hosted service has been provisioned.

## Run locally

Requires Python 3.9+ (3.12 recommended). No third-party Python or JavaScript dependencies, build step or package install is required.

```sh
cp .env.example .env
python3 server.py create-admin --email your-email@example.com
python3 server.py
```

Choose a unique admin password of at least 12 characters at the hidden prompt. There is no default account or password. Open **http://localhost:8000** and **http://localhost:8000/admin**. Use `localhost` consistently: the write API checks the exact `PUBLIC_URL` origin, including the port. To use `127.0.0.1`, change `PUBLIC_URL` first. Stop with Ctrl+C.

The app reads `.env` automatically; process environment takes precedence. Restart after changing backend code or configuration. Data persists in `data/app.sqlite3` across restarts. It is excluded from Git. Changing or recreating the admin with the same command revokes their active sessions.

## What works

- Responsive landing page, original flyer, five-session curriculum, booking request form and privacy notice.
- Self-service unique referral URLs by name, copy button and WhatsApp share link. No booking required to refer.
- Optional real SMS verification using Twilio Verify. With all three credentials configured, verification is required for referral generation. Verified numbers recover their existing referral code; one-time verification tokens expire after ten minutes and are consumed on use.
- Without SMS configuration, links are labelled **unverified**. Names do not identify unique people; duplicate names and unverified numbers can create different links. Save the returned URL. Phone-only recovery is intentionally unavailable without verified ownership.
- SQLite-backed bookings, referrers, visitor attribution, payment records and administrator activity logs.
- Private dashboard with unique browser visitors, page visits, requests, paid count, recorded revenue, referral performance, participant/referrer mapping, campaign/partner/source labels and searchable/filterable bookings.
- Admin booking and payment updates, receipt/refund references, CSV export, durable audit history.
- Password hashing (PBKDF2-SHA256, 600,000 rounds), expiring server-side sessions, HttpOnly/SameSite cookies, HTTPS Secure cookies, origin checks, CSRF protection for admin mutations, input validation, request-size limits, throttling, SQL parameters, output escaping and CSV formula neutralisation.
- Local assets and system fonts; no analytics SDKs or external font requests.

## Booking and payment model

This version accepts **requests**, not guaranteed seat reservations. The flyer has no dates, venue, capacity or price, so none have been invented. Set the batch, dates, venue and fee label in `.env` when known. The booking flow has one configured upcoming cohort.

Booking statuses: `requested`, `contacted`, `confirmed`, `cancelled`.
Payment statuses: `pending`, `paid`, `failed`, `refunded`.

Admins record payments made outside the site after checking receipts. Paid/refunded records require a positive amount and reference. Amounts are stored as integer **paise**, displayed as INR. Revenue and successful referral metrics include only records currently marked paid. Refunded entries exclude the full amount; **partial refunds are not supported**. Changing a payment status does not move money. Booking status and payment status are independent, so cancelling a paid booking does not silently refund it.

No online gateway, automated email/SMS booking confirmation, WhatsApp API messaging, commissions, inventory limits or attendee portal is included. WhatsApp sharing opens a draft only; it does not send automatically. Adding checkout later requires server-created orders, verified signed gateway webhooks, idempotency, amount/currency checks and reconciliation; do not trust browser payment success callbacks.

Repeated requests for the same normalised phone and active batch return a generic acknowledgement, without exposing any existing booking ID or personal information. Unverified mobile submissions cannot prove identity, so administrators must confirm contact before confirming seats.

## Attribution rules and links

Replace the example host with your actual `PUBLIC_URL` after deployment:

| Purpose | URL |
| --- | --- |
| Public booking page | `https://your-domain.example/` |
| Flyer QR target | `https://your-domain.example/?src=flyer` |
| Instagram campaign | `https://your-domain.example/?utm_source=instagram&utm_campaign=launch` |
| Partner campaign | `https://your-domain.example/?src=partner&partner=COLLEGE01` |
| Referral generator | `https://your-domain.example/refer` |
| Personal referral | `https://your-domain.example/?ref=MW…` |
| Admin | `https://your-domain.example/admin` |

- First valid referral stays for 30 days. A later referral does not replace it until expiry. The visitor can explicitly remove referral attribution when submitting a booking.
- Latest explicitly supplied source, campaign and partner values are retained separately. A direct visit does not erase previously tagged values. These campaign parameters are self-reported attribution, not independently verified identities.
- Invalid referral codes do not receive credit. Matching referrer/participant mobile numbers are excluded from referral credit. Name-only referrals cannot reliably prevent self-referral.
- Forwarding the same personal URL still credits its original owner. The site cannot identify private WhatsApp forwarding chains. Each sender must share their own generated link to get credit.
- Each page load creates one visit event; unique visitors are unique first-party browser cookies, not people. Clearing cookies, switching devices, bots and repeat visits affect these counts. No person is identified until they submit a form.
- Referrer names are displayed publicly on their links. Mobile numbers and participant data are not.
- No separate lead capture before form submission; each valid booking request is a lead.

## SMS verification

Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_VERIFY_SERVICE_SID`, then restart. Enable SMS for the intended countries in your Twilio account and validate delivery with a test phone before launch. Twilio billing, account approval and delivery remain external prerequisites. No SMS has been sent during development. Tests mock the provider; live provider delivery is not verified.

Implementation follows the official [Verifications API](https://www.twilio.com/docs/verify/api/verification) and [Verification Check API](https://www.twilio.com/docs/verify/api/verification-check). All secrets stay server-side. Without credentials, the server never claims a mobile number is verified.

## Test

```sh
python3 -m unittest discover -s tests -v
```

The integration suite starts an isolated local server and temporary database. It tests referral ownership/expiry, source tracking, self-referral exclusion, duplicate handling, consent and input validation, authentication, CSRF, logout, payment/refund metrics, audit records, verified-mobile recovery, throttling, CSV safety, persistence and private file isolation. The Twilio provider is mocked.

## Deploy

See [DEPLOYMENT.md](DEPLOYMENT.md) for a Docker + HTTPS reverse-proxy deployment, persistent storage, backups and launch configuration. This app requires a long-running Python process and writable persistent disk. GitHub Pages/static-only hosting will not run the backend. Run a **single instance** against the SQLite database; do not put the database on a shared network filesystem or ephemeral container disk.

## GitHub preparation

Included: source, original flyer, `.gitignore`, `.env.example`, Dockerfile, deployment guide and GitHub Actions tests. No secrets, database, real contacts or test administrator passwords should be committed. There is no chosen license; the supplied brand/flyer remains the owner's asset.

Review before publishing:

```sh
git status --short
git diff --check
git add server.py public tests README.md DEPLOYMENT.md TESTING.md .env.example .gitignore .dockerignore Dockerfile compose.yaml Caddyfile .github data/.gitkeep
git diff --cached --stat
git commit -m "Build Money Wise Women booking and referral platform"
```

Only after explicit owner approval: create/select a GitHub repository, add its remote, and push. **Do not push as part of setup.**

## Layout

- `server.py`: HTTP routing, authentication, SQLite schema, attribution, SMS verification and reporting.
- `public/`: landing page, admin dashboard, privacy page, CSS, browser scripts and original flyer.
- `tests/test_app.py`: isolated backend integration tests.
- `data/`: local runtime database; intentionally ignored.

## Practical limits

This is a compact, single-instance application for an initial programme launch. Use a managed HTTPS reverse proxy in front of the Python server, keep Python patched, restrict network exposure, monitor logs and maintain backups. The built-in per-IP limiter sees the proxy's IP when proxied and may therefore throttle users collectively; add trusted edge-level rate limiting or a carefully validated proxy identity layer before a broad campaign. It deliberately ignores untrusted `X-Forwarded-For` headers. The backend is not a multi-region/high-throughput platform.

Before collecting public registrations, fill in the actual programme details, add the designated privacy contact and retention policy to `public/privacy.html`, create a production admin, and complete the launch checks in the deployment guide.
