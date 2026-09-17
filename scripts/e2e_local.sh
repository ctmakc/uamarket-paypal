#!/usr/bin/env bash
# End-to-end purchase on the docker compose stack, with a PASS/FAIL line per step.
#
#   scripts/e2e_local.sh            # build, start, run, leave the stack up
#   scripts/e2e_local.sh --down     # ... and stop it afterwards (volumes removed)
#
# Uses its own compose project (uamarket-e2e), its own env file (.e2e.env, built from
# .env.example with fake payments and random API keys) and its own host ports, so it does
# not touch a stack started with plain `docker compose up`.
# Needs: docker compose, curl, python3, node with the `playwright` package and Chromium
# (NODE_PATH=$(npm root -g) is set below).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-uamarket-e2e}"
export APP_HOST_PORT="${E2E_APP_PORT:-18000}"
export WEB_HOST_PORT="${E2E_WEB_PORT:-13000}"
export MAILPIT_UI_PORT="${E2E_MAILPIT_PORT:-18025}"
export UAMARKET_ENV_FILE=.e2e.env
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
API="http://127.0.0.1:${APP_HOST_PORT}"
WEB="http://localhost:${WEB_HOST_PORT}"
MAILPIT="http://127.0.0.1:${MAILPIT_UI_PORT}"
OUT="${E2E_OUT:-$ROOT/e2e-artifacts}"
mkdir -p "$OUT"

FAILS=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s%s\n' "$1" "${2:+ — $2}"; FAILS=$((FAILS + 1)); }
step() { if "${@:2}"; then pass "$1"; else fail "$1"; fi; }

KEY_OP="e2e-op-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
KEY_AD="e2e-ad-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
ADMIN_PW="e2e-owner-$(python3 -c 'import secrets;print(secrets.token_hex(8))')"
python3 - "$KEY_OP" "$KEY_AD" "$WEB" "$ADMIN_PW" <<'PY'
import re, sys
sys.path.insert(0, "tools")
from admin_password_hash import make_hash
import secrets
op, ad, web, pw = sys.argv[1:5]
text = open(".env.example", encoding="utf-8").read()
over = {
    "PAYMENT_PROVIDER": "fake", "ALLOW_INSECURE_DEV": "false", "OPERATOR_API_KEY": op, "ADMIN_API_KEY": ad,
    "WEB_BASE_URL": web, "SCHEDULER_INTERVAL_SECONDS": "30", "SHOP_CATALOGUE_STATUS": "", "WEB_INDEXABLE": "false",
    "SHOP_BASE_PLACE": "", "SHOP_BASE_PLACE_UK": "", "ETRANSFER_EMAIL": "", "UAMARKET_ENV_FILE": ".e2e.env",
    "ADMIN_PASSWORD_HASH": make_hash(pw), "ADMIN_SESSION_SECRET": secrets.token_hex(32), "ADMIN_LOGIN_LOCK_SECONDS": "20",
}
for k, v in over.items():
    text, n = re.subn(rf"(?m)^{k}=.*$", f"{k}={v}", text)
    if not n:
        text += f"\n{k}={v}\n"
open(".e2e.env", "w", encoding="utf-8").write(text)
PY
AUTH=(-H "x-api-key: ${KEY_OP}")
ADMIN=(-H "x-api-key: ${KEY_AD}")
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
psql_q() { docker compose exec -T db psql -U heritage -d heritage -tAc "$1" | tr -d '[:space:]'; }

echo "== UA Market e2e (project ${COMPOSE_PROJECT_NAME}, web ${WEB}, api ${API}, mailpit ${MAILPIT}) =="

step "docker compose config -q" docker compose config -q

start=$(date +%s)
if docker compose up --build -d >"$OUT/compose-up.log" 2>&1; then pass "compose up --build"; else fail "compose up --build" "see $OUT/compose-up.log"; fi
healthy=0
while [ $(( $(date +%s) - start )) -lt 180 ]; do
  ps_out=$(docker compose ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null)
  if echo "$ps_out" | grep -q '^app running healthy' && echo "$ps_out" | grep -q '^web running healthy' \
     && echo "$ps_out" | grep -q '^db running healthy' && echo "$ps_out" | grep -q '^mailpit running' \
     && echo "$ps_out" | grep -q '^scheduler running'; then healthy=1; break; fi
  sleep 3
done
elapsed=$(( $(date +%s) - start ))
if [ "$healthy" = 1 ]; then pass "db, app, web, mailpit, scheduler up and healthy in ${elapsed}s (limit 180s)"; else fail "stack healthy within 180s" "$(docker compose ps --format '{{.Service}}={{.State}}/{{.Health}}' | tr '\n' ' ')"; fi

