#!/usr/bin/env bash
# Rehearse the production stack on this machine, with a PASS/FAIL line per step.
#
#   scripts/prod_local_check.sh            # build, start, check, leave it running
#   scripts/prod_local_check.sh --down     # ... and remove it afterwards (volumes too)
#
# docker-compose.yml + docker-compose.prod.yml under its own project name (uamarket-prodcheck),
# with Caddy's internal certificate authority for SHOP_DOMAIN=localhost on host ports
# 18080/18443. Checks: compose config, https through Caddy, no host port on app/db/web, the
# Stripe webhook route, forged X-Forwarded-For rate limiting, two real client addresses counted
# separately, a browser purchase over https, backup and restore into a scratch database.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export COMPOSE_PROJECT_NAME=uamarket-prodcheck
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
export COMPOSE_ENV_FILES=.prod-check.env
export UAMARKET_ENV_FILE=.prod-check.env
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
HTTPS_PORT=18443
BASE="https://localhost:${HTTPS_PORT}"
OUT="${PROD_CHECK_OUT:-$ROOT/prod-check-artifacts}"
mkdir -p "$OUT"
FAILS=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s%s\n' "$1" "${2:+ — $2}"; FAILS=$((FAILS + 1)); }

KEY_AD="pc-ad-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
KEY_OP="pc-op-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
python3 - "$KEY_AD" "$KEY_OP" "$SECRET" "$BASE" "$HTTPS_PORT" <<'PY'
import re, secrets, sys
ad, op, secret, base, port = sys.argv[1:6]
text = open(".env.example", encoding="utf-8").read()
over = {
    "POSTGRES_PASSWORD": secrets.token_hex(24), "INTERNAL_PROXY_SECRET": secret, "SHOP_DOMAIN": "localhost",
    "CADDY_TLS": "tls internal", "CADDY_HTTP_PORT": "18080", "CADDY_HTTPS_PORT": port, "WEB_BASE_URL": base,
    "PAYMENT_PROVIDER": "fake", "ADMIN_API_KEY": ad, "OPERATOR_API_KEY": op, "ALLOW_INSECURE_DEV": "false",
    "SMTP_HOST": "", "MAIL_FROM": "", "SHOP_TAX_MODE": "gst_hst_registered", "UAMARKET_ENV_FILE": ".prod-check.env",
}
for k, v in over.items():
    text, n = re.subn(rf"(?m)^{k}=.*$", f"{k}={v}", text)
    if not n:
        text += f"\n{k}={v}\n"
open(".prod-check.env", "w", encoding="utf-8").write(text)
PY

echo "== production rehearsal (project $COMPOSE_PROJECT_NAME, $BASE) =="
if docker compose config -q; then pass "docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q"; else fail "prod compose config"; fi

if docker compose up -d --build >"$OUT/up.log" 2>&1; then pass "prod compose up --build"; else fail "prod compose up" "see $OUT/up.log"; fi
ok=0
for _ in $(seq 1 90); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/" || true)
  [ "$code" = 200 ] && { ok=1; break; }
  sleep 2
done
if [ "$ok" = 1 ]; then pass "https://localhost:${HTTPS_PORT}/ answers 200 through Caddy"; else fail "https through Caddy" "last code $code"; fi
issuer=$(echo | openssl s_client -connect "localhost:${HTTPS_PORT}" -servername localhost 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null)
if echo "$issuer" | grep -qi "Caddy Local Authority"; then pass "certificate from Caddy's internal CA ($issuer)"; else fail "internal CA certificate" "$issuer"; fi
redirect=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://localhost:18080/shop")
if echo "$redirect" | grep -q "^30[18] https://localhost"; then pass "http redirects to https ($redirect)"; else fail "http to https redirect" "$redirect"; fi

