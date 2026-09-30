"""Optional loopback VOICEVOX adapter (Japanese speech)."""

import os
from urllib.parse import urlparse

import aiohttp
from fastapi import HTTPException

BASE = os.environ.get('VOICEVOX_BASE_URL', 'http://127.0.0.1:50021').rstrip('/')
if urlparse(BASE).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise RuntimeError('VOICEVOX_BASE_URL must use a loopback address')
SAMPLE_TEXT = 'こんにちは。音声スタジオへようこそ。今日も楽しい一日を過ごしましょう。'


async def request(method, path, *, params=None, json=None, binary=False, timeout=180):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout, connect=3)) as session:
            async with session.request(method, BASE + path, params=params, json=json) as response:
                if response.status >= 400:
                    raise HTTPException(502, 'VOICEVOX 生成失败，请检查日语文案和服务状态')
                return await response.read() if binary else await response.json()
    except (TimeoutError, aiohttp.ClientError):
        raise HTTPException(503, 'VOICEVOX 未连接或请求超时') from None


async def voices():
    speakers = await request('GET', '/speakers', timeout=5)
    version = await request('GET', '/version', timeout=5)
    return [
        dict(
            id=f'voicevox_{style["id"]}',
            name=f'{speaker["name"]} · {style["name"]}（日语）',
            kind='preset',
            engine='voicevox',
            language='ja',
            version=str(version),
            credit=f'VOICEVOX:{speaker["name"]}',
            license_url='https://voicevox.hiroshiba.jp/',
        )
        for speaker in speakers
        for style in speaker['styles']
        if style.get('type', 'talk') == 'talk'
    ]


async def synthesize(job):
    speaker = int(job['voice_id'].removeprefix('voicevox_'))
    query = await request('POST', '/audio_query', params={'speaker': speaker, 'text': job['text']})
    query['speedScale'] = job['speed']
    return await request('POST', '/synthesis', params={'speaker': speaker}, json=query, binary=True, timeout=1800)
