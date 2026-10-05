"""4090 image workspace; separate from the existing local/cloud image settings."""
import asyncio
import base64
import binascii
import io
import re
from typing import Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from PIL import Image

from open_webui.internal.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from open_webui.models.files import Files
from open_webui.storage.provider import Storage
from open_webui.routers.files import delete_file_by_id
from open_webui.models.config import Config
from open_webui.models import video_studio as records
from open_webui.routers.images import upload_image
from open_webui.utils.auth import get_admin_user

router = APIRouter()
CONFIG_KEY = 'image.studio.cuda'
DEFAULT_URL = 'http://127.0.0.1:28093'
MODELS = [{'id': 'qwen-image-2.1-turbo6', 'name': '4090 · Viggle Turbo · 6 步'},
          {'id': 'qwen-image-2.1-base40', 'name': '4090 · Qwen Image · 40 步'}]


def validate_url(value):
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', value) or not 1 <= int(value.rsplit(':', 1)[1]) <= 65535:
        raise HTTPException(422, '请使用本机 SSH 隧道地址，如 http://127.0.0.1:28093')
    return value


async def settings():
    return await Config.get(CONFIG_KEY, {'base_url': DEFAULT_URL, 'enabled': False, 'api_key': ''})


async def remote(config, method, path, **kwargs):
    url = validate_url(config.get('base_url', DEFAULT_URL))
    try:
        async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=290)) as session:
            async with session.request(method, url+path, headers={'Authorization': 'Bearer '+config.get('api_key', '')},
                                       allow_redirects=False, **kwargs) as response:
                chunks = []
                size = 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 24*1024*1024:
                        raise HTTPException(502, '图像服务返回内容过大')
                    chunks.append(chunk)
                import json
                payload = json.loads(b''.join(chunks))
                if response.status >= 300:
                    detail = payload.get('detail') if isinstance(payload, dict) else None
                    message = detail if isinstance(detail, str) else '4090 图像服务拒绝请求'
                    raise HTTPException(response.status if response.status in (409, 413, 422, 503, 504) else 502, message)
                if not isinstance(payload, dict):
                    raise ValueError('Invalid service response')
                return payload
    except HTTPException:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise HTTPException(503, '无法连接 4090 图像服务，请检查 SSH 隧道和远端服务') from None
    except ValueError:
        raise HTTPException(502, '4090 图像服务返回了无效结果') from None


@router.get('/config')
async def get_config(user=Depends(get_admin_user)):
    config = await settings()
    online = False
    busy = False
    if config.get('enabled'):
        try:
            state = await remote(config, 'GET', '/health', timeout=aiohttp.ClientTimeout(total=5))
            online = bool(state.get('model_ready'))
            busy = bool(state.get('busy'))
        except HTTPException:
            pass
    return {'base_url': config.get('base_url', DEFAULT_URL), 'enabled': bool(config.get('enabled')),
            'configured': bool(config.get('api_key')), 'online': online, 'busy': busy, 'models': MODELS}


class Settings(BaseModel):
    base_url: str = Field(default=DEFAULT_URL, max_length=200)
    enabled: bool
    api_key: str | None = Field(default=None, min_length=32, max_length=200)


@router.put('/config')
async def save_config(form: Settings, user=Depends(get_admin_user)):
    config = await settings()
    new = {'base_url': validate_url(form.base_url.rstrip('/')), 'enabled': form.enabled,
           'api_key': form.api_key if form.api_key is not None else config.get('api_key', '')}
    if new['enabled']:
        available = await remote(new, 'GET', '/v1/models', timeout=aiohttp.ClientTimeout(total=5))
        if not all(model['id'] in [m.get('id') for m in available.get('data', [])] for model in MODELS):
            raise HTTPException(422, '此地址没有提供 Qwen Image 的两种模式')
    await Config.upsert({CONFIG_KEY: new})
    return await get_config(user)


