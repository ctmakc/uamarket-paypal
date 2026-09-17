from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bay, Device, Location, Variant


def seed(db: Session):
    variants = [
        ("UA-W-BLACK-M", "Women's Ukrainian-inspired blouse Black / M", "620640001001", 79.99),
        ("UA-M-WHITE-L", "Men's embroidered shirt White / L", "620520001002", 94.99),
        ("UA-KIDS-BLUE-8", "Kids embroidered shirt Blue / 8", "620630001003", 49.99),
        ("UA-RUNNER-RED", "Embroidered table runner Red", "630253001004", 39.99),
        ("UA-MOTANKA-KYIV", "Motanka doll Kyiv region", "950300001005", 59.99),
    ]
    for sku, name, barcode, price in variants:
        if not db.scalar(select(Variant).where(Variant.sku == sku)):
            db.add(Variant(sku=sku, name=name, barcode=barcode, price_cad=price))

    for loc_id, kind in [
        ("A-LANE-01", "A_LANE"), ("A-LANE-02", "A_LANE"),
        ("B-BIN-001", "B_BIN"), ("B-BIN-002", "B_BIN"),
        ("RESERVE-R01-S01-B01", "RESERVE"), ("EXCEPTION-01", "EXCEPTION"),
    ]:
        if not db.get(Location, loc_id): db.add(Location(id=loc_id, kind=kind))

    for bay_id, carrier in [("BAY-CP", "CANADA_POST"), ("BAY-OTHER", "OTHER"), ("BAY-OVERFLOW", "OVERFLOW")]:
        if not db.get(Bay, bay_id): db.add(Bay(id=bay_id, carrier_group=carrier))

    for dev_id, kind in [("SCANNER-01", "SCANNER"), ("SCALE-01", "SCALE"), ("LOCKER-01", "LOCKER"), ("DISPENSER-SIM", "DISPENSER"), ("ROBOT-SIM", "ROBOT")]:
        if not db.get(Device, dev_id): db.add(Device(id=dev_id, kind=kind))
