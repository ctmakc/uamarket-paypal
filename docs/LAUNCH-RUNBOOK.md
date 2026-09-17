# UA Market launch runbook (one page)

Server: Linux with Docker Compose 2.24+, ports 80 and 443 open. `P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"`.
Decisions and their settings: `docs/OWNER-ACTIONS.md`. Laptop rehearsal of all of this: `scripts/prod_local_check.sh --down`.

**1. DNS.** An A (and AAAA) record for the shop's domain points at the server. Caddy asks Let's Encrypt for the certificate on first start.

**2. Env file and secrets.** `git clone <repo> uamarket && cd uamarket && cp .env.example .env`, then in `.env`:
- `openssl rand -hex 32` once each for `POSTGRES_PASSWORD`, `INTERNAL_PROXY_SECRET`, `OPERATOR_API_KEY`, `ADMIN_API_KEY`.
- `python3 tools/admin_password_hash.py` prints `ADMIN_PASSWORD_HASH` and `ADMIN_SESSION_SECRET`.
- `SHOP_DOMAIN=<domain>`, `WEB_BASE_URL=https://<domain>`, `CADDY_TLS=` (empty).
- Mail: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_SECURITY=starttls`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` on the domain (replace the Mailpit values).
- Payments: `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` and/or `ETRANSFER_EMAIL`. `PAYMENT_PROVIDER` stays empty.
- Owner answers from OWNER-ACTIONS A and B. Keep `SHOP_CATALOGUE_STATUS=` empty and `WEB_INDEXABLE=false` for now.
- Check: `$P config -q` prints nothing.

**3. Start.** `$P up -d --build`. The API applies database migrations itself (`alembic upgrade head`) before it starts. `$P ps` shows db, app, web, scheduler, caddy, backup running; open `https://<domain>`: the demo strip is at the top.

**4. Stripe.** In the Stripe dashboard add the endpoint `https://<domain>/webhooks/stripe` for `checkout.session.completed` and `checkout.session.expired`; its signing secret is `STRIPE_WEBHOOK_SECRET` (then `$P up -d`).

**5. Catalogue.** Sign in at `https://<domain>/admin`. Import the sourcing sheet (Import, dry run, apply; `docs/catalogue-import.md`), add photos with alt text in both languages, receive stock, put products on sale. No products yet and want to test first: `$P exec app python -c "import urllib.request as u,os; print(u.urlopen(u.Request('http://127.0.0.1:8000/admin/seed-catalog', method='POST', headers={'x-api-key': os.environ['ADMIN_API_KEY']})).read())"` loads the demo catalogue with stock.

**6. Test order while still in demo mode.** Buy one item on the site in a private window (tick the terms, place the order). The order page opens at `/order/<number>` and the "order received" email arrives. In `/admin` the order is in the queue (Awaiting payment, or To pack once paid): open it, "Cancel this order" with a reason. Demo orders ask for no money.

**7. Go live, deliberately.** Remove the demo products in `/admin` (Retire) if any were loaded. Set `SHOP_CATALOGUE_STATUS=live`, `$P up -d`. The demo strip disappears. Place one real order with a real card for the cheapest item, check it appears as paid in `/admin` and in Stripe, then refund it in the Stripe dashboard and cancel it in `/admin` with the reason "launch test". Only then set `WEB_INDEXABLE=true` (and `SEO_USE_PROPOSED_TITLES=true` if approved), `$P up -d`.

**8. Backups.** Nightly at `BACKUP_HOUR_UTC` the `backup` service writes a database dump and a photo archive to the `backups` volume and keeps `BACKUP_KEEP_DAYS` (14). Check once now:
`$P exec backup sh /scripts/pg-backup.sh now` then `scripts/backup/restore.sh <uamarket-….dump>` (restores into the scratch database `restore_check` and prints order and product counts). Copy the volume off the server weekly: `docker run --rm -v uamarket_backups:/b -v "$PWD":/o alpine tar czf /o/backups.tgz -C /b .` (volume name: `docker volume ls | grep backups`).

