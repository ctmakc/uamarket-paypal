from __future__ import annotations

import os

from fastapi import FastAPI

from .db import Base, make_engine, make_session_factory
from .api import admin, admin_catalog, admin_orders, agents, orders, shipping, edge, storefront
from .services.storefront import check_payment_configuration


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(database_url: str | None = None, create_schema: bool | None = None) -> FastAPI:
    """Build the API.

    The schema belongs to Alembic (`alembic upgrade head` runs before Uvicorn in the
    container). `create_all` runs only for local insecure development, or when a caller
    such as a test asks for it explicitly, so a deployment can never drift from its
    migrations by starting against an empty database.
    """
    check_payment_configuration()
    engine = make_engine(database_url)
    SessionLocal = make_session_factory(engine)
    if create_schema is None:
        create_schema = _truthy(os.getenv("ALLOW_INSECURE_DEV"))
    if create_schema:
        import app.edge_models  # noqa: F401  - registers edge tables on Base.metadata
        Base.metadata.create_all(engine)
    app = FastAPI(title="UA Market — fulfillment API", version="0.9.0")
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.include_router(admin.router)
    app.include_router(orders.router)
    app.include_router(shipping.router)
    app.include_router(edge.router)
    app.include_router(storefront.router)
    app.include_router(admin_catalog.router)
    app.include_router(admin_catalog.media_router)
    app.include_router(admin_orders.router)
    app.include_router(agents.router)
    return app


app = create_app()
