# Vercel deployment

The application now supports Vercel Python Functions with persistent Turso Cloud SQLite storage. It never stores production bookings in `/tmp` or the deployment filesystem.

## Required configuration

- Runtime: Python 3.12, installed from `requirements.txt`.
- Framework preset: Other (the checked-in `vercel.json` supplies routing).
- Build command: none. Leave the output directory at its default.
- Region: Mumbai (`bom1`).
- Connect the dedicated Turso database to the Vercel project. The integration sets `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` as server-side secrets.
- `PUBLIC_URL`: the final production HTTPS origin. If omitted, the app uses Vercel's `VERCEL_PROJECT_PRODUCTION_URL`.
- Programme and optional Twilio environment variables are documented in `.env.example`.

Import the GitHub repository into Vercel, connect Turso, and deploy. A missing database configuration fails closed with a setup message rather than creating disposable storage. The first function invocation creates the schema idempotently. Production uses the remote primary; no local replicas are involved.

The Python function serves the existing routes through a rewrite. Sessions, rate limits, bookings and referrals all live in Turso, so they work across function instances. On Vercel only, client throttling uses the edge's `x-vercel-forwarded-for` header. Other hosts continue to use the direct peer address.

## Admin account

Install requirements locally with Python 3.12 and supply the same Turso environment variables through a private `.env` or your shell's secret manager. Then run:

```sh
python server.py create-admin --email your-email@example.com
```

The password is collected at a hidden prompt. This writes only a salted hash to the remote database. Do not add a public setup endpoint or put an admin password in frontend code. Repeating the command resets that account and revokes its sessions.

## Validation

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The suite exercises both standard SQLite and the libSQL adapter, plus Vercel's refusal to use ephemeral storage. Check the live booking form, referral attribution, admin sign-in and reporting after deployment. Test data must be clearly labelled and removed by its exact IDs after verification.

The existing local/Docker setup still uses `data/app.sqlite3` unless Turso environment variables are supplied. Local preview records are not automatically migrated to the production database. Use a reviewed migration if those records must be retained.

For backups and recovery on Vercel, use Turso's database backup/recovery facilities and verify the retention included with your selected plan. The Docker file-copy instructions do not apply to Turso.