published=$(docker compose ps --format '{{.Service}} {{.Publishers}}')
echo "$published" > "$OUT/published.txt"
bad=$(docker compose ps --format json | python3 -c "
import sys, json
rows = [json.loads(l) for l in sys.stdin if l.strip()]
print(' '.join(r['Service'] for r in rows if r['Service'] != 'caddy' and any(p.get('PublishedPort') for p in (r.get('Publishers') or []))))")
if [ -z "$bad" ]; then pass "only caddy publishes a host port (app, db, web, scheduler, backup have none)"; else fail "host ports" "$bad"; fi
if ! curl -s -m 3 "http://127.0.0.1:18000/health" | grep -q ok; then pass "the API is not reachable on a host port"; else fail "API reachable from host"; fi

inapp() { docker compose exec -T app python -c "$1"; }
seed=$(inapp "import urllib.request as u; r=u.Request('http://127.0.0.1:8000/admin/seed-catalog?with_stock=false', method='POST', headers={'x-api-key':'$KEY_AD'}); print(u.urlopen(r).read().decode())")
echo "$seed" | grep -q '"ok":true' && pass "demo catalogue seeded inside the network" || fail "seed" "$seed"
for sku in TABLE-RUNNER-RED-01 OPISHNIA-MUG-01; do
  inapp "import urllib.request as u, json; r=u.Request('http://127.0.0.1:8000/v1/receipts', data=json.dumps({'sku':'$sku','location_id':'A-LANE-01','qty':80,'reference_id':'PC-$sku'}).encode(), method='POST', headers={'x-api-key':'$KEY_OP','content-type':'application/json'}); u.urlopen(r).read()" \
    && pass "stock received for $sku" || fail "receipt $sku"
done

wh=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "$BASE/webhooks/stripe" -d '{}')
if [ "$wh" = 401 ]; then pass "/webhooks/stripe reaches the API through Caddy (401 without a signature)"; else fail "/webhooks/stripe route" "$wh"; fi
v1=$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/v1/storefront/config")
if [ "$v1" = 404 ]; then pass "other API paths are not exposed by Caddy (/v1/storefront/config -> 404 from the storefront)"; else fail "API path exposure" "$v1"; fi

# The browser purchase comes before the rate-limit runs, which use up this machine's ten orders.
if res=$(E2E_INSECURE_TLS=1 node scripts/e2e/purchase.mjs buy "$BASE" uk "$OUT" 2>"$OUT/buy.log"); then
  pass "browser purchase over https (UK, test payment): $(echo "$res" | python3 -c 'import sys,json;print(json.load(sys.stdin)["order"])')"
else
  fail "browser purchase over https" "see $OUT/buy.log"
fi

order_body() { printf '{"idempotency_key":"pc-%s-%s","email":"rate@example.test","name":"Rate Test","locale":"en","fulfillment_method":"SHIP","ship_to":{"street1":"1 Main St","city":"Ottawa","province":"ON","postal_code":"K1A 0B1"},"lines":[{"sku":"TABLE-RUNNER-RED-01","qty":1}],"terms_accepted":true}' "$1" "$RANDOM$RANDOM"; }
codes=""
for i in $(seq 1 12); do
  c=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "$BASE/api/order" -H 'content-type: application/json' \
      -H "X-Forwarded-For: 203.0.113.$i" -H "X-Real-IP: 203.0.113.$i" -H "X-Client-IP: 203.0.113.$i" -H "X-Internal-Proxy-Secret: guess-$i" \
      --data "$(order_body host$i)")
  codes="$codes$c "
done
echo "forged: $codes" > "$OUT/rate-forged.txt"
# The browser purchase above came from this machine too, so fewer than ten may be left.
if python3 -c "
import sys; c=sys.argv[1].split(); i=c.index('429') if '429' in c else -1
sys.exit(0 if 0 < i <= 10 and all(x=='201' for x in c[:i]) and all(x=='429' for x in c[i:]) else 1)" "$codes"; then
  pass "12 orders with forged forwarding headers through Caddy: accepted up to the limit of 10 per address, then 429 ($codes)"
