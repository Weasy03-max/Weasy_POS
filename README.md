# Weasy POS — Multi-purpose Business Edition

A Flask + SQLite point-of-sale starter for general retail, mini-markets, clothing, electronics, restaurants and other small businesses. Dark luxury interface, ZMW currency default, browser-based access.

## Features
- Admin/cashier login with hashed passwords and role checks
- Product catalogue, SKU/barcode lookup, stock levels and low-stock alerts
- Barcode scanner support (USB scanners that type a code and press Enter)
- Multi-item cart, quantity controls, discount, payment-method recording and change calculation
- Customer records
- Sale history, printable receipts and CSV export
- Seven-day sales chart
- Staff account creation
- SQLite local database

## Requirements
Python 3.10+.

## Run locally
1. Extract the ZIP.
2. Create and activate a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\\Scripts\\activate`
   - Linux/macOS: `python3 -m venv .venv` then `source .venv/bin/activate`
3. Install packages: `pip install -r requirements.txt`
4. Set a strong `SECRET_KEY` and `ADMIN_PASSWORD` environment variables before first launch.
5. Start: `python app.py`
6. Open `http://127.0.0.1:5000`

Default bootstrap account (only if environment variables are not set):
- Username: `admin`
- Password: `ChangeThisImmediately123!`

Change this immediately. The initial account is created only when the database has no matching admin username. For a new deployment, set `ADMIN_USERNAME` and a strong `ADMIN_PASSWORD` before the first run.

## Cloud deployment
Use a managed Python host that supports Flask and persistent storage. Set:
- `SECRET_KEY` to a long random secret
- `ADMIN_USERNAME` and `ADMIN_PASSWORD` to unique values
- `DATABASE_URL` to a persistent PostgreSQL URL for production (install a PostgreSQL driver and configure SQLAlchemy URL as required by your host)
- `COOKIE_SECURE=1` when HTTPS is enabled

Start command: `gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app`

Do not expose the development server directly to the public internet. Use HTTPS, backups, a managed database, and platform secrets. This starter does not include a card processor; Cash, Mobile Money, Card and Bank Transfer are recorded as tender types only. To actually charge cards or mobile money, integrate a compliant provider and never store card numbers or PINs.

## Important production hardening
Before handling real business transactions, add automated tests, database migrations, audit logging, backup/restore procedures, rate limiting, account lockout, password reset, per-business tenancy, stronger inventory concurrency handling, and a real payment-provider integration. Keep secrets out of source control.
# Weasy_POS
# Weasy_POS_complete-
