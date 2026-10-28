# Deployment and operations

## 1. Prepare the programme

Confirm the public domain, batch name, dates, venue, fees and booking policy with myPAL. The current application records booking requests and offline payments only. Publish a designated privacy contact and retention period in `public/privacy.html` before collecting real contacts. Review the consent wording and ownership/use rights for the supplied flyer.

## 2. Local setup

```sh
cp .env.example .env
python3 server.py create-admin --email your-email@example.com
python3 server.py
```

Visit http://localhost:8000 and http://localhost:8000/admin. There is no bundled admin password. Keep `.env`, the database, backups and admin credentials out of Git.

## 3. Single-host Docker deployment with HTTPS

The included `compose.yaml` runs the application behind Caddy and persists SQLite in a named volume. Install Docker with Compose on your hosting machine. Point a domain's DNS to it and allow incoming TCP 80/443. Do not expose port 8000 publicly.

Set `.env` with real values, including:

```dotenv
PUBLIC_URL=https://moneywise.your-domain.example
DOMAIN=moneywise.your-domain.example
PROGRAMME_BATCH=Your actual cohort name
PROGRAMME_SCHEDULE=Your actual dates
PROGRAMME_VENUE=Your actual venue
PROGRAMME_FEE_LABEL=Your actual fee and inclusions
```

`PUBLIC_URL` must exactly match the public origin, with no trailing path. The default deployment is at the domain root, not under `/money-wise` on an existing website. Redirect alternate hostnames to the canonical host at the proxy. Keep HTTPS enabled; it activates Secure cookies and HSTS.

```sh
docker compose up -d --build
docker compose exec app python server.py create-admin --email your-email@example.com
docker compose logs --tail=100
```

Caddy provisions certificates for the configured domain. Use the host's secret management for Twilio credentials if available. The named data volume survives app restarts/rebuilds; **never run `docker compose down -v` against production** unless intentionally deleting the database.

The app binds only inside the container network. The proxy terminates TLS and forwards traffic to the application. This lightweight server is suitable for a controlled pilot behind a proxy; perform load/security review before a broad public campaign. Set an appropriate edge firewall/rate limiter. The included application rate limiter uses the direct peer address, which is Caddy behind this proxy, so limits are shared there. Do not blindly accept arbitrary forwarded IP headers to bypass this constraint.

## 4. Verify before sharing

1. Load the public page on desktop and mobile; verify programme information and all local assets.
2. Generate a referral; open it in a fresh browser. Confirm the displayed referrer name.
3. Submit a clearly labelled test request with a phone you control; check name, referrer and source in the admin dashboard.
4. Record a test offline payment with a reference; check revenue/referral totals. Record a full refund; check both totals decrease.
5. Sign out; confirm the dashboard and CSV endpoint deny access.
6. If SMS is enabled, verify actual delivery and that the same verified number retrieves the same link. Also test expired/wrong codes.
7. Restart the container; ensure the record persists. Back up and restore into a staging instance.
8. Remove only your labelled test records using a reviewed database operation before launch, or retain them in a separate staging database. Do not use the real database for automated tests.
9. Generate the flyer QR against the **deployed** URL `https://your-domain.example/?src=flyer`. Localhost links work only on the machine running the app.

## 5. Backups and restore

SQLite runs in WAL mode. Use SQLite's backup API for a consistent live snapshot; do not copy just the `.sqlite3` file while writes are active.

```sh
docker compose exec app python -c 'import sqlite3; source=sqlite3.connect("/app/data/app.sqlite3"); target=sqlite3.connect("/app/data/backup.sqlite3"); source.backup(target); target.close(); source.close()'
```

Copy the snapshot to protected off-host storage with your normal backup process, encrypt it, restrict access and apply the retention policy. Schedule backups according to acceptable data loss (daily for an initial pilot). To restore, stop the app, preserve its current database and WAL/SHM files, restore the snapshot as `app.sqlite3` with the correct ownership, remove obsolete WAL/SHM files from the stopped instance, then start and verify. Test this procedure on staging first.

## 6. Admin and privacy operations

- Create one account per team member with `create-admin`; never share passwords.
- Reset an admin password with the same command; active sessions for that email are revoked.
- To revoke access completely, delete that admin and their sessions through a reviewed database operation.
- CSV exports contain personal information. Store them only in approved, access-controlled locations.
- Apply your retention schedule to bookings, referral contacts, visit records, audit history and backups. There is no automatic retention job or public account-deletion endpoint in this version.
- Audit records contain previous payment states and administrator email. Restrict database access along with dashboard access.
- Monitor HTTP/proxy errors, disk space and backups. Application logs intentionally omit query strings and form data.

## 7. Changes and growth

Run the tests before deploying. Back up before schema changes. Current schema creation is idempotent; future schema changes need explicit migrations. For multiple app instances or higher traffic, move to PostgreSQL, a production application server/framework, trusted proxy-aware rate limiting and managed job processing before scaling out. Online payment collection and automated programme notifications are separate integrations.

## 8. GitHub

The repository is prepared locally with source, tests and CI. Review the staged files, then commit. Add a GitHub remote and push **only after explicit user approval**. Deploying to a host also requires choosing that host/domain and supplying production credentials; none are provisioned by this project.
