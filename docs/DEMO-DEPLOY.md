# Public demo: https://market.agintent.com

A demonstration shop (decisions: `docs/DECISIONS-2026-09-17.md`). Every order is a demo order that
asks for no money, card payment is the local test page (`PAYMENT_PROVIDER=fake`), no email leaves
the machine (Mailpit), and search engines are told to stay away (robots.txt disallow, `noindex`
meta and `X-Robots-Tag` header).

## Where it runs

- **Host: the workstation**, not VPS docker-2. On 17.09.2026 docker-2 had 48 MB of free memory with
  swap full (2 GB total) and 1.9 GB of free disk, too little to build and run Postgres, the API,
  the scheduler, Next.js and Caddy. This is the fallback the hosting decision names.
- **Code**: its own git worktree `/data/projects/uamarket-demo`, detached at a pushed commit.
  Edits in the development checkout reach the demo only through `scripts/demo_deploy.sh`.
- **Stack**: compose project `uamarket-demo` = `docker-compose.yml` + `docker-compose.prod.yml` +
  `docker-compose.tunnel.yml` (db, app, scheduler, web, caddy, backup, mailpit).
- **Settings and secrets**: `~/.config/uamarket/demo.env` (mode 600, not in git). The admin
  password is in `~/.config/uamarket/demo-admin.txt` next to it.
