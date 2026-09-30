"""Authenticated portrait library and explicit, paid video workflow actions."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from open_webui.models import video_studio as records
from open_webui.services import audio_studio, video_studio as service, video_media as media, video_delivery
from open_webui.services.video_providers import PROVIDERS, provider_for
from open_webui.services.video_providers.base import ProviderError
from open_webui.utils.auth import get_admin_user, get_verified_user

router = APIRouter()
send_tasks = set()


@router.get('/providers')
async def providers(user=Depends(get_verified_user)):
    config = await service.settings()
    return [
        dict(**p.capabilities, configured=bool(config.get('config_version')), enabled=bool(config.get('enabled')))
        for p in PROVIDERS.values()
    ]


@router.get('/config')
async def config(user=Depends(get_admin_user)):
    data = await service.settings()
    return dict(configured=bool(data.get('config_version')), enabled=bool(data.get('enabled')))


class Settings(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool


@router.put('/config')
async def save_config(form: Settings, user=Depends(get_admin_user)):
    await service.save_settings(form.api_key, form.enabled)
    return await config(user)


@router.get('/portraits')
async def portraits(user=Depends(get_verified_user)):
    return [service.public(p) for p in await records.listing(user.id, kind='portrait', statuses=['active'])]


async def portrait_data(file, name, voice, user):
    if not name.strip() or len(name) > 80:
        raise HTTPException(400, '人物名称需为 1–80 个字符')
    if voice:
        await audio_studio.voice_for(user, voice)
    data = dict(name=name.strip(), default_voice_id=voice)
    if file:
        raw = await file.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(413, '照片不能超过 20 MB')
        data.update(await asyncio.to_thread(media.save_portrait, raw))
    return data


@router.post('/portraits')
async def create_portrait(
    name: str = Form(...),
    default_voice_id: str = Form(''),
    file: UploadFile = File(...),
    user=Depends(get_verified_user),
):
    data = await portrait_data(file, name, default_voice_id, user)
    return service.public(await records.create(user.id, 'portrait', data, 'active'))


@router.put('/portraits/{id}')
async def update_portrait(
    id: str,
    revision: int = Form(...),
    name: str = Form(...),
    default_voice_id: str = Form(''),
    file: UploadFile | None = File(None),
    user=Depends(get_verified_user),
):
    item = await service.owned(id, user, 'portrait')
    if item['status'] != 'active' or revision != item['revision']:
        raise HTTPException(409, '人物已变化，请刷新后重试')
    data = await portrait_data(file, name, default_voice_id, user)
    result = await records.change(item, **data)
    if not result:
        raise HTTPException(409, '人物已变化，请刷新后重试')
    return service.public(result)


@router.delete('/portraits/{id}')
async def delete_portrait(id: str, user=Depends(get_verified_user)):
    item = await service.owned(id, user, 'portrait')
    if not await records.change(item, 'deleted'):
        raise HTTPException(409, '人物已变化，请刷新')
    return {'ok': True}


@router.get('/portraits/{id}/image')
async def portrait_image(id: str, user=Depends(get_verified_user)):
    item = await service.owned(id, user, 'portrait')
    source = media.path(item['asset'])
    if not source.is_file():
        raise HTTPException(404, '照片不存在')
    return FileResponse(source, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})


class Preview(BaseModel):
    portrait_id: str = Field(max_length=100)
    audio_job_id: str = Field(max_length=100)
    provider_id: str = Field(default='heygen', max_length=60)
    aspect_ratio: str = Field(default='16:9', max_length=10)
    consent: Literal[True]


@router.post('/jobs')
async def preview(form: Preview, user=Depends(get_verified_user)):
    return service.public(await service.create_preview(user, form))


@router.get('/jobs')
async def jobs(user=Depends(get_verified_user)):
    return [service.public(item) for item in await records.listing(user.id)]


class Approval(BaseModel):
    fingerprint: str = Field(max_length=64)
    consent: Literal[True]


@router.post('/jobs/{id}/final')
async def final(id: str, form: Approval, user=Depends(get_verified_user)):
    item = await service.owned(id, user)
    return service.public(await service.create_final(user, item, form.fingerprint))


class Retry(BaseModel):
    consent: bool = False


@router.post('/jobs/{id}/retry')
async def retry(id: str, form: Retry, user=Depends(get_verified_user)):
    return service.public(await service.retry(await service.owned(id, user), form.consent))


class ResolveSubmission(BaseModel):
    external_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,200}$')
    confirmed_not_created: bool = False


@router.post('/jobs/{id}/resolve')
async def resolve_submission(id: str, form: ResolveSubmission, user=Depends(get_admin_user)):
    item = await service.owned(id, user)
    if item['status'] != 'submission_unknown':
        raise HTTPException(409, '任务当前无需核实')
    if form.external_id:
        try:
            provider = provider_for(item['provider_id'], await service.configuration(item['config_version']))
            result = await provider.poll(form.external_id)
        except ProviderError as exc:
            raise HTTPException(400, str(exc)) from None
        if result.get('title') != 'OWUI-' + id and result.get('callback_id') != id:
            raise HTTPException(400, '此视频的标题或 callback_id 与当前任务不匹配')
        updated = await records.change(item, 'processing', external_id=form.external_id, error=None, next_poll=0)
    elif form.confirmed_not_created:
        updated = await records.change(item, 'failed', error='已人工确认未创建任务，可明确确认后重新生成')
    else:
        raise HTTPException(400, '请填写外部任务 ID，或确认引擎后台没有创建此任务')
    if not updated:
        raise HTTPException(409, '任务状态已变化，请刷新')
    return service.public(updated)


@router.get('/jobs/{id}/video')
async def video(id: str, user=Depends(get_verified_user)):
    item = await service.owned(id, user)
    source = media.path(item['id'] + '.mp4')
    if item['status'] != 'completed' or not source.is_file():
        raise HTTPException(409, '视频尚未准备好')
    return FileResponse(
        source,
        media_type='video/mp4',
        filename=f'{item["title"][:50]}-{item["stage"]}.mp4',
        headers={'Cache-Control': 'private, no-store'},
    )


@router.get('/deliveries')
async def deliveries(user=Depends(get_admin_user)):
    return [service.public(item) for item in await records.listing(user.id, kind='delivery')]


@router.post('/jobs/{id}/telegram')
async def telegram(id: str, user=Depends(get_admin_user)):
    item = await service.owned(id, user)
    if item['status'] != 'completed':
        raise HTTPException(409, '视频尚未生成完成')
    task = asyncio.create_task(video_delivery.send(item, user))
    send_tasks.add(task)

    def done(result):
        send_tasks.discard(result)
        if not result.cancelled():
            result.exception()

    task.add_done_callback(done)
    return service.public(await asyncio.shield(task))


class ResolveDelivery(BaseModel):
    received: bool


@router.post('/deliveries/{id}/resolve')
async def resolve_delivery(id: str, form: ResolveDelivery, user=Depends(get_admin_user)):
    item = await service.owned(id, user, 'delivery')
    if item['status'] != 'unknown':
        raise HTTPException(409, '发送结果无需核实')
    result = await records.change(item, 'sent' if form.received else 'failed', error=None)
    if not result:
        raise HTTPException(409, '发送状态已变化，请刷新')
    return service.public(result)