**9. Rollback.** Code: `git checkout <previous commit>` and `$P up -d --build`. Data: stop writers `$P stop app web scheduler`, then `scripts/backup/restore.sh <dump> heritage`, then `$P up -d`. Photos: untar the matching `media-….tar.gz` into the `media_data` volume. Take a fresh `pg-backup.sh now` before any restore into `heritage`.

**Laptop rehearsal of steps 2–6.** Same commands with `SHOP_DOMAIN=localhost`, `CADDY_TLS=tls internal`, `CADDY_HTTP_PORT=18080`, `CADDY_HTTPS_PORT=18443`, `WEB_BASE_URL=https://localhost:18443`, `PAYMENT_PROVIDER=fake`, SMTP empty; open `https://localhost:18443` (accept the local certificate), load the demo catalogue as in step 5, and in step 6 the card option opens a test payment page that marks the order paid.

## From the public demo to a real shop (added 17.09.2026)

The demo at https://market.agintent.com runs from `scripts/demo_deploy.sh` (details: `docs/DEMO-DEPLOY.md`, decisions: `docs/DECISIONS-2026-09-17.md`). Going real is a sequence of owner facts first, settings second. Do not skip a step to save time.

**A. Facts only the owner can supply (nothing below starts without them).**
- Own domain for the shop (market.agintent.com is a demo address) and a contact mailbox on it.
- Registered seller name and address; GST/HST registration decided with the accountant (`SHOP_TAX_MODE`). Tax table was checked against CRA and provincial pages on 17.09.2026; recheck on the go-live date.
- Payment account: Stripe live keys and/or an e-Transfer address. Live keys never go into git or reports, only the server env file.
- Email provider (SMTP with DKIM on the domain). Mailpit is removed from the env.
- The real catalogue with written consent from each maker (name, photos, story). The commission terms toward makers signed per maker (model: commission marketplace, makers keep ownership).
- Confirmation of the demo defaults: returns 30 days, free shipping threshold, carrier (`SHOP_CARRIER`), ship-from city (`SHOP_BASE_PLACE`), Quebec shipping, retention periods. While a value is unconfirmed the pages keep saying "not confirmed yet".
- A lawyer's read of Terms and Privacy.

**B. Hosting.** Either keep the workstation + tunnel (costs nothing, depends on this machine being up) or move to a server with at least 2 GB free RAM and 10 GB disk. docker-2 did not qualify on 17.09 (48 MB free memory, 1.9 GB disk). On a server, steps 1–3 above apply; behind Cloudflare keep `docker-compose.tunnel.yml` and `ADMIN_CLIENT_IP_HEADER=cf-connecting-ip` (only with Cloudflare in front, since it overwrites that header).

**C. Before real buyers exist.**
- Wipe demo data: take a backup, then start from an empty database (new volume) instead of retiring demo items one by one. Demo orders (UA-260917-…) must not reach real reports.
- The mail sweep would send the new "cancelled" email for orders cancelled in the last `ORDER_MAIL_MAX_AGE_DAYS`; an empty database avoids this. If data is kept, mark old cancellations as handled first.
- Replace demo barcodes (GS1 482 prefix in seed data) with the real ones or in-store 2x codes.
- Sign-in protection counts attempts in web-server memory and can be bypassed by parallel requests; put Cloudflare rate limiting on `/admin/api/login` or fix the counter before real money is involved.
- Copy backups off the machine (step 8, weekly), e.g. to the owner's Drive.

**D. Switch.** In the server env: remove `PAYMENT_PROVIDER=fake`, add payment keys, real SMTP, `SHOP_CONTACT_*`, policy values; `SHOP_CATALOGUE_STATUS=live`. Deploy, then step 7 above (one real order, refund, cancel). `WEB_INDEXABLE=true` and removing the robots/`X-Robots-Tag` lines from `deploy/Caddyfile.tunnel` come last.