- **Ports, all on 127.0.0.1**: Caddy 18480 (the tunnel's target), Mailpit UI 18425. The API and the
  storefront publish no port in the production compose.
- **Public address**: named Cloudflare Tunnel `uamarket-demo` → `http://127.0.0.1:18480`, config
  `~/.cloudflared/uamarket-demo.yml`, user unit `cloudflared-uamarket-demo.service` (enabled).
  Tunnel id `55bb761b-332c-47be-be30-bc02986db8b6`. DNS: proxied CNAME `market.agintent.com` →
  `55bb761b-332c-47be-be30-bc02986db8b6.cfargotunnel.com` (it overrides the zone's `*.agintent.com` wildcard).
- **Visitor address**: Caddy passes `CF-Connecting-IP` as `X-Real-IP`; the admin sign-in reads
  `cf-connecting-ip` (`ADMIN_CLIENT_IP_HEADER`).

## Update to the latest pushed code

    git push                                   # from the development checkout, on main
    scripts/demo_deploy.sh                     # or: scripts/demo_deploy.sh <commit>

The script's default ref is **origin/main** (17.09.2026; it followed the feature branch before,
which let the public site and main drift apart in silence). Deploy anything else only by naming
the commit, and put it on main afterwards.

The API applies migrations itself on start. Database and photos live in docker volumes and survive.

## Everyday commands

    cd /data/projects/uamarket-demo
    P="docker compose -p uamarket-demo -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tunnel.yml --env-file $HOME/.config/uamarket/demo.env"
    $P ps                                      # all services up and healthy
    $P logs --tail 100 app web                 # recent errors
    $P exec backup sh /scripts/pg-backup.sh now   # a backup right now
    systemctl --user status cloudflared-uamarket-demo

Emails the demo "sends": `http://127.0.0.1:18425` on the workstation.

## Smoke the live site

    ADMIN_PASSWORD=$(sed -n 's/^password=//p' ~/.config/uamarket/demo-admin.txt) NODE_PATH=$(npm root -g) \
      node web/tests/live-demo-smoke.mjs https://market.agintent.com prod-check-artifacts/live-demo http://127.0.0.1:18425

Each run places one demo order (`smoke-…@example.test`) and ships it. Those rehearsal orders pile up
in the admin queue, so clear them out before anybody records or shows the demo — the queue on
17.09.2026 held nine of them and now holds two written ones (`demo-buyer@example.test`,
`demo-shopper@example.test`: one being picked, one handed over). Take a backup first, then delete the
order and everything that points at it in one transaction: `order_lines`, `reservations`, `missions`,
`packages`, `shipments`, `exceptions` (reference_type MISSION), `inventory_events` (reference_type
ORDER_LINE), `outbox_messages` (aggregate_id) and `locker_access`.

## Backups

The `backup` service dumps the database and the photo volume every night at 07:00 UTC and keeps 14 days
in the volume `uamarket-demo_backups`. The schedule is unchanged; what follows is the proof that a dump
can be taken and read back, run against this stack on **17.09.2026**.

    P="-p uamarket-demo -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tunnel.yml --env-file $HOME/.config/uamarket/demo.env"

    # 1. a backup right now
    docker compose $P exec -T backup sh /scripts/pg-backup.sh now
    # backup 20260917T211857Z: 2 file(s); kept: 3 database dump(s)

    # 2. what is in the volume
    docker compose $P exec -T backup ls -l /backups
    # uamarket-20260917T211857Z.dump   98017 bytes
    # media-20260917T211857Z.tar.gz    16905 bytes

    # 3. read that dump back into a scratch database inside the same stack
    COMPOSE_ARGS="$P" scripts/backup/restore.sh uamarket-20260917T211857Z.dump
    # NOTICE: database "restore_check" does not exist, skipping
    # DROP DATABASE / CREATE DATABASE
    # orders=2
    # products=22
    # alembic=b2e6d4f1a8c3
    # restored uamarket-20260917T211857Z.dump into restore_check

The three numbers are the check: they matched the live `heritage` database (2 orders, 22 products, the
migration head the API runs). `restore_check` is a scratch database in the same Postgres container and
the script recreates it on every run, so the live database is never touched unless the target is named
`heritage` on purpose. Drop it with
`docker compose $P exec -T backup psql -d postgres -c 'DROP DATABASE restore_check'`.

Photos live in the `media-*.tar.gz` beside the dump: `docker compose $P exec -T backup tar -xzf
/backups/media-<stamp>.tar.gz -C /media` puts them back.

## The demo answers, and comes back on its own

- Every compose service is `restart: always`: a container comes back from a crash, from a reboot and
  from a docker daemon restart, and it comes back even when somebody stopped it by hand earlier (that
  last case is where `unless-stopped` used to leave it down for good). A `docker stop` still holds
  until the next `up`, which is the gap the uptime check below covers.
  `cloudflared-uamarket-demo.service` is `Restart=always`, `RestartSec=5`, `StartLimitIntervalSec=0`.
- `uamarket-demo-uptime.timer` (user timer, every 5 minutes) runs `scripts/demo_uptime_check.sh`: it
  curls https://market.agintent.com/ and, on the **second** failure in a row, restarts the tunnel unit
  and runs `compose up -d`, then checks again. One failure heals nothing, because a single 5xx during a
  deploy is normal. It writes one line per run and warns no person — no mail, no chat, no alert:

      systemctl --user list-timers uamarket-demo-uptime.timer
      tail -n 20 ~/.local/state/uamarket-demo/uptime.log

  Tried on 17.09.2026 by stopping the tunnel unit and the `web` container by hand (a `docker stop`
  is the one thing `restart: always` leaves alone, which is what the check is for):

      # 2026-09-17T21:16:31Z ok 200
      # 2026-09-17T21:19:40Z FAIL 530 (in a row: 1)
      # 2026-09-17T21:19:40Z FAIL 530 (in a row: 2)
      # 2026-09-17T21:19:40Z healing: restart cloudflared-uamarket-demo.service
      # 2026-09-17T21:19:40Z healing: compose up -d
      # 2026-09-17T21:20:07Z after healing: 200

- Unit copies live in `deploy/systemd/`; install them with
  `install -m 644 deploy/systemd/<unit> ~/.config/systemd/user/ && systemctl --user daemon-reload`.

## Reset the demo data

Load the demo catalogue again after a wipe:

    $P exec app python -c "import urllib.request as u,os; print(u.urlopen(u.Request('http://127.0.0.1:8000/admin/seed-catalog', method='POST', headers={'x-api-key': os.environ['ADMIN_API_KEY']})).read())"

## Stop the demo

    $P down                                    # keeps data volumes
    systemctl --user disable --now cloudflared-uamarket-demo
