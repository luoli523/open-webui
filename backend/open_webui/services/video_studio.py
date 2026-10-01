"""Durable provider-neutral video workflow; every paid submit has a saved intent."""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from open_webui.models import audio_studio as audio_records, video_studio as records
from open_webui.models.config import Config
from open_webui.services import audio_studio as audio, video_media as media
from open_webui.services.video_providers import PROVIDERS, provider_for
from open_webui.services.video_providers.base import ProviderError, SubmissionUnknown

log = logging.getLogger(__name__)
ACTIVE = ['queued', 'preparing', 'submitting', 'processing', 'downloading', 'cancelling']
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
    'variant',
    'artifact_hash',
    'auto_captions',
    'approved_at',
    'attempt',
    'steps', 'seed', 'preview_start', 'preview_seconds', 'progress', 'can_generate_final',
    'estimated_seconds',
)


def public(item):
    result = {k: item[k] for k in PUBLIC_FIELDS if k in item}
    if item['kind'] == 'job':
        result['retry_requires_payment'] = item.get('provider_id') != 'local_h3' and (not item.get('external_id') or bool(item.get('remote_failed')))
    return result


async def owned(id, user, kind='job'):
    item = await records.get(id, user.id)
    if not item or item['kind'] != kind or item.get('deleted_at'):
        raise HTTPException(404, '记录不存在')
    return item


