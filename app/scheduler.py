"""The shop's timer: order email that is due, expired pickup codes, expired stock holds.

Runs as its own container (`scheduler` in docker-compose.yml) against the same database as
the API. It calls the same service functions as POST /v1/notifications/order-mail, so the
two can never disagree, and every step is safe to repeat: mail is claimed in the outbox
before it is sent, and a released hold is released once.

    python -m app.scheduler            # every SCHEDULER_INTERVAL_SECONDS (default 300)
    python -m app.scheduler --once     # one pass, then exit
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time

from .db import make_engine, make_session_factory
from .services.locker import sweep_expired_pickup_codes
from .services.storefront import dispatch_order_mail, release_expired_holds

log = logging.getLogger("uamarket.scheduler")


def interval_seconds() -> int:
    try:
        return max(30, int((os.getenv("SCHEDULER_INTERVAL_SECONDS") or "300").strip()))
    except ValueError:
        return 300


def run_once(SessionLocal) -> dict:
    with SessionLocal() as db:
        holds = release_expired_holds(db)
        db.commit()
        mail = dispatch_order_mail(db)
        codes = sweep_expired_pickup_codes(db)
        db.commit()
    return {"holds_released": holds, "pickup_codes_forgotten": codes, **mail}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    SessionLocal = make_session_factory(make_engine())
    stop = {"now": False}

    def _stop(*_):
        stop["now"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    every = interval_seconds()
    while True:
        try:
            log.info("sweep %s", run_once(SessionLocal))
        except Exception:  # noqa: BLE001 - a failed pass is logged and retried next tick
            log.exception("sweep failed")
        if args.once:
            return
        waited = 0
        while waited < every and not stop["now"]:
            time.sleep(1)
            waited += 1
        if stop["now"]:
            return


if __name__ == "__main__":
    main()