curl -sf -X DELETE "$MAILPIT/api/v1/messages" >/dev/null || true
seed() { curl -sf -X POST "${ADMIN[@]}" "$API/admin/seed-catalog?with_stock=false" | grep -q '"ok":true'; }
step "seed placeholder catalogue (no stock)" seed
receipt() { curl -sf -X POST "${AUTH[@]}" -H 'content-type: application/json' "$API/v1/receipts" -d "{\"sku\":\"$1\",\"location_id\":\"A-LANE-01\",\"qty\":$2,\"reference_id\":\"E2E-$1\"}" | grep -q '"ok":true'; }
receipts() { receipt OPISHNIA-MUG-01 10 && receipt OPISHNIA-MUG-03 1; }
step "receipts: OPISHNIA-MUG-01 x10, OPISHNIA-MUG-03 x1" receipts

config_ok() {
  curl -sf "$API/v1/storefront/config" | python3 -c 'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d["payment_methods"]==["STRIPE"] and d["payment_test_mode"] and d["catalogue"]=="placeholder" and d["notifications"]["email"] else 1)'
}
step "config: fake card payments, placeholder catalogue, email on" config_ok

rsc_headers=$(curl -s -D - -o /dev/null -H 'RSC: 1' -H 'Next-Router-Prefetch: 1' "$WEB/faq?_rsc=abc")
if echo "$rsc_headers" | head -1 | grep -q ' 200' && ! echo "$rsc_headers" | grep -qi '^location:'; then pass "RSC prefetch /faq?_rsc=abc -> 200, no location"; else fail "RSC prefetch /faq?_rsc=abc" "$(echo "$rsc_headers" | head -1)"; fi

ottawa=$(for p in / /uk /llms.txt; do curl -s "$WEB$p"; done | grep -ci 'ottawa\|оттав' || true)
if [ "$ottawa" = 0 ]; then pass "SHOP_BASE_PLACE unset: no Ottawa on /, /uk, /llms.txt"; else fail "no Ottawa on /, /uk, /llms.txt" "$ottawa lines"; fi

if node web/tests/smoke-requests.mjs "$WEB" >"$OUT/smoke-requests.log" 2>&1; then pass "idle request counter (/, /faq, /uk/faq, /shop <= 60 in 10 s)"; else fail "idle request counter" "$(tr '\n' ' ' < "$OUT/smoke-requests.log")"; fi

declare -A ORDER EMAIL
for lang in en uk; do
  if res=$(node scripts/e2e/purchase.mjs buy "$WEB" "$lang" "$OUT" 2>"$OUT/buy-$lang.log"); then
    ORDER[$lang]=$(echo "$res" | json 'd["order"]'); EMAIL[$lang]=$(echo "$res" | json 'd["email"]')
    demo=$(echo "$res" | json 'd["demoLine"] and d["demoNote"]')
    pass "browser purchase $lang: product -> bag -> checkout -> test payment (${ORDER[$lang]})"
    if [ "$demo" = "1" ] || [ "$demo" = "True" ]; then pass "demo line at checkout and no-money note on the order page ($lang)"; else fail "demo line and note ($lang)"; fi
  else
    fail "browser purchase $lang" "see $OUT/buy-$lang.log"
  fi
done

