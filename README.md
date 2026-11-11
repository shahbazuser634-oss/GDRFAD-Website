# GDRFAD private visa-assistance portal

A starter full-stack Flask application with SQLite, customer accounts, private document uploads, application references, public reference tracking, an admin dashboard, status changes, payment records/printable receipts, and authority-verified visa PDF release.

## Run locally

1. Install Python 3.10+.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set strong secrets. (This starter does not automatically load `.env`; export those variables in your shell or use a production process manager that loads them.)
5. Run: `python app.py`
6. Open `http://127.0.0.1:5000`

On first run, an admin account is created from `ADMIN_EMAIL` and `ADMIN_PASSWORD`. If unset, the development defaults are `admin@gdrfad.local` / `ChangeThisAdmin123!`. Change these immediately and never deploy with defaults.

## Included routes

- `/` home
- `/services` services listing and search
- `/services/tourist-visa`, `/services/visit-visa`, `/services/transit-visa`
- `/register`, `/login`, `/logout`
- `/apply` authenticated application form
- `/dashboard` customer application history
- `/track` reference-number tracking
- `/admin` admin dashboard
- `/receipt/<id>` printable GDRFAD payment record

## Important production work still required

This is a working development foundation, not a production-ready immigration system. Before accepting real passport data or taking payments:

- Replace SQLite with managed PostgreSQL and add migrations/backups.
- Add CSRF protection, rate limiting, login lockout/MFA, audit logs, session expiry, password reset and email verification.
- Add malware scanning, MIME/content inspection, encryption at rest, private object storage, retention/deletion policy and secure backups for uploaded identity documents.
- Add actual email/SMS providers and delivery logging; currently no notifications are sent.
- Integrate a PCI-compliant hosted payment provider; currently payments are manual admin records only, no card data is collected.
- Add Arabic translations and RTL layout; this starter currently ships in English only.
- Add privacy policy, terms, consent records, data access/deletion workflow and legal review for jurisdictions served.
- Deploy behind HTTPS with secure cookies, production WSGI server, firewall, monitoring and least-privilege admin accounts.
- Verify official visa documents independently before upload; the checkbox is an admin workflow reminder, not an automated authenticity check.
- Have a qualified security engineer test the complete system before production.

GDRFAD is presented as an independent private service provider. It is not affiliated with GDRFA or any government authority and does not issue visas or guarantee approval. Do not use government logos, seals, official-looking identifiers, or wording that implies government affiliation.


## Public demo deployment (Render)

1. Push this folder to a GitHub repository (do not upload a real `.env` file or real customer documents).
2. In Render, create a new **Web Service** connected to that repository. Set the root directory to `gdrfad-portal` if the repository contains the parent folder.
3. Set the build command to `pip install -r requirements.txt` and the start command to `gunicorn --workers 1 --bind 0.0.0.0:$PORT app:app`. The included `Procfile` provides the same start command on platforms that read it.
4. Add environment variables: `SECRET_KEY` (a long random secret), `ADMIN_EMAIL` (your admin email), `ADMIN_PASSWORD` (a unique strong password), `COOKIE_SECURE=1`, and `FLASK_DEBUG=0`. Never use the development defaults.
5. The app stores its SQLite database and uploaded files in `DATA_DIR`. For any persistent test deployment, attach a persistent disk and set `DATA_DIR` to that disk's mount path (for example `/var/data`). Without persistent storage, redeploys/restarts may erase uploaded files and database contents.
6. After deployment, test only with dummy accounts and dummy documents. Share the generated `https://...onrender.com` URL.

**Important:** This package is prepared for a public demonstration, not approval for handling real passports, identity photos, payments, or immigration applications. The current app still needs the security and privacy work listed above (including CSRF protection, file-content validation/malware scanning, encryption, access logging, secure backups, and legal review). GDRFAD must remain clearly identified as an independent private service, not a government website or visa issuer. Do not collect real identity documents until qualified security and legal review is complete.
