"""Authenticated portrait library and explicit, paid video workflow actions."""

import asyncio
from typing import Literal
from open_webui.services.video_providers import H3_PROVIDERS

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from open_webui.models import video_studio as records
from open_webui.services import audio_studio, video_studio as service, video_media as media, video_delivery
from open_webui.services import video_captions as captions
from open_webui.services.video_providers import PROVIDERS, provider_for
from open_webui.services.video_providers.base import ProviderError
from open_webui.utils.auth import get_admin_user, get_verified_user

router = APIRouter()
send_tasks = set()


@router.get('/providers')
async def providers(user=Depends(get_verified_user)):
    result = []
    for name, provider in PROVIDERS.items():
        if name == 'local_h3':
            continue  # Legacy jobs retain their original provider and config version.
        config = await service.settings(name)
        caps = dict(provider.capabilities)
        enabled = bool(config.get('enabled'))
        configured = bool(config.get('config_version'))
        if name in H3_PROVIDERS and configured:
            try:
                remote = await provider_for(name, await service.configuration(config['config_version'])).request('GET', '/v1/video/capabilities')
                for key in ('supported_steps','default_steps','long_video_enabled'):
                    caps[key] = remote.get(key, caps.get(key))
                enabled = enabled and bool(remote.get('ready'))
            except ProviderError:
                enabled = False
        result.append(dict(**caps, configured=configured, enabled=enabled))
    return result


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


class LocalSettings(BaseModel):
    base_url: str = Field(default='http://127.0.0.1:8092', max_length=200)
    enabled: bool


@router.get('/config/local-h3')
async def local_config(user=Depends(get_admin_user)):
    data = await service.settings('local_h3')
    return dict(base_url=data.get('base_url', 'http://127.0.0.1:8092'),
                configured=bool(data.get('config_version')), enabled=bool(data.get('enabled')))


@router.put('/config/local-h3')
async def save_local_config(form: LocalSettings, user=Depends(get_admin_user)):
    await service.save_local_settings(form.base_url, form.enabled)
    return await local_config(user)


@router.get('/config/h3/{provider_id}')
async def h3_config(provider_id: Literal['h3_mac', 'h3_4090'], user=Depends(get_admin_user)):
    data = await service.settings(provider_id)
    default = 'http://127.0.0.1:8092' if provider_id == 'h3_mac' else 'http://127.0.0.1:28092'
    return dict(base_url=data.get('base_url', default), configured=bool(data.get('config_version')),
                enabled=bool(data.get('enabled')))


@router.put('/config/h3/{provider_id}')
async def save_h3_config(provider_id: Literal['h3_mac', 'h3_4090'], form: LocalSettings,
                         user=Depends(get_admin_user)):
    await service.save_local_settings(form.base_url, form.enabled, provider_id)
    return await h3_config(provider_id, user)


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
    steps: Literal[8, 12, 20] = 12
    preview_start: float = Field(default=0, ge=0, le=298, allow_inf_nan=False)
    preview_seconds: float = Field(default=5, ge=2, le=15, allow_inf_nan=False)


@router.post('/jobs')
async def preview(form: Preview, user=Depends(get_verified_user)):
    return service.public(await service.create_preview(user, form))


@router.get('/jobs')
async def jobs(user=Depends(get_verified_user)):
    caption_items = {c['job_id']: c for c in await records.listing(user.id, kind='caption', limit=10000)}
    result = []
    for item in await records.listing(user.id, visible_only=True):
        caption = caption_items.get(item['id'])
        result.append(
            dict(
                service.public(item),
                caption_ready=captions.ready(caption),
                caption_hash=caption.get('render_hash') if caption else None,
                caption_status=caption['status'] if caption else 'queued' if item.get('auto_captions') else None,
                caption_operation=caption.get('operation') if caption else 'generate',
                caption_version=caption.get('rendered_version') if caption else None,
                caption_error=caption.get('error') if caption else None,
            )
        )
    return result


@router.delete('/jobs/{id}')
async def delete_job(id: str, user=Depends(get_verified_user)):
    return await service.delete_record(id, user)


@router.post('/jobs/{id}/cancel')
async def cancel_job(id: str, user=Depends(get_verified_user)):
    return service.public(await service.cancel_local(await service.owned(id, user)))


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)


