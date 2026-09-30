"""Loopback speech adapter, durable worker, audio conversion and delivery."""

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import time
import shutil
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from fastapi import HTTPException
from open_webui.env import DATA_DIR
from open_webui.models import audio_studio as records
from open_webui.models.config import Config

log = logging.getLogger(__name__)
DIRECTORY = Path(DATA_DIR) / 'audio-studio'
BASE = os.environ.get('LOCAL_TTS_BASE_URL', 'http://127.0.0.1:8091').rstrip('/')
# This service is trusted and carries uncredentialed voice management APIs.
if urlparse(BASE).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise RuntimeError('LOCAL_TTS_BASE_URL must use a trusted loopback address')
TIMEOUT = aiohttp.ClientTimeout(total=1800, connect=10)


async def local(method, path, *, json=None, data=None, binary=False):
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(method, BASE + path, json=json, data=data) as response:
                if response.status >= 400:
                    try:
                        detail = (await response.json()).get('detail', '语音服务请求失败')
                    except Exception:
                        detail = '语音服务请求失败'
                    raise HTTPException(response.status, str(detail))
                return await response.read() if binary else await response.json()
    except (TimeoutError, aiohttp.ClientError):
        raise HTTPException(503, '本地语音服务未连接或请求超时，请检查 local-tts') from None


PRESET_LANGUAGES = {
    'Serena': 'zh',
    'Vivian': 'zh',
    'Uncle_Fu': 'zh',
    'Dylan': 'zh',
    'Eric': 'zh',
    'Ryan': 'en',
    'Aiden': 'en',
    'Ono_Anna': 'ja',
    'Sohee': 'ko',
}


def language_for(text):
    # The studio targets Chinese/English; mixed Chinese text keeps Chinese pronunciation.
    return 'chinese' if re.search(r'[\u3400-\u9fff]', text) else 'english'


async def voices(user):
    result = await local('GET', '/v1/audio/voices')
    return [
        dict(v, language=PRESET_LANGUAGES.get(v['id'], 'auto'))
        for v in result['voices']
        if not v.get('owner_id') or v['owner_id'] == user.id
    ]


async def voice_for(user, id, edit=False):
    item = next((v for v in await voices(user) if v['id'] == id), None)
    if not item:
        raise HTTPException(404, '音色不存在')
    if edit and (item['kind'] != 'clone' or (item.get('owner_id') != user.id and user.role != 'admin')):
        raise HTTPException(403, '无权修改此音色')
    return item


def audio_path(id, format='mp3'):
    # IDs only come from owned database records.
    return DIRECTORY / f'{id}.{format}'