@asynccontextmanager
async def asset_lock():
    # Serialize creation and cleanup across server processes.
    import fcntl

    with (media.directory() / 'assets.lock').open('a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def available_id(id, user_id):
    existing = await records.get(id, user_id)
    while existing and existing.get('deleted_at'):
        id = fingerprint({'recreate_after': id})
        existing = await records.get(id, user_id)
    return id, existing


async def cleanup_deleted():
    async with asset_lock():
        items = await records.media_records()
        referenced = set()
        for item in items:
            if item['kind'] == 'portrait' and item['status'] == 'active':
                referenced.add(item.get('asset'))
            elif item['kind'] == 'job' and not item.get('deleted_at'):
                referenced.update([item.get('audio_asset'), item.get('portrait_asset')])
        freed = 0
        for item in items:
            if item['kind'] != 'job' or not item.get('deleted_at'):
                continue
            names = [
                item['id'] + suffix
                for suffix in (
                    '.mp4',
                    '.tmp.mp4',
                    '-preview.mp3',
                    '-preview.mp3.tmp.mp3',
                    '-thumb.jpg',
                    '-thumb.tmp.jpg',
                )
            ]
            names.extend(file.name for file in media.directory().glob(item['id'] + '-caption*') if file.is_file())
            names.extend(
                name
                for name in (item.get('audio_asset'), item.get('portrait_asset'))
                if name and name not in referenced
            )
            for name in names:
                target = media.path(name)
                try:
                    size = target.stat().st_size
                    target.unlink()
                    freed += size
                except FileNotFoundError:
                    pass
        return freed


async def delete_record(id, user):
    async with asset_lock():
        item = await owned(id, user)
        if item['status'] not in ('completed', 'failed', 'cancelled'):
            raise HTTPException(409, '请等待生成结束，或先核实提交结果，再删除记录')
        from open_webui.services.video_captions import identifier

        caption = await records.get(identifier(id), user.id)
        if caption and caption['status'] in ('queued', 'running'):
            raise HTTPException(409, '请等待字幕处理完成后删除视频')
        deliveries = await records.listing(user.id, kind='delivery', statuses=['sending', 'unknown'], limit=10000)
        if any(receipt.get('job_id') == id for receipt in deliveries):
            raise HTTPException(409, '请等待 TG 发送完成，或先核实发送结果，再删除记录')
        if not await records.change(item, deleted_at=int(time.time())):
            raise HTTPException(409, '任务状态已变化，请刷新后重试')
    try:
        return {'ok': True, 'freed_bytes': await cleanup_deleted(), 'cleanup_pending': False}
    except OSError:
        log.warning('Video cleanup deferred; worker will retry')
        return {'ok': True, 'freed_bytes': 0, 'cleanup_pending': True}


async def settings(provider='heygen'):
    key = 'video.studio.local_h3' if provider == 'local_h3' else 'video.studio.settings'
    return await Config.get(key, {}) or {}


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


async def save_local_settings(url, enabled):
    from open_webui.services.video_providers.local_h3 import base_url
    try:
        url = base_url(url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    config = {'base_url': url}
    if enabled:
        try:
            caps = await provider_for('local_h3', config).request('GET', '/v1/video/capabilities')
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from None
        if not caps.get('ready'):
            raise HTTPException(409, '本地 H3 模型尚未准备好')
    version = uuid.uuid4().hex
    await Config.upsert({'video.studio.credentials.'+version: config,
                         'video.studio.local_h3': dict(enabled=enabled, config_version=version, base_url=url)})


async def cancel_local(job):
    if job['provider_id'] != 'local_h3':
        raise HTTPException(409, '该引擎不支持取消')
    if job['status'] in ('completed', 'failed', 'cancelled') and not job.get('submission_pending'):
        return job
    # CAS prevents the worker from proceeding after a preparation cancellation.
    updated = await records.change(job, 'cancelling' if job.get('external_id') or job.get('submission_pending') or job['status'] == 'submitting' else 'cancelled')
    if not updated:
        raise HTTPException(409, '任务状态已变化，请刷新后重试')
    if updated.get('external_id'):
        try:
            await provider_for('local_h3', await configuration(job['config_version'])).cancel(job['external_id'])
        except ProviderError as exc:
            # The worker will retry cancellation with the durable external ID.
            await records.change(updated, error=str(exc))
    return await records.get(job['id'])


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


async def create_preview(user, form):
    async with asset_lock():
        return await _create_preview(user, form)


async def _create_preview(user, form):
    config = await settings(form.provider_id)
    if not config.get('enabled') or not config.get('config_version'):
        raise HTTPException(409, '请管理员先配置并启用视频引擎')
    if form.provider_id not in PROVIDERS:
        raise HTTPException(400, '视频引擎尚未安装')
    caps = dict(PROVIDERS[form.provider_id].capabilities)
    if form.provider_id == 'local_h3':
        try:
            caps.update(await provider_for('local_h3', await configuration(config['config_version'])).request('GET', '/v1/video/capabilities'))
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from None
        if not caps.get('ready') or form.steps not in caps.get('supported_steps', []):
            raise HTTPException(422, 'H3 未就绪或不支持所选步数')
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
    if duration > (300 if form.provider_id == 'local_h3' else caps['max_duration_seconds']) or source.stat().st_size > caps['max_asset_bytes']:
        raise HTTPException(400, '首版视频支持不超过 5 分钟、32 MB 的播报')
    if form.provider_id == 'local_h3' and duration - form.preview_start < 2:
        raise HTTPException(422, '预览起点后需至少保留 2 秒音频')
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
    if form.provider_id == 'local_h3':
        inputs.update(steps=form.steps, seed=42, preview_start=form.preview_start,
                      preview_seconds=min(form.preview_seconds, duration-form.preview_start))
    stamp = fingerprint(inputs)
    # Same immutable inputs have one preview; repeat paid generation is an explicit retry action.
    id = fingerprint({'user': user.id, 'preview': stamp})
    id, existing = await available_id(id, user.id)
    if existing:
        if not existing.get('auto_captions'):
            return await records.change(existing, auto_captions=True) or existing
        return existing
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
        source_text=source_job.get('text', ''),
        auto_captions=True,
        credit=source_job.get('credit'),
        portrait_name=portrait['name'],
        audio_asset=snapshot.name,
        full_duration=duration,
        duration=inputs.get('preview_seconds', min(15, duration)),
        can_generate_final=form.provider_id != 'local_h3' or bool(caps.get('long_video_enabled')) or duration <= 15,
        estimated_seconds=(inputs.get('preview_seconds', min(15, duration)) / (107/24) * {8:430,12:626,20:1003}[form.steps]) if form.provider_id == 'local_h3' else None,
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
    async with asset_lock():
        preview = await owned(preview['id'], user)
        return await _create_final(user, preview, expected_fingerprint)


async def _create_final(user, preview, expected_fingerprint):
    if preview['stage'] != 'preview' or preview['status'] != 'completed':
        raise HTTPException(409, '请先完成并观看预览')
    if expected_fingerprint != preview['fingerprint']:
        raise HTTPException(409, '预览内容已变化，请重新确认')
    config = await settings(preview['provider_id'])
    if preview['provider_id'] == 'local_h3' and not preview.get('can_generate_final'):
        raise HTTPException(409, '长片分段尚未启用，请先使用短片预览')
    if not config.get('enabled'):
        raise HTTPException(409, '管理员已暂停新的视频生成')
    id = fingerprint({'preview': preview['id'], 'attempt': preview['attempt'], 'stage': 'final'})
    id, existing = await available_id(id, user.id)
    if existing:
        if not existing.get('auto_captions'):
            return await records.change(existing, auto_captions=True) or existing
        return existing
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
    if preview['provider_id'] == 'local_h3':
        data.update(steps=preview['steps'], seed=preview.get('seed',42), can_generate_final=True)
    data.update(
        credit=preview.get('credit'),
        source_text=preview.get('source_text', ''),
        auto_captions=True,
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
    if job['provider_id'] == 'local_h3' and job['status'] in ('failed','cancelled'):
        if not (await settings('local_h3')).get('enabled'):
            raise HTTPException(409, '本地 H3 已暂停新任务')
        if job.get('external_id'):
            provider = provider_for('local_h3', await configuration(job['config_version']))
            result = await provider.poll(job['external_id'])
            if result['state'] in ('failed','cancelled'):
                await provider.retry(job['external_id'])
            return await records.change(job, 'processing', error=None, remote_failed=False, failures=0, next_poll=0)
        return await records.change(job, 'queued', error=None, failures=0, next_poll=0)
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
        if job['status'] == 'cancelling':
            if not job.get('external_id'):
                external_id = await provider.submit(job, job['assets'])
                job = await records.change(job, external_id=external_id, submission_pending=False)
                if not job:
                    return
            await provider.cancel(job['external_id'])
            result = await provider.poll(job['external_id'])
            if result['state'] in ('cancelled','failed','completed'):
                await records.change(job, 'cancelled', error=None, submission_pending=False)
            return
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
                if job['provider_id'] == 'local_h3':
                    duration = await media.local_preview_audio(full_audio, target, job.get('preview_start',0), job.get('preview_seconds',5))
                else:
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
            job = await records.change(job, 'submitting', submitted_at=int(time.time()), submission_pending=job['provider_id']=='local_h3')
            if not job:
                return
            external_id = await provider.submit(job, job['assets'])
            updated = await records.change(job, 'processing', external_id=external_id, submission_pending=False, next_poll=int(time.time()) + 10)
            if not updated and job['provider_id'] == 'local_h3':
                current = await records.get(job['id'])
                if current and current['status'] in ('cancelled','cancelling'):
                    await records.change(current, 'cancelling', external_id=external_id, submission_pending=False)
                    await provider.cancel(external_id)
            return
        if job['status'] == 'processing':
            result = await provider.poll(job['external_id'])
            if result['state'] == 'cancelled':
                await records.change(job, 'cancelled', error=None, submission_pending=False)
            elif result['state'] == 'failed':
                await records.change(
                    job, 'failed', remote_failed=True, error=result.get('error') or ('本地任务中断或失败，可重试未完成片段' if job['provider_id']=='local_h3' else '引擎报告生成失败，请到引擎后台核对原因和扣费')
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
                    expected_duration = result.get('duration') if job['provider_id'] == 'local_h3' else job['duration']
                    await media.validate_video(temp, expected_duration or job['duration'])
                    video_hash = await asyncio.to_thread(media.digest, temp)
                    os.replace(temp, target)
                    await records.change(job, 'completed', video_hash=video_hash, error=None, failures=0, duration=expected_duration or job['duration'])
                finally:
                    temp.unlink(missing_ok=True)
            else:
                await records.change(job, next_poll=int(time.time()) + (3 if job['provider_id']=='local_h3' else 15), failures=0, error=None, progress=result.get('progress'))
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
        if current['status'] in ('cancelled', 'cancelling'):
            return
        if current['status'] == 'submitting' and current['provider_id'] == 'local_h3':
            uncertain = isinstance(exc, SubmissionUnknown) or not isinstance(exc, ProviderError)
            await records.change(current, 'queued' if uncertain else 'failed',
                                 submission_pending=uncertain, error=message, next_poll=int(time.time())+5)
            return
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
            if item.get('provider_id') == 'local_h3' and state == 'submission_unknown':
                state = 'queued'  # replay the same durable idempotency key
            await records.change(
                item,
                state,
                next_poll=0,
                error='服务重启时提交结果不明，请到 HeyGen 核对任务' if state == 'submission_unknown' else None,
            )
        for item in await records.listing(kind='delivery', statuses=['sending'], limit=10000):
            await records.change(item, 'unknown', error='服务重启，请到 Telegram 核对收件结果')
        next_cleanup = 0
        while True:
            try:
                if time.time() >= next_cleanup:
                    try:
                        await cleanup_deleted()
                    except OSError:
                        log.warning('Video file cleanup failed; retrying later')
                    next_cleanup = time.time() + 60
                jobs = await records.listing(statuses=['queued', 'processing', 'cancelling'], limit=10000, oldest=True)
                for job in jobs:
                    if job.get('next_poll', 0) <= time.time():
                        await execute(job)
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('Video worker unavailable (%s)', type(exc).__name__)
                await asyncio.sleep(5)
