"""Private portraits and video jobs, isolated from speech job recovery."""

import time
import uuid

from sqlalchemy import JSON, BigInteger, Column, Integer, String, select, update
from open_webui.internal.db import Base, get_async_db_context


class VideoRecord(Base):
    __tablename__ = 'video_studio'
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False)


def serialize(row):
    return {
        **row.data,
        'id': row.id,
        'user_id': row.user_id,
        'kind': row.kind,
        'status': row.status,
        'revision': row.revision,
        'created_at': row.created_at,
    }


async def create(user_id, kind, data, status='queued', id=None):
    async with get_async_db_context() as db:
        row = VideoRecord(
            id=id or uuid.uuid4().hex,
            user_id=user_id,
            kind=kind,
            status=status,
            data=data,
            revision=0,
            created_at=int(time.time()),
        )
        db.add(row)
        await db.commit()
        return serialize(row)


async def get(id, user_id=None):
    async with get_async_db_context() as db:
        row = await db.get(VideoRecord, id)
        if row and (user_id is None or row.user_id == user_id):
            return serialize(row)


async def listing(user_id=None, kind='job', statuses=None, limit=100, oldest=False, visible_only=False):
    async with get_async_db_context() as db:
        query = select(VideoRecord).where(VideoRecord.kind == kind)
        if user_id is not None:
            query = query.where(VideoRecord.user_id == user_id)
        if visible_only:
            query = query.where(VideoRecord.data['deleted_at'].as_integer().is_(None))
        if statuses:
            query = query.where(VideoRecord.status.in_(statuses))
        query = query.order_by(VideoRecord.created_at.asc() if oldest else VideoRecord.created_at.desc())
        rows = await db.execute(query.limit(limit))
        return [serialize(row) for row in rows.scalars()]


async def change(item, status=None, **data):
    """Compare-and-swap protects worker updates from concurrent UI actions."""
    async with get_async_db_context() as db:
        row = await db.get(VideoRecord, item['id'])
        if not row or row.revision != item['revision']:
            return None
        merged = {**row.data, **data}
        result = await db.execute(
            update(VideoRecord)
            .where(VideoRecord.id == item['id'], VideoRecord.revision == item['revision'])
            .values(data=merged, status=status or row.status, revision=row.revision + 1)
        )
        await db.commit()
        if result.rowcount == 1:
            return await get(item['id'])


async def media_records():
    """Read all media references, without pagination, for shared-asset cleanup."""
    async with get_async_db_context() as db:
        rows = await db.execute(select(VideoRecord).where(VideoRecord.kind.in_(['job', 'portrait'])))
        return [serialize(row) for row in rows.scalars()]