else
  fail "forged forwarding headers" "$codes"
fi

NET="${COMPOSE_PROJECT_NAME}_default"
client() {
  docker run -i --rm --network "$NET" -e BODY_TAG="$1" uamarket-api:local python - <<'PY'
import http.client, json, os, random, socket, ssl
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
ip = socket.gethostbyname(socket.gethostname())


class ToCaddy(http.client.HTTPSConnection):
    """Connect to the caddy service, and say localhost in SNI and Host: the site Caddy serves."""
    def connect(self):
        self.sock = ctx.wrap_socket(socket.create_connection(("caddy", 443), timeout=20), server_hostname="localhost")


codes = []
for i in range(11):
    body = {"idempotency_key": f"pc-{os.environ['BODY_TAG']}-{i}-{random.random()}", "email": "rate@example.test", "name": "Rate Test",
            "locale": "en", "fulfillment_method": "SHIP", "terms_accepted": True,
            "ship_to": {"street1": "1 Main St", "city": "Ottawa", "province": "ON", "postal_code": "K1A 0B1"},
            "lines": [{"sku": "TABLE-RUNNER-RED-01", "qty": 1}]}
    conn = ToCaddy("localhost", 443, context=ctx)
    conn.request("POST", "/api/order", body=json.dumps(body), headers={"content-type": "application/json"})
    codes.append(conn.getresponse().status)
    conn.close()
print(ip, " ".join(map(str, codes)))
PY
}
# Both at once, so the two containers hold two different addresses on the compose network.
client a >"$OUT/rate-real-a.txt" & pa=$!
client b >"$OUT/rate-real-b.txt" & pb=$!
wait $pa $pb
a=$(cat "$OUT/rate-real-a.txt"); b=$(cat "$OUT/rate-real-b.txt")
ok_client() { echo "$1" | awk '{c=0; for(i=2;i<=11;i++) if($i==201) c++; exit !(c==10 && $12==429)}'; }
if ok_client "$a" && ok_client "$b" && [ "$(echo "$a" | cut -d' ' -f1)" != "$(echo "$b" | cut -d' ' -f1)" ]; then
  pass "two real client addresses through Caddy are counted separately ($a | $b)"
else
  fail "two real client addresses" "$a | $b"
fi

if docker compose exec -T backup sh /scripts/pg-backup.sh now >"$OUT/backup.log" 2>&1; then
  dump=$(docker compose exec -T backup sh -c 'ls -1t /backups/uamarket-*.dump | head -1' | tr -d '\r')
  size=$(docker compose exec -T backup sh -c "stat -c %s $dump" | tr -d '\r')
  if [ -n "$dump" ] && [ "${size:-0}" -gt 1000 ]; then pass "backup wrote $dump ($size bytes) and the photo archive"; else fail "backup file" "$dump $size"; fi
  if scripts/backup/restore.sh "$(basename "$dump")" restore_check >"$OUT/restore.log" 2>&1 && grep -q "orders=" "$OUT/restore.log"; then
    pass "restore into scratch database restore_check: $(grep -E 'orders=|products=|alembic=' "$OUT/restore.log" | tr '\n' ' ')"
  else
    fail "restore" "$(tail -3 "$OUT/restore.log" | tr '\n' ' ')"
  fi
else
  fail "backup now" "$(tail -3 "$OUT/backup.log" | tr '\n' ' ')"
fi
loop=$(docker compose logs backup 2>/dev/null | grep -c "next backup in")
if [ "$loop" -ge 1 ]; then pass "backup service is waiting for its nightly run"; else fail "backup loop" "no 'next backup' line"; fi

echo "== artifacts: $OUT =="
if [ "${1:-}" = "--down" ]; then docker compose down -v >/dev/null 2>&1; rm -f .prod-check.env; fi
if [ "$FAILS" = 0 ]; then echo "ALL PASS"; exit 0; else echo "$FAILS step(s) FAILED"; exit 1; fi
