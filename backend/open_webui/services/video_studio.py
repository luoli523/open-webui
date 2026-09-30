"""Durable provider-neutral video workflow; every paid submit has a saved intent."""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from open_webui.models import audio_studio as audio_records, video_studio as records
from open_webui.models.config import Config
from open_webui.services import audio_studio as audio, video_media as media
from open_webui.services.video_providers import PROVIDERS, provider_for
from open_webui.services.video_providers.base import ProviderError, SubmissionUnknown

log = logging.getLogger(__name__)
ACTIVE = ['queued', 'preparing', 'submitting', 'processing', 'downloading']
PUBLIC_FIELDS = (
    'id',
    'status',
    'created_at',
    'revision',
    'name',
    'default_voice_id',
    'version',
    'width',
    'height',
    'input_type',
    'title',
    'credit',
    'portrait_name',
    'audio_job_id',
    'provider_id',
    'aspect_ratio',
    'resolution',
    'stage',
    'preview_id',
    'duration',
    'full_duration',
    'error',
    'external_id',
    'fingerprint',
    'job_id',
    'message_id',
    'approved_at',
    'attempt',
)


def public(item):
    result = {k: item[k] for k in PUBLIC_FIELDS if k in item}
    if item['kind'] == 'job':
        result['retry_requires_payment'] = not item.get('external_id') or bool(item.get('remote_failed'))
    return result


async def owned(id, user, kind='job'):
    item = await records.get(id, user.id)
    if not item or item['kind'] != kind or item.get('deleted_at'):
        raise HTTPException(404, '记录不存在')
    return item


async def restore_record(item):
    # Reusing identical inputs restores the original task, never creates a paid duplicate.
    if item.get('deleted_at'):
        item = await records.change(item, deleted_at=None)
        if not item:
            raise HTTPException(409, '记录已变化，请刷新重试')
    return item


async def settings():
    return await Config.get('video.studio.settings', {}) or {}


async def configuration(version):
    config = await Config.get('video.studio.credentials.' + version)
    if not isinstance(config, dict):
        raise ProviderError('该任务的引擎配置不可用，请联系管理员')
    return config


async def save_settings(api_key, enabled):
    old = await settings()
    version = old.get('config_version')
    if api_key is not None:
        if not api_key.strip() or '\n' in api_key or '\r' in api_key:
            raise HTTPException(400, '请输入有效的 HeyGen API Key')
        version = uuid.uuid4().hex
        await Config.upsert({'video.studio.credentials.' + version: {'api_key': api_key.strip()}})
    if enabled and not version:
        raise HTTPException(400, '请先保存 HeyGen API Key')
    await Config.upsert(
        {'video.studio.settings': dict(enabled=enabled, default_provider='heygen', config_version=version)}
    )


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


