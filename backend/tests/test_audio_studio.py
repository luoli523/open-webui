"""Run against an isolated database: python -m unittest discover -s backend/tests -p test_audio_studio.py."""

import os
import secrets
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sandbox = tempfile.TemporaryDirectory()
os.environ.update(
    DATA_DIR=sandbox.name,
    STATIC_DIR=sandbox.name + '/static',
    WEBUI_SECRET_KEY=secrets.token_hex(32),
    OFFLINE_MODE='true',
)
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from open_webui.models import audio_studio as records  # noqa: E402
from open_webui.routers import audio_studio as api  # noqa: E402
from open_webui.services import audio_studio as service  # noqa: E402
from open_webui.utils.auth import get_admin_user, get_verified_user  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402


class StudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = SimpleNamespace(id=secrets.token_hex(8), role='admin')
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_verified_user] = lambda: self.user
        app.dependency_overrides[get_admin_user] = lambda: self.user
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_owned_jobs_and_atomic_state(self):
        job = await records.create(self.user.id, 'job', {'title': 'sample'})
        self.assertIsNone(await records.get(job['id'], 'someone_else'))
        self.assertTrue(await records.transition(job['id'], ['queued'], 'running'))
        self.assertFalse(await records.transition(job['id'], ['queued'], 'running'))
        await records.recover()
        self.assertEqual((await records.get(job['id']))['status'], 'interrupted')

    async def test_voice_access_control(self):
        catalog = {
            'voices': [
                {'id': 'preset', 'kind': 'preset', 'owner_id': None},
                {'id': 'mine', 'kind': 'clone', 'owner_id': self.user.id},
                {'id': 'other', 'kind': 'clone', 'owner_id': 'other'},
            ]
        }
        with patch.object(service, 'local', AsyncMock(return_value=catalog)):
            ids = [v['id'] for v in await service.voices(self.user)]
            self.assertEqual(ids, ['preset', 'mine'])
            r = await self.client.delete('/voices/other')
            self.assertEqual(r.status_code, 404)
            r = await self.client.delete('/voices/preset')
            self.assertEqual(r.status_code, 403)

    async def test_generate_validation_and_version_snapshot(self):
        voice = {'id': 'luwei', 'name': 'luwei', 'kind': 'clone', 'version': 'abc123'}
        with patch.object(service, 'voice_for', AsyncMock(return_value=voice)):
            r = await self.client.post('/jobs', json={'text': ' ', 'voice_id': 'luwei'})
            self.assertEqual(r.status_code, 400)
            r = await self.client.post('/jobs', json={'text': '你好', 'voice_id': 'luwei', 'speed': 1})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['voice_version'], 'abc123')
            r = await self.client.get('/jobs/' + r.json()['id'] + '/audio')
            self.assertEqual(r.status_code, 409)

    async def test_delivery_dedup_and_unknown_resolution(self):
        id = secrets.token_hex(16)
        await records.create(self.user.id, 'delivery', {'job_id': 'job'}, 'sending', id)
        with self.assertRaises(IntegrityError):
            await records.create(self.user.id, 'delivery', {}, 'sending', id)
        await records.recover()
        self.assertEqual((await records.get(id))['status'], 'unknown')
        r = await self.client.post('/deliveries/' + id + '/resolve', json={'received': True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'sent')
        r = await self.client.post('/deliveries/' + id + '/resolve', json={'received': False})
        self.assertEqual(r.status_code, 409)

    async def test_telegram_success_rejection_and_ambiguous_result(self):  # noqa: C901
        from pathlib import Path

        from fastapi import HTTPException

        for scenario in ('success', 'reject', 'timeout'):
            id = secrets.token_hex(16)
            job = {'id': id, 'title': '验收', 'audio_hash': id}
            audio = Path(sandbox.name) / (id + '.mp3')
            audio.write_bytes(b'audio')

            class Response:
                status = 400 if scenario == 'reject' else 200

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def json(self):
                    if scenario == 'timeout':
                        raise TimeoutError()
                    return {'ok': scenario == 'success', 'error_code': 400, 'result': {'message_id': 123}}

            class Session:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                def post(self, *args, **kwargs):
                    return Response()

            with (
                patch.object(
                    service, 'telegram_config', AsyncMock(return_value={'token': '123:mock', 'chat_id': '123'})
                ),
                patch.object(service, 'audio_path', return_value=audio),
                patch.object(service.aiohttp, 'ClientSession', return_value=Session()) as factory,
            ):
                if scenario == 'timeout':
                    with self.assertRaises(HTTPException):
                        await service.send_telegram(job, self.user)
                    entries = await records.listing(self.user.id, kind='delivery')
                    self.assertEqual(next(r for r in entries if r['job_id'] == id)['status'], 'unknown')
                else:
                    receipt = await service.send_telegram(job, self.user)
                    self.assertEqual(receipt['status'], 'sent' if scenario == 'success' else 'failed')
                    if scenario == 'success':
                        await service.send_telegram(job, self.user)
                        self.assertEqual(factory.call_count, 1)

    async def test_config_redacts_token(self):
        r = await self.client.put('/telegram/config', json={'token': '123:abc_DEF', 'chat_id': '1234'})
        self.assertEqual(r.status_code, 200)
        r = await self.client.get('/telegram/config')
        self.assertTrue(r.json()['configured'])
        self.assertNotIn('token', r.json())
        await self.client.put('/telegram/config', json={'token': None, 'chat_id': '5678'})
        self.assertEqual((await service.telegram_config())['token'], '123:abc_DEF')


if __name__ == '__main__':
    unittest.main()
