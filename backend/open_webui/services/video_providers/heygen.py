"""HeyGen v3 image + existing audio adapter. No vendor TTS or automatic POST retry."""

import ipaddress
import re
from urllib.parse import quote, urlsplit

import aiohttp
from aiohttp.resolver import ThreadedResolver
from .base import ProviderError, SubmissionUnknown, VideoProvider


class PublicResolver(ThreadedResolver):
    async def resolve(self, host, port=0, family=0):
        entries = await super().resolve(host, port, family)
        if any(not ipaddress.ip_address(entry['host']).is_global for entry in entries):
            raise ProviderError('视频下载地址不是公共地址')
        return entries


class HeyGen(VideoProvider):
    capabilities = dict(
        id='heygen',
        name='HeyGen',
        cloud=True,
        paid=True,
        input_types=['image'],
        aspect_ratios=['16:9', '9:16', '1:1'],
        resolutions=['720p', '1080p'],
        preview_resolution='720p',
        final_resolution='1080p',
        max_asset_bytes=32 * 1024 * 1024,
        max_duration_seconds=300,
        supports_cancel=False,
        duration_note='工作台首版限制为 5 分钟，实际还受 HeyGen 账户配额限制',
    )

    async def request(self, method, path, *, json=None, data=None, submission=False):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120, connect=15)) as session:
                async with session.request(
                    method,
                    'https://api.heygen.com/v3' + path,
                    headers={'x-api-key': self.config['api_key']},
                    json=json,
                    data=data,
                    allow_redirects=False,
                ) as response:
                    if response.status >= 500 or 300 <= response.status < 400:
                        if submission:
                            raise SubmissionUnknown('提交结果待核实，请到 HeyGen 核对任务，勿重复生成')
                        raise ProviderError('HeyGen 暂时无法响应，可稍后继续查询')
                    if response.status >= 400:
                        if submission and response.status not in (400, 401, 403, 404, 413, 415, 422, 429):
                            raise SubmissionUnknown('提交结果待核实，请到 HeyGen 核对任务')
                        raise ProviderError(f'HeyGen 拒绝请求（HTTP {response.status}），请检查密钥、配额和素材')
                    result = await response.json()
                    body = result.get('data', result)
                    if not isinstance(body, dict):
                        raise ValueError('Invalid response')
                    return body
        except ProviderError:
            raise
        except Exception:
            if submission:
                raise SubmissionUnknown('提交连接中断，结果待核实，请到 HeyGen 核对任务') from None
            raise ProviderError('HeyGen 连接或响应异常，可稍后重试') from None

    async def prepare_asset(self, path, media_type):
        if path.stat().st_size > self.capabilities['max_asset_bytes']:
            raise ProviderError('上传素材超过 32 MB，请缩短播报或调整照片')
        with path.open('rb') as source:
            form = aiohttp.FormData()
            form.add_field('file', source, filename=path.name, content_type=media_type)
            data = await self.request('POST', '/assets', data=form)
        asset_id = data.get('asset_id') or data.get('id')
        if not isinstance(asset_id, str) or not asset_id:
            raise ProviderError('HeyGen 未返回素材 ID')
        return asset_id

    async def submit(self, request, assets):
        data = await self.request(
            'POST',
            '/videos',
            submission=True,
            json={
                'type': 'image',
                'image': {'type': 'asset_id', 'asset_id': assets['portrait']},
                'audio_asset_id': assets['audio'],
                'resolution': request['resolution'],
                'aspect_ratio': request['aspect_ratio'],
                'title': f'OWUI-{request["id"]}-{request["attempt"]}',
                'callback_id': f'{request["id"]}:{request["attempt"]}',
            },
        )
        value = data.get('video_id') or data.get('id')
        if not isinstance(value, str) or not value:
            raise SubmissionUnknown('未收到视频 ID，请到 HeyGen 核对任务')
        return value

    async def poll(self, external_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', external_id):
            raise ProviderError('视频 ID 格式不正确')
        data = await self.request('GET', '/videos/' + quote(external_id, safe=''))
        state = data.get('status')
        if state not in ('pending', 'processing', 'completed', 'failed'):
            raise ProviderError('HeyGen 返回未知状态，请稍后继续查询')
        return {
            'state': state,
            'result_url': data.get('video_url'),
            'title': data.get('title'),
            'callback_id': data.get('callback_id'),
        }

    async def fetch_result(self, result, destination):
        url = result.get('result_url')
        parsed = urlsplit(url or '')
        if (
            parsed.scheme != 'https'
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ProviderError('HeyGen 未返回有效的 HTTPS 视频地址')
        try:
            # aiohttp bypasses DNS resolvers for numeric IPs, so reject them explicitly.
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            pass
        else:
            raise ProviderError('视频下载地址必须使用公共域名')
        connector = aiohttp.TCPConnector(resolver=PublicResolver())
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=600)) as session:
                async with session.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        raise ProviderError('视频下载失败，请重新查询并下载已有视频')
                    size = 0
                    with destination.open('wb') as target:
                        async for chunk in response.content.iter_chunked(256 * 1024):
                            size += len(chunk)
                            if size > 512 * 1024 * 1024:
                                raise ProviderError('视频超过工作台 512 MB 下载限制')
                            target.write(chunk)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('视频下载连接异常，请重试下载已有视频') from None