@router.patch('/jobs/{id}')
async def rename_job(id: str, form: Rename, user=Depends(get_verified_user)):
    item = await service.owned(id, user)
    if item['status'] != 'completed':
        raise HTTPException(409, '视频生成完成后可改名')
    title = ' '.join(form.title.split())
    if not title:
        raise HTTPException(400, '请输入视频名称')
    if item['revision'] != form.revision:
        raise HTTPException(409, '记录已变化，请刷新后重新改名')
    result = await records.change(item, title=title)
    if not result:
        raise HTTPException(409, '记录已变化，请刷新后重新改名')
    return service.public(result)


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
        if (
            result.get('title') != f'OWUI-{id}-{item["attempt"]}'
            and result.get('callback_id') != f'{id}:{item["attempt"]}'
        ):
            raise HTTPException(400, '此视频的标题或 callback_id 与当前任务不匹配')
        updated = await records.change(item, 'processing', external_id=form.external_id, error=None, next_poll=0)
    elif form.confirmed_not_created:
        updated = await records.change(item, 'failed', error='已人工确认未创建任务，可明确确认后重新生成')
    else:
        raise HTTPException(400, '请填写外部任务 ID，或确认引擎后台没有创建此任务')
    if not updated:
        raise HTTPException(409, '任务状态已变化，请刷新')
    return service.public(updated)


@router.get('/jobs/{id}/thumbnail')
async def thumbnail(id: str, user=Depends(get_verified_user)):
    async with service.asset_lock():
        item = await service.owned(id, user)
        source = media.path(item['id'] + '.mp4')
        if item['status'] != 'completed' or not source.is_file():
            raise HTTPException(409, '视频尚未准备好')
        target = media.path(item['id'] + '-thumb.jpg')
        if not target.is_file() or target.stat().st_mtime_ns < source.stat().st_mtime_ns:
            try:
                await media.thumbnail(source, target)
            except (OSError, ValueError, TimeoutError):
                raise HTTPException(502, '首帧提取失败，仍可播放原视频') from None
        return FileResponse(target, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})


@router.get('/jobs/{id}/video')
async def video(id: str, variant: Literal['auto', 'original'] = 'auto', user=Depends(get_verified_user)):
    item = await service.owned(id, user)
    source = media.path(item['id'] + '.mp4')
    if item['status'] != 'completed' or not source.is_file():
        raise HTTPException(409, '视频尚未准备好')
    if variant == 'auto':
        caption = await records.get(captions.identifier(id), user.id)
        if item.get('auto_captions') or captions.ready(caption):
            source, _ = await captions.artifact(id, user, 'mp4')
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
async def telegram(id: str, variant: Literal['auto', 'original', 'captioned'] = 'auto', user=Depends(get_admin_user)):
    item = await service.owned(id, user)
    if item['status'] != 'completed':
        raise HTTPException(409, '视频尚未生成完成')

    async def deliver():
        async with service.asset_lock():
            current = await service.owned(id, user)
            caption = await records.get(captions.identifier(id), user.id)
            use_captions = variant == 'captioned' or (
                variant == 'auto' and (current.get('auto_captions') or captions.ready(caption))
            )
            if use_captions:
                source, caption = await captions.artifact(id, user, 'mp4')
                return await video_delivery.send(
                    current, user, source=source, video_hash=caption['render_hash'], variant='captioned'
                )
            return await video_delivery.send(current, user)

    task = asyncio.create_task(deliver())
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


@router.get('/jobs/{id}/captions')
async def get_captions(id: str, user=Depends(get_verified_user)):
    return await captions.get(id, user)


@router.post('/jobs/{id}/captions')
async def generate_captions(id: str, form: captions.Generate, user=Depends(get_verified_user)):
    return await captions.generate(id, user, form)


@router.put('/jobs/{id}/captions')
async def save_captions(id: str, form: captions.Edit, user=Depends(get_verified_user)):
    return await captions.save(id, user, form)


@router.post('/jobs/{id}/captions/render')
async def render_captions(id: str, form: captions.Render, user=Depends(get_verified_user)):
    return await captions.render(id, user, form)


@router.get('/jobs/{id}/captions/file')
async def caption_file(id: str, format: Literal['srt', 'vtt', 'ass', 'mp4'] = 'srt', user=Depends(get_verified_user)):
    content, item = await captions.artifact(id, user, format)
    filename = f'subtitles-v{item["version"]}.{format}'
    if format == 'mp4':
        return FileResponse(
            content, media_type='video/mp4', filename=filename, headers={'Cache-Control': 'private, no-store'}
        )
    return Response(
        content,
        media_type='text/vtt' if format == 'vtt' else 'text/plain',
        headers={'Cache-Control': 'private, no-store', 'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/jobs/{id}/captions/automatic')
async def retry_automatic_captions(id: str, user=Depends(get_verified_user)):
    job = await captions.completed_job(id, user)
    return captions.public(await captions.ensure_automatic(job, retry=True))