async def convert(source, target):
    process = await asyncio.create_subprocess_exec(
        shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg',
        '-nostdin',
        '-v',
        'error',
        '-y',
        '-i',
        str(source),
        '-c:a',
        'libmp3lame' if target.suffix == '.mp3' else 'pcm_s16le',
        '-f',
        'mp3' if target.suffix == '.mp3' else 'wav',
        str(target) + '.tmp',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(process.communicate(), 120)
        if process.returncode:
            raise RuntimeError('音频格式转换失败')
        os.replace(str(target) + '.tmp', target)
        os.chmod(target, 0o600)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        Path(str(target) + '.tmp').unlink(missing_ok=True)
        raise


async def execute(job):
    if not await records.transition(job['id'], ['queued'], 'running'):
        return
    try:
        if job.get('voice_id', '').startswith('voicevox_'):
            raise HTTPException(410, 'VOICEVOX 日语音色已卸载，请选择中文或英文音色')
        payload = dict(
            input=job['text'],
            speed=job['speed'],
            response_format='wav',
            lang_code=job.get('language') or language_for(job['text']),
        )
        if job['kind'] == 'design':
            payload.update(model='qwen3-tts-voice-design', instructions=job['instructions'])
        else:
            payload.update(model='qwen3-tts', voice=job['voice_id'], voice_version=job['voice_version'])
        data = await local('POST', '/v1/audio/speech', json=payload, binary=True)
        path = audio_path(job['id'], 'wav')
        await asyncio.to_thread(path.write_bytes, data)
        os.chmod(path, 0o600)
        await convert(path, audio_path(job['id']))
        digest = hashlib.sha256(await asyncio.to_thread(audio_path(job['id']).read_bytes)).hexdigest()
        await records.transition(job['id'], ['running'], 'completed', audio_hash=digest)
    except asyncio.CancelledError:
        await records.transition(job['id'], ['running'], 'interrupted', error='服务重启，生成已中断')
        raise
    except Exception as exc:
        error = exc.detail if isinstance(exc, HTTPException) else '生成或音频转换失败，请重试'
        log.warning('Audio studio job failed: %s', type(exc).__name__)
        await records.transition(job['id'], ['running'], 'failed', error=error)


async def cleanup_deleted():
    # Video creation and Telegram delivery hold this same cross-process lock.
    from open_webui.services import video_studio

    async with video_studio.asset_lock():
        freed = 0
        for job in await records.listing(status='deleted', limit=None):
            for suffix in ('wav', 'mp3', 'wav.tmp', 'mp3.tmp'):
                target = audio_path(job['id'], suffix)
                try:
                    size = target.stat().st_size
                    target.unlink()
                    freed += size
                except FileNotFoundError:
                    pass
        return freed


async def delete_job(id, user):
    from open_webui.services import video_studio

    async with video_studio.asset_lock():
        job = await records.get(id, user.id)
        if not job or job['kind'] != 'job' or job['status'] == 'deleted':
            raise HTTPException(404, '播报不存在')
        if job['status'] not in ('completed', 'failed', 'interrupted'):
            raise HTTPException(409, '请等待播报生成结束后再删除')
        for status in ('sending', 'unknown'):
            receipts = await records.listing(user.id, kind='delivery', status=status, limit=None)
            if any(r.get('job_id') == id for r in receipts):
                raise HTTPException(409, '请等待 TG 发送结束或核实发送结果后再删除')
        if not await records.transition(id, [job['status']], 'deleted'):
            raise HTTPException(409, '播报状态已变化，请刷新')
    try:
        return {'ok': True, 'freed_bytes': await cleanup_deleted(), 'cleanup_pending': False}
    except OSError:
        log.warning('Audio cleanup deferred; worker will retry')
        return {'ok': True, 'freed_bytes': 0, 'cleanup_pending': True}


async def worker():
    # One worker across local uvicorn processes; held until shutdown.
    import fcntl

    DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(DIRECTORY, 0o700)
    with (DIRECTORY / 'worker.lock').open('a') as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        await records.recover()
        next_cleanup = 0
        while True:
            try:
                if time.time() >= next_cleanup:
                    try:
                        await cleanup_deleted()
                    except OSError:
                        log.warning('Audio file cleanup failed; retrying later')
                    next_cleanup = time.time() + 60
                jobs = await records.listing(status='queued', limit=10000)
                samples = await records.listing(kind='sample', status='queued', limit=10000)
                designs = await records.listing(kind='design', status='queued', limit=10000)
                jobs = sorted(jobs + samples + designs, key=lambda job: job['created_at'], reverse=True)
                if jobs:
                    await execute(jobs[-1])
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('Audio studio worker error')
                await asyncio.sleep(3)


async def shutdown(task):
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def telegram_config():
    return await Config.get('audio.studio.telegram', {}) or {}


async def send_telegram(job, user):
    config = await telegram_config()
    if not config.get('token') or not config.get('chat_id'):
        raise HTTPException(400, '请先配置 Telegram Bot 和目标聊天')
    key = hashlib.sha256(f'{user.id}:{config["chat_id"]}:{job["audio_hash"]}'.encode()).hexdigest()
    receipt = await records.get(key, user.id)
    if receipt:
        if receipt['status'] == 'sent':
            return receipt
        if receipt['status'] in ('sending', 'unknown'):
            raise HTTPException(409, '发送中或上次结果待确认，请先到 Telegram 核对')
        if not await records.transition(key, ['failed'], 'sending'):
            raise HTTPException(409, '发送状态已变化，请刷新')
    else:
        from sqlalchemy.exc import IntegrityError

        try:
            await records.create(
                user.id, 'delivery', {'job_id': job['id'], 'chat_id': config['chat_id']}, 'sending', key
            )
        except IntegrityError:
            raise HTTPException(409, '该音频已在发送，请刷新') from None
    try:
        with audio_path(job['id']).open('rb') as audio:
            form = aiohttp.FormData()
            form.add_field('chat_id', config['chat_id'])
            form.add_field('title', job['title'])
            if job.get('credit'):
                form.add_field('caption', job['credit'])
            form.add_field('audio', audio, filename=f'{job["id"]}.mp3', content_type='audio/mpeg')
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.post(
                    f'https://api.telegram.org/bot{config["token"]}/sendAudio', data=form
                ) as response:
                    result = await response.json()
                    if not result.get('ok'):
                        await records.transition(
                            key,
                            ['sending'],
                            'failed',
                            error=f'Telegram 拒绝请求（{result.get("error_code", response.status)}）',
                        )
                    else:
                        await records.transition(key, ['sending'], 'sent', message_id=result['result']['message_id'])
    except BaseException:
        await records.transition(key, ['sending'], 'unknown', error='连接中断，发送结果待确认，请在 Telegram 核对')
        raise HTTPException(502, '发送结果待确认，请在 Telegram 核对后再操作') from None
    return await records.get(key, user.id)
