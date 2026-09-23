#!/usr/bin/env python3
"""Copy only the five tagged local demo schools to a remote PostgreSQL database.

This deliberately does not copy users, password hashes, audit logs, LINE IDs,
or the separate sales demo leads. Re-running is additive and idempotent.

From backend/: python scripts/promote_local_mockup.py         # local preview
               python scripts/promote_local_mockup.py --apply # secure prompt
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import (
    Device, DeviceHealthFlag, Organization, PMPlan, PMTask, RepairTicket,
    Room, SessionLocal, TicketUpdate,
)
from scripts.demo_safety import require_local_demo_database

SCHOOL_CODES = tuple(f"SCH-M{n:02d}" for n in range(1, 6))


def values(row, *, omit=(), **overrides):
    data = {column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name not in {"id", *omit}}
    data.update(overrides)
    return data


def source_data(source):
    schools = source.scalars(select(Organization).where(Organization.code.in_(SCHOOL_CODES))).all()
    if {school.code for school in schools} != set(SCHOOL_CODES):
        raise RuntimeError("Local database does not contain all five SCH-M01..SCH-M05 schools")
    ids = [school.id for school in schools]
    rooms = source.scalars(select(Room).where(Room.organization_id.in_(ids))).all()
    devices = source.scalars(select(Device).where(Device.organization_id.in_(ids))).all()
    tickets = source.scalars(select(RepairTicket).where(RepairTicket.organization_id.in_(ids))).all()
    updates = source.scalars(select(TicketUpdate).where(
        TicketUpdate.ticket_id.in_([ticket.id for ticket in tickets]))).all()
    tasks = source.scalars(select(PMTask).where(PMTask.organization_id.in_(ids))).all()
    plans = source.scalars(select(PMPlan).where(
        PMPlan.id.in_([task.plan_id for task in tasks if task.plan_id is not None]))).all()
    flags = source.scalars(select(DeviceHealthFlag).where(
        DeviceHealthFlag.organization_id.in_(ids))).all()
    return schools, rooms, devices, tickets, updates, plans, tasks, flags


def copy_data(target, data):
    schools, rooms, devices, tickets, updates, plans, tasks, flags = data
    org_ids, room_ids, ticket_ids, plan_ids = {}, {}, {}, {}
    created = {name: 0 for name in (
        "schools", "rooms", "devices", "tickets", "updates", "plans", "tasks", "flags")}

    for school in schools:
        row = target.scalar(select(Organization).where(Organization.code == school.code))
        if row is not None and row.name != school.name:
            raise RuntimeError(f"School code collision: {school.code}")
        if row is None:
            row = Organization(**values(school))
            target.add(row)
            target.flush()
            created["schools"] += 1
        org_ids[school.id] = row.id

    for room in rooms:
        org_id = org_ids[room.organization_id]
        row = target.scalar(select(Room).where(Room.organization_id == org_id, Room.code == room.code))
        if row is not None and row.name != room.name:
            raise RuntimeError(f"Room code collision: {room.code}")
        if row is None:
            row = Room(**values(room, organization_id=org_id))
            target.add(row)
            target.flush()
            created["rooms"] += 1
        room_ids[room.id] = row.id

    for device in devices:
        org_id = org_ids[device.organization_id]
        row = target.scalar(select(Device).where(Device.device_id == device.device_id))
        if row is not None and row.organization_id != org_id:
            raise RuntimeError(f"Device ID collision: {device.device_id}")
        if row is None:
            row = Device(**values(device, organization_id=org_id,
                                  room_id=room_ids.get(device.room_id),
                                  qr_token=secrets.token_hex(16)))
            target.add(row)
            created["devices"] += 1
    target.flush()

    new_ticket_ids = set()
    for ticket in tickets:
        org_id = org_ids[ticket.organization_id]
        row = target.scalar(select(RepairTicket).where(RepairTicket.ticket_id == ticket.ticket_id))
        if row is not None and row.organization_id != org_id:
            raise RuntimeError(f"Ticket ID collision: {ticket.ticket_id}")
        if row is None:
            row = RepairTicket(**values(ticket, organization_id=org_id,
                                        assigned_to=None))
            target.add(row)
            target.flush()
            new_ticket_ids.add(ticket.id)
            created["tickets"] += 1
        ticket_ids[ticket.id] = row.id
    for update in updates:
        if update.ticket_id in new_ticket_ids:
            target.add(TicketUpdate(**values(update, ticket_id=ticket_ids[update.ticket_id])))
            created["updates"] += 1

    for plan in plans:
        row = target.scalar(select(PMPlan).where(PMPlan.name == plan.name,
                                                  PMPlan.device_type == plan.device_type,
                                                  PMPlan.interval_days == plan.interval_days))
        if row is None:
            row = PMPlan(**values(plan))
            target.add(row)
            target.flush()
            created["plans"] += 1
        plan_ids[plan.id] = row.id

    for task in tasks:
        org_id = org_ids[task.organization_id]
        row = target.scalar(select(PMTask).where(PMTask.task_no == task.task_no))
        if row is not None and row.organization_id != org_id:
            raise RuntimeError(f"PM task collision: {task.task_no}")
        if row is None:
            target.add(PMTask(**values(task, organization_id=org_id,
                                       plan_id=plan_ids.get(task.plan_id), done_by=None)))
            created["tasks"] += 1

    for flag in flags:
        org_id = org_ids[flag.organization_id]
        row = target.scalar(select(DeviceHealthFlag).where(
            DeviceHealthFlag.device_id == flag.device_id,
            DeviceHealthFlag.rule_code == flag.rule_code,
            DeviceHealthFlag.message == flag.message))
        if row is None:
            target.add(DeviceHealthFlag(**values(flag, organization_id=org_id,
                                                 acknowledged_by=None)))
            created["flags"] += 1
    target.flush()
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="prompt for remote URL and commit")
    args = parser.parse_args()
    require_local_demo_database()
    with SessionLocal() as source:
        data = source_data(source)
        names = ("schools", "rooms", "devices", "tickets", "updates", "plans", "tasks", "flags")
        print("Local demo preview:", ", ".join(
            f"{name}={len(rows)}" for name, rows in zip(names, data)))
        print("Excludes users, passwords, audit logs and sales demo leads.")
        if not args.apply:
            return
        raw_url = getpass.getpass("Paste production DATABASE_URL (hidden): ").strip()
        try:
            url = make_url(raw_url)
        except Exception as exc:
            raise SystemExit("Invalid PostgreSQL URL") from exc
        if not url.drivername.startswith("postgresql") or not url.host or url.host.lower() in {
            "localhost", "127.0.0.1", "::1", "postgres"}:
            raise SystemExit("Target must be a remote PostgreSQL database")
        print(f"Target host: {url.host}; database: {url.database}")
        if input("Type COPY FIVE DEMO SCHOOLS to commit: ").strip() != "COPY FIVE DEMO SCHOOLS":
            raise SystemExit("Cancelled; target unchanged")
        remote = create_engine(url, pool_pre_ping=True,
                               connect_args={"connect_timeout": 15, "sslmode": "require"})
        try:
            TargetSession = sessionmaker(bind=remote, expire_on_commit=False)
            with TargetSession.begin() as target:
                created = copy_data(target, data)
            print("Committed:", ", ".join(f"{key}={value}" for key, value in created.items()))
        finally:
            remote.dispose()


if __name__ == "__main__":
    main()