async def create_preview(user, form):
    config = await settings()
    if not config.get('enabled') or not config.get('config_version'):
        raise HTTPException(409, '请管理员先配置并启用视频引擎')
    if form.provider_id not in PROVIDERS:
        raise HTTPException(400, '视频引擎尚未安装')
    caps = PROVIDERS[form.provider_id].capabilities
    if form.aspect_ratio not in caps['aspect_ratios']:
        raise HTTPException(400, '该引擎不支持此画面比例')
    portrait = await owned(form.portrait_id, user, 'portrait')
    if portrait['status'] != 'active' or portrait['input_type'] not in caps['input_types']:
        raise HTTPException(409, '人物已删除或素材不适用于当前引擎')
    source_job = await audio_records.get(form.audio_job_id, user.id)
    if not source_job or source_job['kind'] != 'job' or source_job['status'] != 'completed':
        raise HTTPException(400, '请选择已完成的播报')
    source = audio.audio_path(source_job['id'])
    if not source.is_file():
        raise HTTPException(404, '播报音频不存在')
    try:
        duration, streams = await media.probe(source)
    except (ValueError, FileNotFoundError):
        raise HTTPException(400, '无法读取配音，请检查文件及 FFmpeg') from None
    if duration > caps['max_duration_seconds'] or source.stat().st_size > caps['max_asset_bytes']:
        raise HTTPException(400, '首版视频支持不超过 5 分钟、32 MB 的播报')
    digest = await asyncio.to_thread(media.digest, source)
    inputs = dict(
        portrait_asset=portrait['asset'],
        portrait_hash=portrait['asset_hash'],
        portrait_version=portrait['version'],
        audio_hash=digest,
        audio_job_id=source_job['id'],
        provider_id=form.provider_id,
        config_version=config['config_version'],
        aspect_ratio=form.aspect_ratio,
        preview_resolution=caps['preview_resolution'],
        final_resolution=caps['final_resolution'],
    )
    stamp = fingerprint(inputs)
    # Same immutable inputs have one preview; repeat paid generation is an explicit retry action.
    id = fingerprint({'user': user.id, 'preview': stamp})
    existing = await records.get(id, user.id)
    if existing:
        return await restore_record(existing)
    waiting = await records.listing(user.id, statuses=ACTIVE, limit=8)
    if len(waiting) >= 8:
        raise HTTPException(429, '视频任务过多，请稍后再试')
    snapshot = media.path(digest + '.mp3')
    if not snapshot.is_file():
        source_bytes = await asyncio.to_thread(source.read_bytes)
        await asyncio.to_thread(media.atomic_bytes, snapshot, source_bytes)
    data = dict(
        **inputs,
        title=source_job['title'],
        credit=source_job.get('credit'),
        portrait_name=portrait['name'],
        audio_asset=snapshot.name,
        full_duration=duration,
        duration=min(15, duration),
        stage='preview',
        resolution=caps['preview_resolution'],
        fingerprint=stamp,
        consent_at=int(time.time()),
        assets={},
        attempt=1,
        next_poll=0,
    )
    try:
        return await records.create(user.id, 'job', data, id=id)
    except IntegrityError:
        return await records.get(id, user.id)


async def create_final(user, preview, expected_fingerprint):
    if preview['stage'] != 'preview' or preview['status'] != 'completed':
        raise HTTPException(409, '请先完成并观看预览')
    if expected_fingerprint != preview['fingerprint']:
        raise HTTPException(409, '预览内容已变化，请重新确认')
    config = await settings()
    if not config.get('enabled'):
        raise HTTPException(409, '管理员已暂停新的视频生成')
    id = fingerprint({'preview': preview['id'], 'attempt': preview['attempt'], 'stage': 'final'})
    existing = await records.get(id, user.id)
    if existing:
        return await restore_record(existing)
    fields = (
        'portrait_asset',
        'portrait_hash',
        'portrait_version',
        'audio_hash',
        'audio_job_id',
        'provider_id',
        'config_version',
        'aspect_ratio',
        'preview_resolution',
        'final_resolution',
        'title',
        'portrait_name',
        'audio_asset',
        'full_duration',
        'fingerprint',
    )
    data = {k: preview[k] for k in fields}
    data.update(
        credit=preview.get('credit'),
        stage='final',
        preview_id=preview['id'],
        resolution=preview['final_resolution'],
        duration=preview['full_duration'],
        approved_at=int(time.time()),
        approved_by=user.id,
        assets={'portrait': preview['assets']['portrait']},
        attempt=1,
        next_poll=0,
    )
    try:
        return await records.create(user.id, 'job', data, id=id)
    except IntegrityError:
        return await records.get(id, user.id)


async def retry(job, paid=False):
    if job['status'] != 'failed':
        raise HTTPException(409, '当前状态不能重试；提交结果待核实的任务须先核对')
    if job.get('external_id') and not job.get('remote_failed'):
        updated = await records.change(job, 'processing', error=None, next_poll=0, failures=0)
    else:
        if not paid:
            raise HTTPException(400, '重新生成可能产生费用，请明确确认')
        if not (await settings()).get('enabled'):
            raise HTTPException(409, '管理员已暂停新的视频生成')
        updated = await records.change(
            job,
            'queued',
            external_id=None,
            remote_failed=False,
            error=None,
            next_poll=0,
            failures=0,
            attempt=job['attempt'] + 1,
        )
    if not updated:
        raise HTTPException(409, '任务状态已变化，请刷新')
    return updated


