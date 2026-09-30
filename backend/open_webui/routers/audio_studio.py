"""Authenticated audio workspace. Local TTS remains a private loopback service."""

import asyncio
import re

import aiohttp
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from open_webui.models import audio_studio as records
from open_webui.models.config import Config
from open_webui.services import audio_studio as service
from open_webui.utils.auth import get_admin_user, get_verified_user
from pydantic import BaseModel, Field

router = APIRouter()
send_tasks = set()


@router.get('/voices')
async def voices(user=Depends(get_verified_user)):
    return await service.voices(user)


async def form_data(file, name=None, ref_text='', owner_id=None):
    form = aiohttp.FormData()
    if name is not None:
        form.add_field('name', name)
        form.add_field('ref_text', ref_text)
    if owner_id:
        form.add_field('owner_id', owner_id)
    if file:
        data = await file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, '录音不能超过 20 MB')
        form.add_field('file', data, filename='recording', content_type='application/octet-stream')
    return form


@router.post('/voices')
async def create_voice(
    name: str = Form(...), ref_text: str = Form(''), file: UploadFile = File(...), user=Depends(get_verified_user)
):
    return await service.local('POST', '/v1/audio/voices', data=await form_data(file, name, ref_text, user.id))


@router.put('/voices/{id}')
async def update_voice(
    id: str,
    name: str = Form(...),
    ref_text: str = Form(''),
    file: UploadFile | None = File(None),
    user=Depends(get_verified_user),
):
    await service.voice_for(user, id, edit=True)
    return await service.local('PUT', f'/v1/audio/voices/{id}', data=await form_data(file, name, ref_text))


@router.delete('/voices/{id}')
async def delete_voice(id: str, user=Depends(get_verified_user)):
    await service.voice_for(user, id, edit=True)
    return await service.local('DELETE', f'/v1/audio/voices/{id}')


@router.get('/voices/{id}/reference')
async def reference(id: str, user=Depends(get_verified_user)):
    await service.voice_for(user, id)
    return Response(await service.local('GET', f'/v1/audio/voices/{id}/reference', binary=True), media_type='audio/wav')


@router.post('/transcriptions')
async def transcribe(file: UploadFile = File(...), user=Depends(get_verified_user)):
    return await service.local('POST', '/v1/audio/transcriptions', data=await form_data(file))


class Generate(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    voice_id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    speed: float = Field(default=1, ge=0.25, le=4)
    title: str = Field(default='', max_length=100)


@router.post('/jobs')
async def generate(form: Generate, user=Depends(get_verified_user)):
    if not form.text.strip():
        raise HTTPException(400, '请输入播报文案')
    waiting = await records.listing(user.id, status='queued', limit=8)
    if len(waiting) >= 8:
        raise HTTPException(429, '待生成任务过多，请稍后再试')
    voice = await service.voice_for(user, form.voice_id)
    return await records.create(
        user.id,
        'job',
        dict(
            text=form.text.strip(),
            voice_id=voice['id'],
            voice_name=voice['name'],
            voice_version=voice.get('version') if voice['kind'] == 'clone' else None,
            speed=form.speed,
            title=form.title.strip() or form.text.strip()[:30],
        ),
    )


@router.get('/jobs')
async def jobs(user=Depends(get_verified_user)):
    return await records.listing(user.id)


async def owned_job(id, user):
    job = await records.get(id, user.id)
    if not job or job['kind'] != 'job':
        raise HTTPException(404, '任务不存在')
    return job


@router.get('/jobs/{id}/audio')
async def audio(id: str, format: str = 'mp3', user=Depends(get_verified_user)):
    job = await owned_job(id, user)
    if format not in ('mp3', 'wav'):
        raise HTTPException(400, '不支持的格式')
    if job['status'] != 'completed':
        raise HTTPException(409, '音频尚未生成完成')
    path = service.audio_path(job['id'], format)
    if not path.is_file():
        raise HTTPException(404, '音频文件不存在')
    return FileResponse(
        path, media_type='audio/mpeg' if format == 'mp3' else 'audio/wav', filename=f'{job["title"][:50]}.{format}'
    )


class TelegramConfig(BaseModel):
    token: str | None = Field(default=None, max_length=200)
    chat_id: str = Field(max_length=100)


@router.get('/telegram/config')
async def config(user=Depends(get_admin_user)):
    value = await service.telegram_config()
    return {'configured': bool(value.get('token') and value.get('chat_id')), 'chat_id': value.get('chat_id', '')}


@router.put('/telegram/config')
async def save_config(form: TelegramConfig, user=Depends(get_admin_user)):
    old = await service.telegram_config()
    token = form.token.strip() if form.token is not None else old.get('token', '')
    chat = form.chat_id.strip()
    if token and not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise HTTPException(400, 'Bot Token 格式不正确')
    if chat and not re.fullmatch(r'-?[0-9]+|@[A-Za-z0-9_]+', chat):
        raise HTTPException(400, '目标 chat_id 格式不正确')
    await Config.upsert({'audio.studio.telegram': {'token': token, 'chat_id': chat}})
    return {'configured': bool(token and chat), 'chat_id': chat}


@router.get('/deliveries')
async def deliveries(user=Depends(get_admin_user)):
    return await records.listing(user.id, kind='delivery', limit=100)


@router.post('/jobs/{id}/telegram')
async def send(id: str, user=Depends(get_admin_user)):
    job = await owned_job(id, user)
    if job['status'] != 'completed':
        raise HTTPException(409, '音频尚未生成完成')
    task = asyncio.create_task(service.send_telegram(job, user))
    send_tasks.add(task)

    def done(t):
        send_tasks.discard(t)
        if not t.cancelled():
            t.exception()

    task.add_done_callback(done)
    return await asyncio.shield(task)


class Resolve(BaseModel):
    received: bool


@router.post('/deliveries/{id}/resolve')
async def resolve(id: str, form: Resolve, user=Depends(get_admin_user)):
    receipt = await records.get(id, user.id)
    if not receipt or receipt['kind'] != 'delivery':
        raise HTTPException(404, '回执不存在')
    if not await records.transition(id, ['unknown'], 'sent' if form.received else 'failed', manually_confirmed=True):
        raise HTTPException(409, '当前发送状态无需确认')
    return await records.get(id, user.id)
