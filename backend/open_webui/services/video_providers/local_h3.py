"""Local asynchronous H3 service adapter. No model code belongs in WebUI."""
import re
from urllib.parse import urlsplit
import aiohttp
from .base import ProviderError, SubmissionUnknown, VideoProvider


def base_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1')
        or parsed.username or parsed.password or parsed.path not in ('', '/')
        or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError('H3 地址须为带端口的本机 HTTP 地址，例如 http://127.0.0.1:8092')
    return value.rstrip('/')


class LocalH3(VideoProvider):
    capabilities = dict(id='local_h3', name='本地 H3', cloud=False, paid=False,
        input_types=['image'], aspect_ratios=['1:1'], resolutions=['512x512'],
        preview_resolution='512x512', final_resolution='512x512',
        max_asset_bytes=32*1024*1024, max_duration_seconds=300, supports_cancel=True,
        supported_steps=[8,12,20], default_steps=12, long_video_enabled=False,
        duration_note='默认 12 步；步数越高耗时越长。先生成短片预览。')

    async def request(self, method, path, submission=False, **kwargs):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120, connect=5), trust_env=False) as session:
                async with session.request(method, base_url(self.config['base_url'])+path,
                                           allow_redirects=False, **kwargs) as response:
                    if submission and (response.status >= 500 or 300 <= response.status < 400):
                        raise SubmissionUnknown('本地提交结果待恢复，将使用相同幂等键查询')
                    data = await response.json()
                    if response.status >= 300:
                        detail = data.get('detail') if isinstance(data, dict) else None
                        raise ProviderError(detail if isinstance(detail, str) else '本地 H3 拒绝请求')
                    if not isinstance(data, dict):
                        raise (SubmissionUnknown if submission else ProviderError)('本地 H3 返回无效响应')
                    return data
        except ProviderError:
            raise
        except Exception:
            if submission:
                raise SubmissionUnknown('本地提交连接中断，将使用相同幂等键恢复任务') from None
            raise ProviderError('无法连接本地 H3，请检查视频服务；重试不会重复创建同一任务') from None

    async def prepare_asset(self, path, media_type):
        with path.open('rb') as source:
            form = aiohttp.FormData()
            form.add_field('kind', 'image' if media_type.startswith('image/') else 'audio')
            form.add_field('file', source, filename=path.name, content_type=media_type)
            data = await self.request('POST', '/v1/video/assets', data=form)
        return self.identifier(data.get('id'))

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
            raise ProviderError('本地 H3 返回无效任务或素材 ID')
        return value

    async def submit(self, request, assets):
        data = await self.request('POST', '/v1/video/jobs', submission=True, json=dict(
            image_id=assets['portrait'], audio_id=assets['audio'], steps=request.get('steps', 12),
            seed=request.get('seed', 42), idempotency_key='owui:'+request['id']+':'+str(request['attempt'])))
        try:
            return self.identifier(data.get('id'))
        except ProviderError:
            raise SubmissionUnknown('本地任务 ID 尚未恢复，将以相同幂等键重试') from None

    async def poll(self, external_id):
        identifier = self.identifier(external_id)
        data = await self.request('GET', '/v1/video/jobs/'+identifier)
        state = data.get('state')
        mapping = {'queued':'pending', 'running':'processing', 'cancelling':'processing',
                   'completed':'completed', 'failed':'failed', 'interrupted':'failed', 'cancelled':'cancelled'}
        if state not in mapping:
            raise ProviderError('本地 H3 返回未知任务状态')
        return dict(state=mapping[state], result_url=identifier,
                    progress={key:data.get(key) for key in ('stage','step','total','segment','segments','completed_segments')},
                    duration=data.get('output_duration'), error=data.get('error'),
                    interrupted=state=='interrupted')

    async def cancel(self, external_id):
        return await self.request('POST', '/v1/video/jobs/'+self.identifier(external_id)+'/cancel')

    async def retry(self, external_id):
        return await self.request('POST', '/v1/video/jobs/'+self.identifier(external_id)+'/retry')

    async def fetch_result(self, result, destination):
        identifier = self.identifier(result.get('result_url'))
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600), trust_env=False) as session:
                async with session.get(base_url(self.config['base_url'])+'/v1/video/jobs/'+identifier+'/result', allow_redirects=False) as response:
                    if response.status != 200:
                        raise ProviderError('本地视频尚未准备好')
                    size = 0
                    with destination.open('wb') as target:
                        async for chunk in response.content.iter_chunked(256*1024):
                            size += len(chunk)
                            if size > 512*1024*1024:
                                raise ProviderError('视频超过 512 MB 限制')
                            target.write(chunk)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('本地视频读取失败，可重试下载') from None


class MacH3(LocalH3):
    capabilities = dict(LocalH3.capabilities, id='h3_mac', name='本机 H3（Mac）')


class CudaH3(LocalH3):
    capabilities = dict(LocalH3.capabilities, id='h3_4090', name='4090 H3')