async def execute(job):
    try:
        provider = provider_for(job['provider_id'], await configuration(job['config_version']))
        if job['status'] == 'queued':
            job = await records.change(job, 'preparing', error=None)
            if not job:
                return
            portrait = media.path(job['portrait_asset'])
            full_audio = media.path(job['audio_asset'])
            if (
                await asyncio.to_thread(media.digest, portrait) != job['portrait_hash']
                or await asyncio.to_thread(media.digest, full_audio) != job['audio_hash']
            ):
                raise ProviderError('素材校验失败，无法继续生成')
            target = full_audio
            if job['stage'] == 'preview':
                target = media.path(job['id'] + '-preview.mp3')
                duration = await media.preview_audio(full_audio, target)
                job = await records.change(job, duration=duration)
                if not job:
                    return
            for key, file, mime in [('portrait', portrait, 'image/jpeg'), ('audio', target, 'audio/mpeg')]:
                if not job['assets'].get(key):
                    external_asset = await provider.prepare_asset(file, mime)
                    job = await records.change(job, assets={**job['assets'], key: external_asset})
                    if not job:
                        return
            job = await records.change(job, 'submitting', submitted_at=int(time.time()))
            if not job:
                return
            external_id = await provider.submit(job, job['assets'])
            job = await records.change(job, 'processing', external_id=external_id, next_poll=int(time.time()) + 10)
            return
        if job['status'] == 'processing':
            result = await provider.poll(job['external_id'])
            if result['state'] == 'failed':
                await records.change(
                    job, 'failed', remote_failed=True, error='引擎报告生成失败，请到引擎后台核对原因和扣费'
                )
            elif result['state'] == 'completed':
                job = await records.change(job, 'downloading')
                if not job:
                    return
                target = media.path(job['id'] + '.mp4')
                temp = media.path(job['id'] + '.tmp.mp4')
                try:
                    await provider.fetch_result(result, temp)
                    os.chmod(temp, 0o600)
                    await media.validate_video(temp, job['duration'])
                    video_hash = await asyncio.to_thread(media.digest, temp)
                    os.replace(temp, target)
                    await records.change(job, 'completed', video_hash=video_hash, error=None, failures=0)
                finally:
                    temp.unlink(missing_ok=True)
            else:
                await records.change(job, next_poll=int(time.time()) + 15, failures=0, error=None)
    except asyncio.CancelledError:
        # Startup recovery resolves the saved stage; never silently resubmit an uncertain POST.
        raise
    except Exception as exc:
        current = await records.get(job['id'])
        if not current:
            return
        message = (
            str(exc) if isinstance(exc, (ProviderError, ValueError)) else '视频处理异常，请检查素材、配置和服务状态'
        )
        if current['status'] == 'submitting':
            state = (
                'failed'
                if isinstance(exc, ProviderError) and not isinstance(exc, SubmissionUnknown)
                else 'submission_unknown'
            )
            await records.change(current, state, error=message)
        elif current.get('external_id') and current['status'] in ('processing', 'downloading'):
            failures = current.get('failures', 0) + 1
            await records.change(
                current,
                'processing' if failures < 5 else 'failed',
                error=message,
                failures=failures,
                next_poll=int(time.time()) + min(300, 15 * 2**failures),
            )
        else:
            await records.change(current, 'failed', error=message)
        log.warning('Video job %s failed at %s (%s)', current['id'], current['status'], type(exc).__name__)


async def worker():
    import fcntl

    with (media.directory() / 'worker.lock').open('a') as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        for item in await records.listing(statuses=['preparing', 'submitting', 'downloading'], limit=10000):
            state = {'preparing': 'queued', 'submitting': 'submission_unknown', 'downloading': 'processing'}[
                item['status']
            ]
            await records.change(
                item,
                state,
                next_poll=0,
                error='服务重启时提交结果不明，请到 HeyGen 核对任务' if state == 'submission_unknown' else None,
            )
        for item in await records.listing(kind='delivery', statuses=['sending'], limit=10000):
            await records.change(item, 'unknown', error='服务重启，请到 Telegram 核对收件结果')
        while True:
            try:
                jobs = await records.listing(statuses=['queued', 'processing'], limit=10000, oldest=True)
                for job in jobs:
                    if job.get('next_poll', 0) <= time.time():
                        await execute(job)
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('Video worker unavailable (%s)', type(exc).__name__)
                await asyncio.sleep(5)
