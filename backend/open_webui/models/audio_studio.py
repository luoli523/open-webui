"""Persistent speech jobs and Telegram delivery receipts."""

import time
import uuid

from open_webui.internal.db import Base, get_async_db_context
from sqlalchemy import JSON, BigInteger, Column, String, select, update


class StudioRecord(Base):
    __tablename__ = 'audio_studio'
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    created_at = Column(BigInteger, nullable=False)


def serialize(row):
    return dict(id=row.id, user_id=row.user_id, kind=row.kind, status=row.status, created_at=row.created_at, **row.data)


async def create(user_id, kind, data, status='queued', id=None):
    async with get_async_db_context() as db:
        row = StudioRecord(
            id=id or uuid.uuid4().hex, user_id=user_id, kind=kind, status=status, data=data, created_at=int(time.time())
        )
        db.add(row)
        await db.commit()
        return serialize(row)


async def get(id, user_id=None):
    async with get_async_db_context() as db:
        row = await db.get(StudioRecord, id)
        if not row or (user_id is not None and row.user_id != user_id):
            return None
        return serialize(row)


async def listing(user_id=None, kind='job', status=None, limit=50):
    async with get_async_db_context() as db:
        query = select(StudioRecord).where(StudioRecord.kind == kind)
        if user_id is not None:
            query = query.where(StudioRecord.user_id == user_id)
        if status:
            query = query.where(StudioRecord.status == status)
        result = await db.execute(query.order_by(StudioRecord.created_at.desc()).limit(limit))
        return [serialize(r) for r in result.scalars()]


async def transition(id, before, after, **data):
    async with get_async_db_context() as db:
        row = await db.get(StudioRecord, id)
        if not row or row.status not in before:
            return False
        result = await db.execute(
            update(StudioRecord)
            .where(StudioRecord.id == id, StudioRecord.status.in_(before))
            .values(status=after, data={**row.data, **data})
        )
        await db.commit()
        return result.rowcount == 1


async def recover():
    async with get_async_db_context() as db:
        await db.execute(
            update(StudioRecord)
            .where(StudioRecord.kind.in_(['job', 'sample']), StudioRecord.status == 'running')
            .values(status='interrupted')
        )
        await db.execute(
            update(StudioRecord)
            .where(StudioRecord.kind == 'delivery', StudioRecord.status == 'sending')
            .values(status='unknown')
        )
        await db.commit()
