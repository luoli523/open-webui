"""Explicit video delivery using the audio studio's admin-managed destination."""

import asyncio
import hashlib

import aiohttp
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from open_webui.models import video_studio as records
from open_webui.services.audio_studio import telegram_config
from open_webui.services.video_media import path


async def send(job, user):
    config = await telegram_config()
    if not config.get('token') or not config.get('chat_id'):
        raise HTTPException(400, '请先在生成播报页配置 Telegram')
    source = path(job['id'] + '.mp4')
    if not source.is_file():
        raise HTTPException(404, '视频文件不存在')
    if source.stat().st_size > 49 * 1024 * 1024:
        raise HTTPException(413, '视频超过工作台 Telegram 49 MB 发送限制，请下载后手动发送')
    id = hashlib.sha256(f'{user.id}:{config["chat_id"]}:{job["video_hash"]}'.encode()).hexdigest()
    receipt = await records.get(id, user.id)
    if receipt:
        if receipt['status'] == 'sent':
            return receipt
        if receipt['status'] != 'failed':
            raise HTTPException(409, '发送中或结果待核实，请先到 Telegram 核对')
        receipt = await records.change(receipt, 'sending', error=None)
        if not receipt:
            raise HTTPException(409, '发送状态已变化，请刷新')
    else:
        try:
            receipt = await records.create(
                user.id, 'delivery', dict(job_id=job['id'], chat_id=config['chat_id']), 'sending', id
            )
        except IntegrityError:
            raise HTTPException(409, '该视频已在发送，请刷新') from None
    try:
        with source.open('rb') as video:
            form = aiohttp.FormData()
            form.add_field('chat_id', config['chat_id'])
            form.add_field('caption', job['title'][:200])
            form.add_field('supports_streaming', 'true')
            form.add_field('video', video, filename='broadcast.mp4', content_type='video/mp4')
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
                async with session.post(
                    f'https://api.telegram.org/bot{config["token"]}/sendVideo', data=form
                ) as response:
                    result = await response.json()
                    if result.get('ok'):
                        receipt = await records.change(receipt, 'sent', message_id=result['result']['message_id'])
                    elif response.status < 500:
                        receipt = await records.change(
                            receipt, 'failed', error='Telegram 拒绝发送，请检查 Bot、目标和文件'
                        )
                    else:
                        receipt = await records.change(receipt, 'unknown', error='Telegram 返回异常，请先核对收件情况')
    except asyncio.CancelledError:
        await records.change(receipt, 'unknown', error='发送中断，请到 Telegram 核对')
        raise
    except Exception:
        receipt = await records.change(receipt, 'unknown', error='发送结果待核实，请先到 Telegram 核对')
    return receipt or await records.get(id, user.id)
