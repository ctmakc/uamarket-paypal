"""initial phase a schema

Revision ID: 59c91708be4e
Revises: 
Create Date: 2026-08-31 15:40:06.969879
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '59c91708be4e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('bays',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('carrier_group', sa.String(length=60), nullable=False),
    sa.Column('inner_gate_closed', sa.Boolean(), nullable=False),
    sa.Column('outer_door_locked', sa.Boolean(), nullable=False),
    sa.Column('outer_door_closed', sa.Boolean(), nullable=False),
    sa.Column('weight_g', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bays_carrier_group'), 'bays', ['carrier_group'], unique=False)
    op.create_table('devices',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('state', sa.String(length=40), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exceptions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('reference_type', sa.String(length=40), nullable=False),
    sa.Column('reference_id', sa.String(length=120), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('details', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exceptions_kind'), 'exceptions', ['kind'], unique=False)
    op.create_index(op.f('ix_exceptions_reference_id'), 'exceptions', ['reference_id'], unique=False)
    op.create_index(op.f('ix_exceptions_state'), 'exceptions', ['state'], unique=False)
    op.create_table('locations',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_locations_kind'), 'locations', ['kind'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel', sa.String(length=40), nullable=False),
    sa.Column('external_id', sa.String(length=160), nullable=False),
    sa.Column('state', sa.String(length=40), nullable=False),
    sa.Column('gross_amount_cad', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel', 'external_id', name='uq_order_channel_external')
    )
    op.create_index(op.f('ix_orders_channel'), 'orders', ['channel'], unique=False)
    op.create_index(op.f('ix_orders_state'), 'orders', ['state'], unique=False)
    op.create_table('variants',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('sku', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('barcode', sa.String(length=120), nullable=False),
    sa.Column('price_cad', sa.Float(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_variants_barcode'), 'variants', ['barcode'], unique=True)
    op.create_index(op.f('ix_variants_sku'), 'variants', ['sku'], unique=True)
    op.create_table('webhook_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('external_event_id', sa.String(length=160), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'external_event_id', name='uq_webhook_source_event')
    )
    op.create_table('courier_pickups',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('carrier', sa.String(length=60), nullable=False),
    sa.Column('bay_id', sa.String(length=80), nullable=False),
    sa.Column('state', sa.String(length=40), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bay_id'], ['bays.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_courier_pickups_bay_id'), 'courier_pickups', ['bay_id'], unique=False)
    op.create_index(op.f('ix_courier_pickups_carrier'), 'courier_pickups', ['carrier'], unique=False)
    op.create_index(op.f('ix_courier_pickups_state'), 'courier_pickups', ['state'], unique=False)
    op.create_table('device_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('device_id', sa.String(length=80), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_events_device_id'), 'device_events', ['device_id'], unique=False)
    op.create_table('inventory_balances',
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('location_id', sa.String(length=80), nullable=False),
    sa.Column('qty_on_hand', sa.Integer(), nullable=False),
    sa.Column('qty_reserved', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('variant_id', 'location_id')
    )
    op.create_table('inventory_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('from_location_id', sa.String(length=80), nullable=True),
    sa.Column('to_location_id', sa.String(length=80), nullable=True),
    sa.Column('reference_type', sa.String(length=40), nullable=False),
    sa.Column('reference_id', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['from_location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['to_location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inventory_events_created_at'), 'inventory_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_inventory_events_event_type'), 'inventory_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_inventory_events_reference_id'), 'inventory_events', ['reference_id'], unique=False)
    op.create_index(op.f('ix_inventory_events_variant_id'), 'inventory_events', ['variant_id'], unique=False)
    op.create_table('order_lines',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('unit_price_cad', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_lines_order_id'), 'order_lines', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_lines_variant_id'), 'order_lines', ['variant_id'], unique=False)
    op.create_table('packages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('state', sa.String(length=40), nullable=False),
    sa.Column('weight_g', sa.Integer(), nullable=True),
    sa.Column('expected_label_code', sa.String(length=180), nullable=True),
    sa.Column('scanned_label_code', sa.String(length=180), nullable=True),
    sa.Column('bay_id', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['bay_id'], ['bays.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_packages_bay_id'), 'packages', ['bay_id'], unique=False)
    op.create_index(op.f('ix_packages_order_id'), 'packages', ['order_id'], unique=True)
    op.create_index(op.f('ix_packages_state'), 'packages', ['state'], unique=False)
    op.create_table('locker_access',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('pickup_id', sa.String(length=36), nullable=False),
    sa.Column('bay_id', sa.String(length=80), nullable=False),
    sa.Column('pin_hash', sa.String(length=64), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['bay_id'], ['bays.id'], ),
    sa.ForeignKeyConstraint(['pickup_id'], ['courier_pickups.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_locker_access_bay_id'), 'locker_access', ['bay_id'], unique=False)
    op.create_index(op.f('ix_locker_access_pickup_id'), 'locker_access', ['pickup_id'], unique=False)
    op.create_table('missions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('order_line_id', sa.String(length=36), nullable=False),
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('location_id', sa.String(length=80), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('scanned_barcode', sa.String(length=120), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['order_line_id'], ['order_lines.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_missions_location_id'), 'missions', ['location_id'], unique=False)
    op.create_index(op.f('ix_missions_order_id'), 'missions', ['order_id'], unique=False)
    op.create_index(op.f('ix_missions_order_line_id'), 'missions', ['order_line_id'], unique=False)
    op.create_index(op.f('ix_missions_state'), 'missions', ['state'], unique=False)
    op.create_index(op.f('ix_missions_variant_id'), 'missions', ['variant_id'], unique=False)
    op.create_table('reservations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_line_id', sa.String(length=36), nullable=False),
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('location_id', sa.String(length=80), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['order_line_id'], ['order_lines.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reservations_location_id'), 'reservations', ['location_id'], unique=False)
    op.create_index(op.f('ix_reservations_order_line_id'), 'reservations', ['order_line_id'], unique=True)
    op.create_index(op.f('ix_reservations_variant_id'), 'reservations', ['variant_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_reservations_variant_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_order_line_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_location_id'), table_name='reservations')
    op.drop_table('reservations')
    op.drop_index(op.f('ix_missions_variant_id'), table_name='missions')
    op.drop_index(op.f('ix_missions_state'), table_name='missions')
    op.drop_index(op.f('ix_missions_order_line_id'), table_name='missions')
    op.drop_index(op.f('ix_missions_order_id'), table_name='missions')
    op.drop_index(op.f('ix_missions_location_id'), table_name='missions')
    op.drop_table('missions')
    op.drop_index(op.f('ix_locker_access_pickup_id'), table_name='locker_access')
    op.drop_index(op.f('ix_locker_access_bay_id'), table_name='locker_access')
    op.drop_table('locker_access')
    op.drop_index(op.f('ix_packages_state'), table_name='packages')
    op.drop_index(op.f('ix_packages_order_id'), table_name='packages')
    op.drop_index(op.f('ix_packages_bay_id'), table_name='packages')
    op.drop_table('packages')
    op.drop_index(op.f('ix_order_lines_variant_id'), table_name='order_lines')
    op.drop_index(op.f('ix_order_lines_order_id'), table_name='order_lines')
    op.drop_table('order_lines')
    op.drop_index(op.f('ix_inventory_events_variant_id'), table_name='inventory_events')
    op.drop_index(op.f('ix_inventory_events_reference_id'), table_name='inventory_events')
    op.drop_index(op.f('ix_inventory_events_event_type'), table_name='inventory_events')
    op.drop_index(op.f('ix_inventory_events_created_at'), table_name='inventory_events')
    op.drop_table('inventory_events')
    op.drop_table('inventory_balances')
    op.drop_index(op.f('ix_device_events_device_id'), table_name='device_events')
    op.drop_table('device_events')
    op.drop_index(op.f('ix_courier_pickups_state'), table_name='courier_pickups')
    op.drop_index(op.f('ix_courier_pickups_carrier'), table_name='courier_pickups')
    op.drop_index(op.f('ix_courier_pickups_bay_id'), table_name='courier_pickups')
    op.drop_table('courier_pickups')
    op.drop_table('webhook_events')
    op.drop_index(op.f('ix_variants_sku'), table_name='variants')
    op.drop_index(op.f('ix_variants_barcode'), table_name='variants')
    op.drop_table('variants')
    op.drop_index(op.f('ix_orders_state'), table_name='orders')
    op.drop_index(op.f('ix_orders_channel'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_locations_kind'), table_name='locations')
    op.drop_table('locations')
    op.drop_index(op.f('ix_exceptions_state'), table_name='exceptions')
    op.drop_index(op.f('ix_exceptions_reference_id'), table_name='exceptions')
    op.drop_index(op.f('ix_exceptions_kind'), table_name='exceptions')
    op.drop_table('exceptions')
    op.drop_table('devices')
    op.drop_index(op.f('ix_bays_carrier_group'), table_name='bays')
    op.drop_table('bays')
