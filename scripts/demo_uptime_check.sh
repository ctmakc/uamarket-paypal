#!/usr/bin/env bash
# Is the public demo answering? Run by the user timer uamarket-demo-uptime.timer every 5 minutes.
#
#   scripts/demo_uptime_check.sh            check once, heal after two failures in a row
#   DEMO_URL=… DEMO_STATE=… DEMO_LOG=…      override the address, the counter file and the log
#
# One failed curl can be a Cloudflare hiccup or a deploy in flight, so the script heals on the
# SECOND failure in a row: it restarts the tunnel unit, then brings the compose project back up,
# then checks once more. Everything it does goes to the log file and nowhere else — no mail, no
# chat, nobody is paged. Read it with:
#
#   tail -n 40 ~/.local/state/uamarket-demo/uptime.log
set -uo pipefail

URL="${DEMO_URL:-https://market.agintent.com/}"
STATE_DIR="${DEMO_STATE_DIR:-$HOME/.local/state/uamarket-demo}"
STATE="${DEMO_STATE:-$STATE_DIR/uptime.fails}"
LOG="${DEMO_LOG:-$STATE_DIR/uptime.log}"
UNIT="${DEMO_TUNNEL_UNIT:-cloudflared-uamarket-demo.service}"
DEMO_DIR="${DEMO_DIR:-/data/projects/uamarket-demo}"
DEMO_ENV="${DEMO_ENV:-$HOME/.config/uamarket/demo.env}"

mkdir -p "$STATE_DIR"
say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG"; }
# Every run writes a line, so the log itself proves the timer is alive; it is trimmed to the
# last 2000 lines (about a week at one line every five minutes).
trim() { [ "$(wc -l <"$LOG" 2>/dev/null || echo 0)" -gt 2000 ] && { tail -n 1000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"; }; return 0; }

# -L: the storefront answers the bare address with a 308 to the language it picked.
probe() { curl -sSL -o /dev/null -w '%{http_code}' --max-time 20 "$URL" 2>/dev/null || echo 000; }

code="$(probe)"
trim
if [ "$code" = "200" ]; then
  say "ok $code"
  : >"$STATE"
  exit 0
fi

fails=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$fails" >"$STATE"
say "FAIL $code (in a row: $fails)"
[ "$fails" -lt 2 ] && exit 0

say "healing: restart $UNIT"
systemctl --user restart "$UNIT" >>"$LOG" 2>&1 || say "restart of $UNIT failed"
if [ -d "$DEMO_DIR" ] && [ -r "$DEMO_ENV" ]; then
  say "healing: compose up -d"
  docker compose -p uamarket-demo \
    -f "$DEMO_DIR/docker-compose.yml" -f "$DEMO_DIR/docker-compose.prod.yml" -f "$DEMO_DIR/docker-compose.tunnel.yml" \
    --env-file "$DEMO_ENV" --project-directory "$DEMO_DIR" up -d >>"$LOG" 2>&1 || say "compose up failed"
fi
sleep 20
after="$(probe)"
say "after healing: $after"
[ "$after" = "200" ] && : >"$STATE"
exit 0