for lang in en uk; do
  num="${ORDER[$lang]:-}"; [ -z "$num" ] && { fail "operator fulfilment $lang" "no order"; continue; }
  oid=$(psql_q "select id from orders where order_number='${num}'")
  state=$(psql_q "select state from orders where id='${oid}'")
  if [ "$state" = "PICK_PLANNED" ]; then pass "$num paid by fake webhook and auto-reserved (PICK_PLANNED)"; else fail "$num paid and reserved" "state=$state"; fi
  missions=$(curl -sf -X POST "${AUTH[@]}" "$API/v1/orders/$oid/reserve")
  echo "$missions" | grep -q '"missions"' && pass "$num reserve (missions listed)" || fail "$num reserve" "$missions"
  ok=1
  for mid in $(echo "$missions" | json '" ".join(m["id"] for m in d["missions"])'); do
    barcode=$(psql_q "select v.barcode from missions m join variants v on v.id=m.variant_id where m.id='${mid}'")
    curl -sf -X POST "${AUTH[@]}" -H 'content-type: application/json' "$API/v1/missions/$mid/scan-confirm" -d "{\"barcode\":\"$barcode\"}" | grep -q CONFIRMED || ok=0
  done
  [ "$ok" = 1 ] && pass "$num scan barcodes" || fail "$num scan barcodes"
  pkg=$(curl -sf -X POST "${AUTH[@]}" "$API/v1/orders/$oid/pack" | json 'd["package_id"]')
  [ -n "$pkg" ] && pass "$num pack" || fail "$num pack"
  curl -sf -X POST "${AUTH[@]}" -H 'content-type: application/json' "$API/v1/packages/$pkg/weight" -d '{"weight_g": 480}' | grep -q 480 && pass "$num weigh" || fail "$num weigh"
  tracking="E2E${RANDOM}${RANDOM}CA"
  eval "TRACK_$lang=$tracking"
  shipped=$(curl -sf -X POST "${AUTH[@]}" -H 'content-type: application/json' "$API/v1/orders/$oid/ship" -d "{\"carrier\":\"Canada Post\",\"tracking_code\":\"$tracking\"}")
  echo "$shipped" | grep -q HANDOFF_COMPLETE && pass "$num ship with manual tracking $tracking (no locker)" || fail "$num ship" "$shipped"
  curl -sf "${AUTH[@]}" "$API/v1/orders/$oid/mail/handoff/preview?format=text" | grep -q "$tracking" && pass "$num mail preview carries the tracking" || fail "$num mail preview"
done

sleep 2
msgs=$(curl -sf "$MAILPIT/api/v1/messages?limit=200")
for lang in en uk; do
  num="${ORDER[$lang]:-none}"
  count=$(echo "$msgs" | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for m in d.get('messages',[]) if '$num' in m['Subject']))")
  subjects=$(echo "$msgs" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' | '.join(m['Subject'] for m in d.get('messages',[]) if '$num' in m['Subject']))")
  if [ "$count" = 3 ]; then pass "Mailpit holds placed, paid and shipped emails for $num"; else fail "Mailpit placed/paid/shipped for $num" "count=$count: $subjects"; fi
  echo "   $subjects"
done

for lang in en uk; do
  num="${ORDER[$lang]:-}"; [ -z "$num" ] && continue
  var="TRACK_$lang"
  if node scripts/e2e/purchase.mjs status "$WEB" "$lang" "$num" "${EMAIL[$lang]}" "${!var}" "$OUT" >"$OUT/status-$lang.log" 2>&1; then pass "status page $lang shows Shipped and the tracking code (screenshot)"; else fail "status page $lang" "$(cat "$OUT/status-$lang.log")"; fi
done

if node scripts/e2e/purchase.mjs second "$WEB" OPISHNIA-MUG-03 "$OUT" >"$OUT/stock1.log" 2>&1; then pass "stock-1 SKU: first buyer reaches payment, second is stopped at checkout"; else fail "stock-1 SKU second buyer" "$(tail -3 "$OUT/stock1.log" | tr '\n' ' ')"; fi

if ADMIN_PASSWORD="$ADMIN_PW" ADMIN_API_KEY="$KEY_AD" OPERATOR_API_KEY="$KEY_OP" ADMIN_LOGIN_LOCK_SECONDS=20 \
   node web/tests/admin-flow.mjs "$WEB" "$OUT" "$MAILPIT" >"$OUT/admin-flow.log" 2>&1; then
  pass "owner admin in the browser: sign-in lock, maker, product, photos, stock, import, order to shipped ($(grep -c '^PASS' "$OUT/admin-flow.log") checks)"
else
  fail "owner admin in the browser" "$(grep '^FAIL' "$OUT/admin-flow.log" | head -3 | tr '\n' ' ')"
fi

if node web/tests/wave3-shopper.mjs "$WEB" "$API" "$KEY_AD" "$OUT" >"$OUT/wave3-shopper.log" 2>&1; then
  pass "wave 3 shopper checks: search, phone layout, gallery, UK purchase, key-only order URL, seller block, icons, forged XFF ($(grep -c '^PASS' "$OUT/wave3-shopper.log") checks)"
else
  fail "wave 3 shopper checks" "$(grep '^FAIL' "$OUT/wave3-shopper.log" | head -3 | tr '\n' ' ')"
fi

swept() { docker compose logs scheduler 2>/dev/null | grep "sweep {" >/dev/null; }  # no -q: an early exit SIGPIPEs docker under pipefail
step "scheduler container ran a sweep" swept

echo "== artifacts: $OUT =="
if [ "${1:-}" = "--down" ]; then docker compose down -v >/dev/null 2>&1; fi
if [ "$FAILS" = 0 ]; then echo "ALL PASS"; exit 0; else echo "$FAILS step(s) FAILED"; exit 1; fi