class Generation(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: Literal['qwen-image-2.1-turbo6', 'qwen-image-2.1-base40'] = 'qwen-image-2.1-turbo6'
    seed: int | None = Field(default=None, ge=0, le=2**32-1)


def public(row):
    return {key: row[key] for key in ('id', 'file_id', 'prompt', 'model', 'seed', 'width', 'height', 'seconds', 'created_at')}


@router.get('/images')
async def history(user=Depends(get_admin_user)):
    return [public(row) for row in await records.listing(user.id, kind='image', statuses=['completed'], limit=50)]


async def owned_image(id, user):
    row = await records.get(id, user.id)
    if not row or row['kind'] != 'image':
        raise HTTPException(404, '图片不存在')
    return row


def thumbnail_bytes(path):
    with Image.open(Storage.get_file(path)) as picture:
        picture.thumbnail((160, 160))
        output = io.BytesIO()
        picture.convert('RGB').save(output, format='WEBP', quality=80)
        return output.getvalue()


@router.get('/images/{id}/thumbnail')
async def thumbnail(id: str, user=Depends(get_admin_user)):
    row = await owned_image(id, user)
    file = await Files.get_file_by_id(row['file_id'])
    if not file or file.user_id != user.id:
        raise HTTPException(404, '图片文件不存在')
    try:
        raw = await asyncio.to_thread(thumbnail_bytes, file.path)
    except (OSError, ValueError):
        raise HTTPException(404, '无法读取图片文件') from None
    return Response(raw, media_type='image/webp', headers={'Cache-Control': 'private, no-store'})


@router.delete('/images/{id}')
async def delete_image(request: Request, id: str, user=Depends(get_admin_user),
                       db: AsyncSession = Depends(get_async_session)):
    row = await owned_image(id, user)
    file = await Files.get_file_by_id(row['file_id'], db=db)
    if file:
        if file.user_id != user.id:
            raise HTTPException(404, '图片文件不存在')
        # Remove bytes first: if storage fails, keep records so deletion can be retried.
        try:
            await asyncio.to_thread(Storage.delete_file, file.path)
        except Exception:
            raise HTTPException(500, '磁盘图片删除失败，请重试') from None
        await delete_file_by_id(request, file.id, user=user, db=db)
    await records.remove_image(id, user.id)
    return {'deleted': True}


@router.post('/images')
async def generate(request: Request, user=Depends(get_admin_user)):
    config = await settings()
    if not config.get('enabled'):
        raise HTTPException(409, '请先启用 4090 图像服务')
    async with request.form(max_files=1, max_fields=3, max_part_size=16000) as form:
        try:
            params = Generation.model_validate({k: v for k, v in form.items() if k != 'image'})
        except ValidationError:
            raise HTTPException(422, '请填写提示词，并使用有效的模型和 0–4294967295 随机种子') from None
        data = params.model_dump(exclude_none=True)
        if not params.prompt.strip():
            raise HTTPException(422, '提示词不能为空')
        if image := form.get('image'):
            if not hasattr(image, 'read'):
                raise HTTPException(422, '参考图格式错误')
            raw = await image.read(10*1024*1024+1)
            if len(raw) > 10*1024*1024:
                raise HTTPException(413, '参考图不能超过 10 MB')
            multipart = aiohttp.FormData()
            for key, value in data.items():
                multipart.add_field(key, str(value))
            multipart.add_field('image', raw, filename='reference', content_type='application/octet-stream')
            result = await remote(config, 'POST', '/v1/images/edits', data=multipart)
        else:
            result = await remote(config, 'POST', '/v1/images/generations', json=data)
    try:
        raw = base64.b64decode(result['data'][0]['b64_json'], validate=True)
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format != 'PNG' or picture.width*picture.height > 4_000_000:
                raise ValueError('Invalid image')
            picture.verify()
            width, height = picture.size
        seed = int(result['seed'])
        seconds = float(result['seconds'])
    except (KeyError, IndexError, TypeError, ValueError, OSError, binascii.Error):
        raise HTTPException(502, '4090 返回的图片或元数据无效') from None
    file, _ = await upload_image(request, raw, 'image/png', {'source': 'image-studio-4090', **data}, user)
    row = await records.create(user.id, 'image', dict(file_id=file.id, prompt=params.prompt, model=params.model,
                                                    seed=seed, width=width, height=height, seconds=seconds), 'completed')
    return public(row)
