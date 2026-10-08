# BorrowHub BD - peer-to-peer rental marketplace (Django 5)

> Kenar dorkar nei, proyojon hole rent nao; ar unused jinish pore na rekhe income koro.

Owners list items (projector, DSLR, mic, tripod, speaker, laptop, console, event gear). Renters rent them nearby by the day.
BorrowHub manages **connection, booking, payment, security deposit, delivery/return** and earns a **commission on every completed rental**.

## Run locally (Windows / macOS / Linux)

```bash
python -m venv venv
venv\Scripts\activate              # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # optional: categories, 12 sample listings, demo users
python manage.py createsuperuser   # your admin login
python manage.py runserver
```
Site: http://127.0.0.1:8000 · Admin: http://127.0.0.1:8000/admin/
Demo logins (password `demo12345`): owners `rahim`, `nusrat`, `tanvir`; renter `renter`.
No configuration is needed locally: DEBUG is on and SQLite is used.

## What's production-ready

| Area | What you get |
|---|---|
| Config | Everything via environment variables (`.env.example`). The app refuses to start in production with a weak/missing `DJANGO_SECRET_KEY`. |
| Security | HTTPS redirect, HSTS, secure/HttpOnly/SameSite cookies, nosniff, frame deny, referrer + permissions policies. `check --deploy` passes with no warnings. |
| Login protection | Failed-login lockout per username+IP (site **and** admin), rate limits on sign-up and the contact form. Set `REDIS_URL` so limits are shared across workers. |
| Admin | Configurable admin URL (`DJANGO_ADMIN_URL`) to avoid bot probing. |
| Private files | NID photos are stored outside public media and downloadable by staff only (`/private/...`). |
| Images | Uploads are auto-rotated, downscaled (max 1600 px) and recompressed. |
| Data integrity | Row locks stop double-booking / double-accepting under concurrency (PostgreSQL), DB constraints, atomic money operations. |
| Performance | Template caching, persistent DB connections, hashed + gzip static files with 1-year cache, self-hosted Bootstrap/icons/fonts (no CDN). |
| Ops | `/healthz/` probe, structured logging, admin error emails (`DJANGO_ADMIN_EMAILS`), optional Sentry, `robots.txt`, `sitemap.xml`. |
| Email | Optional notification emails (`EMAIL_NOTIFICATIONS=1` + SMTP). |
| Delivery | `Dockerfile`, `docker-compose.yml` (Postgres + Redis + gunicorn + nginx + hourly scheduler), `Procfile`, GitHub Actions CI. |
| Tests | 29 tests: pricing, full lifecycle, disputes, permissions, search, admin pages, throttling, private files, image resize, email, health/sitemap. |

## Deploy with Docker (recommended)

```bash
cp .env.example .env     # fill DJANGO_SECRET_KEY, POSTGRES_PASSWORD, domain, SMTP
# first plain-HTTP test only:  DJANGO_SSL_REDIRECT=0 and DJANGO_SECURE_COOKIES=0
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```
* Put HTTPS in front (Cloudflare, Caddy, or certbot on nginx). Whatever terminates TLS must send `X-Forwarded-Proto: https`. Then set `DJANGO_SSL_REDIRECT=1` and `DJANGO_SECURE_COOKIES=1`.
* The `scheduler` service runs `expire_bookings` hourly (cancels unanswered/unpaid requests, auto-accepts silent inspections).
* Backup: `docker compose exec db pg_dump -U borrowhub borrowhub > backup.sql`, plus the `media` and `private_media` volumes.

### Without Docker (VPS / PaaS)
```bash
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=yourdomain.com \
       DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com DATABASE_URL=postgres://user:pass@host/db
python manage.py migrate && python manage.py collectstatic --noinput
gunicorn config.wsgi:application -c gunicorn.conf.py
```
Add a cron entry: `0 * * * * cd /app && python manage.py expire_bookings`. Serve `/media/` with nginx (or set `DJANGO_SERVE_MEDIA=1` for small sites). gunicorn does not run on Windows; use Docker/WSL there.

## Go-live checklist (business side)
1. Admin > **Site settings**: turn **OFF "auto verify payments"** (demo mode trusts any TrxID), set your real bKash/Nagad/Rocket numbers and commission %.
2. Replace the placeholder Terms page with lawyer-reviewed text.
3. For automatic payments, integrate the bKash/Nagad/SSLCommerz API in `bookings/services.submit_payment`.
4. Upgrading an existing install? Run `python manage.py migrate`, then move old NID files from `media/nid/` to `private_media/nid/`.

## Rental lifecycle

`Request > Owner accepts > Renter pays > Handover > On rent > Return & inspection > Completed (+ reviews)`

| Step | Who | What happens |
|---|---|---|
| Request | Renter | Picks dates + pickup/delivery. Price snapshot is stored (rent, delivery, deposit, commission %). |
| Accept | Owner | Dates are blocked. Renter has `payment_window_hours` to pay. |
| Pay | Renter | Sends rent + delivery + deposit to BorrowHub's number and enters the TrxID. |
| Verify | Staff / auto | Admin action "Verify selected incoming payments". Booking becomes **Paid**. |
| Handover / Return | Owner | Marks handed over, later records return with optional damage deduction. |
| Inspection | Renter | Accepts or disputes a deduction. Silence = accepted after `inspection_window_hours`. |
| Completion | System | Creates a **payout** to the owner (rental + delivery - commission + deductions) and a **refund** of the remaining deposit. |
| Settle | Staff | Admin action "Mark selected payouts/refunds as SENT" after you send the money. |

## Admin panel
Dashboard (commission, GMV, held deposits, items needing attention), users + NID verification, listings moderation, bookings, payments (verify / mark sent / CSV), disputes, singleton Site settings.

## UI & motion
Scroll-reveal with stagger, hero entrance + floating rent tags, category ticker, count-up stats, card hover lift + image zoom, button ripple + loading spinners on submit, animated stepper, live price tween, scroll progress bar, auto-dismissing alerts. All animation switches off for visitors with *reduce motion* enabled, and content stays visible if JavaScript fails.

## Layout
```
config/     settings (env-driven), urls
core/       site settings, notifications, security helpers, healthz/robots/sitemap, admin dashboard, commands
accounts/   custom User, auth (throttled), dashboard, public profile
listings/   categories, listings, photos, search, favorites
bookings/   bookings, payments, disputes, reviews, services.py (all business rules)
deploy/     nginx.conf, entrypoint.sh      static/  css (main + motion), js, vendor (self-hosted)
```
Run tests: `python manage.py test`
