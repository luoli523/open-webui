"""Local, durable captions and immutable rendered versions for studio videos."""

import asyncio
import html
import json
import logging
import math
import os
import shutil
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from open_webui.models import audio_studio as audio_records, video_studio as records
from open_webui.services import video_media as media, video_studio as studio

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
ACTIVE = ('queued', 'running')
LANGUAGES = Literal['', 'zh', 'en', 'ja', 'ko', 'de', 'fr', 'ru', 'pt', 'es', 'it']


class Cue(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=500)


class Style(BaseModel):
    size: int = Field(default=42, ge=20, le=80)
    color: str = Field(default='#FFFFFF', pattern=r'^#[0-9A-Fa-f]{6}$')
    position: Literal['bottom', 'top'] = 'bottom'
    margin: int = Field(default=48, ge=20, le=160)
    background: bool = False


class Generate(BaseModel):
    revision: int | None = Field(default=None, ge=0)
    language: LANGUAGES = ''


class Edit(BaseModel):
    revision: int = Field(ge=0)
    cues: list[Cue] = Field(min_length=1, max_length=1000)
    style: Style = Field(default_factory=Style)


class Render(BaseModel):
    revision: int = Field(ge=0)


def identifier(job_id):
    return studio.fingerprint({'caption': job_id})


def python_path():
    return os.environ.get('STUDIO_SUBTITLE_PYTHON', str(ROOT / '.venv-subtitles/bin/python'))


def ffmpeg_path():
    return os.environ.get('STUDIO_SUBTITLE_FFMPEG') or (
        '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'
        if Path('/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg').is_file()
        else shutil.which('ffmpeg') or 'ffmpeg'
    )


def public(item):
    if not item:
        return None
    return {
        k: item.get(k)
        for k in (
            'revision',
            'status',
            'operation',
            'error',
            'cues',
            'style',
            'version',
            'rendered_version',
            'mode',
            'duration',
            'language',
        )
    }


async def completed_job(id, user):
    job = await studio.owned(id, user)
    if job['status'] != 'completed' or not media.path(id + '.mp4').is_file():
        raise HTTPException(409, '请先完成视频生成')
    return job


async def get(id, user):
    job = await completed_job(id, user)
    item = await records.get(identifier(id), user.id)
    source = job.get('source_text')
    if not source:
        audio = await audio_records.get(job.get('audio_job_id'), user.id)
        source = (audio or {}).get('text', '')
    return dict(caption=public(item), source_text=source or '')


def check_edit(item, revision):
    if not item or item['revision'] != revision:
        raise HTTPException(409, '字幕版本已变化，请重新载入后编辑')
    if item['status'] in ACTIVE:
        raise HTTPException(409, '字幕正在处理，请稍后操作')


def validate_cues(cues, duration):
    result = []
    previous = 0.0
    if not cues or len(cues) > 1000:
        raise HTTPException(400, '字幕需为 1–1000 条')
    for cue in cues:
        cue = Cue.model_validate(cue).model_dump()
        cue['text'] = cue['text'].strip()
        if not cue['text'] or cue['start'] < previous or cue['end'] <= cue['start'] or cue['end'] > duration + 0.001:
            raise HTTPException(400, '字幕需按时间排序、互不重叠，结束时间不能超过视频时长')
        if any(ord(c) < 32 and c != '\n' for c in cue['text']):
            raise HTTPException(400, '字幕含无效控制字符')
        previous = cue['end']
        result.append(cue)
    return result


async def generate(id, user, form):
    if not Path(python_path()).is_file():
        raise HTTPException(503, '本地字幕环境未安装，请按字幕部署文档安装')
    async with studio.asset_lock():
        job = await completed_job(id, user)
        item = await records.get(identifier(id), user.id)
        if item and item['status'] in ACTIVE:
            return public(item)
        if item:
            check_edit(item, form.revision)
        pending = await records.listing(user.id, kind='caption', statuses=ACTIVE, limit=4)
        if len(pending) >= 4:
            raise HTTPException(429, '字幕排队任务过多，请稍后再试')
        source = job.get('source_text', '')
        if not source:
            audio = await audio_records.get(job.get('audio_job_id'), user.id)
            source = (audio or {}).get('text', '')
        data = dict(
            job_id=id,
            operation='generate',
            language=form.language,
            source_text=source,
            align=bool(source) and (job['stage'] == 'final' or job['full_duration'] <= 15),
            error=None,
        )
        if item:
            item = await records.change(item, 'queued', **data)
        else:
            item = await records.create(
                user.id,
                'caption',
                dict(**data, cues=[], style=Style().model_dump(), version=0, rendered_version=None),
                'queued',
                identifier(id),
            )
        return public(item)


async def save(id, user, form):
    async with studio.asset_lock():
        await completed_job(id, user)
        item = await records.get(identifier(id), user.id)
        check_edit(item, form.revision)
        if not item.get('duration'):
            raise HTTPException(409, '请先成功生成字幕')
        cues = validate_cues([c.model_dump() for c in form.cues], item['duration'])
        result = await records.change(
            item, 'completed', cues=cues, style=form.style.model_dump(), version=item['version'] + 1, error=None
        )
        return public(result)


async def render(id, user, form):
    async with studio.asset_lock():
        await completed_job(id, user)
        item = await records.get(identifier(id), user.id)
        if item and item['status'] in ACTIVE and item.get('operation') == 'render':
            return public(item)
        check_edit(item, form.revision)
        if not item.get('cues'):
            raise HTTPException(409, '请先生成并保存字幕')
        if item.get('rendered_version') == item['version'] and media.path(item['render_asset']).is_file():
            return public(item)
        return public(await records.change(item, 'queued', operation='render', error=None))


def timestamp(seconds, separator=','):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{ms:03}'


def ass_time(seconds):
    cs = round(seconds * 100)
    hours, cs = divmod(cs, 360000)
    minutes, cs = divmod(cs, 6000)
    seconds, cs = divmod(cs, 100)
    return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'


def export(item, format):
    cues = item['cues']
    if format in ('srt', 'vtt'):
        sep = '.' if format == 'vtt' else ','
        return (
            ('WEBVTT\n\n' if format == 'vtt' else '')
            + '\n\n'.join(
                f'{i}\n{timestamp(c["start"], sep)} --> {timestamp(c["end"], sep)}\n'
                + html.escape(c['text'], quote=False).replace('\n\n', '\n')
                for i, c in enumerate(cues, 1)
            )
            + '\n'
        )
    style = Style.model_validate(item['style'])
    color = style.color.lstrip('#')
    color = '&H00' + color[4:6] + color[2:4] + color[0:2]
    # Font size/margins are expressed against a constant 720 px canvas height.
    width = max(200, round(720 * item.get('width', 16) / item.get('height', 9)))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,PingFang SC,{style.size},{color},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,{3 if style.background else 1},2,0,{8 if style.position == 'top' else 2},24,24,{style.margin},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Neutralize ASS override and escape syntax in arbitrary user text.
    def plain(text):
        return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')

    return (
        header
        + '\n'.join(
            f' Dialogue: 0,{ass_time(c["start"])},{ass_time(c["end"])},Default,,0,0,0,,{plain(c["text"])}'.lstrip()
            for c in cues
        )
        + '\n'
    )


async def artifact(id, user, format):
    await completed_job(id, user)
    item = await records.get(identifier(id), user.id)
    if not item or not item.get('cues'):
        raise HTTPException(409, '字幕尚未准备好')
    if format == 'mp4':
        if item['status'] in ACTIVE:
            raise HTTPException(409, '字幕正在处理，请等待完成后下载或发送')
        if item.get('rendered_version') != item['version'] or not item.get('render_asset'):
            raise HTTPException(409, '字幕已修改或尚未烧录，请生成当前字幕版视频')
        source = media.path(item['render_asset'])
        if not source.is_file():
            raise HTTPException(404, '字幕版文件不存在，请重新烧录')
        return source, item
    return export(item, format), item


async def execute(item):
    async with studio.asset_lock():
        job = await records.get(item['job_id'], item['user_id'])
        if not job or job.get('deleted_at'):
            await records.change(item, 'failed', error='视频已删除')
            return
        item = await records.change(item, 'running', error=None)
    if not item:
        return
    prefix = job['id'] + '-caption'
    temporary = [media.path(prefix + suffix) for suffix in ('-audio.wav', '-request.json', '-result.json')]
    try:
        source = media.path(job['id'] + '.mp4')
        duration, streams = await media.probe(source)
        video = next(s for s in streams if s.get('codec_type') == 'video')
        if item['operation'] == 'generate':
            wav, request, output = temporary
            await media.command(
                'ffmpeg',
                '-nostdin',
                '-v',
                'error',
                '-y',
                '-protocol_whitelist',
                'file,pipe',
                '-i',
                source,
                '-vn',
                '-ac',
                '1',
                '-ar',
                '16000',
                wav,
            )
            os.chmod(wav, 0o600)
            media.atomic_bytes(
                request,
                json.dumps(
                    dict(
                        audio=str(wav), text=item.get('source_text', ''), align=item['align'], language=item['language']
                    )
                ).encode(),
            )
            await media.command(python_path(), ROOT / 'scripts/subtitle-engine.py', request, output, timeout=3600)
            result = json.loads(output.read_text())
            # Model output is untrusted; clip only to the actual media, discard empty spans.
            cues = []
            previous = 0.0
            for cue in result['cues']:
                start, end = float(cue['start']), float(cue['end'])
                if not math.isfinite(start) or not math.isfinite(end):
                    raise ValueError('字幕时间轴包含无效数值')
                start, end = max(previous, start, 0), min(duration, end)
                if end > start and str(cue['text']).strip():
                    cues.append(dict(start=start, end=end, text=cue['text']))
                    previous = end
            cues = validate_cues(cues, duration)
            async with studio.asset_lock():
                await records.change(
                    item,
                    'completed',
                    cues=cues,
                    duration=duration,
                    width=video['width'],
                    height=video['height'],
                    mode=result['mode'],
                    version=item['version'] + 1,
                )
        else:
            filters = await media.command(ffmpeg_path(), '-hide_banner', '-filters')
            if b' ass ' not in filters:
                raise ValueError('FFmpeg 缺少 libass，请安装 ffmpeg-full')
            ass = media.path(prefix + '.ass')
            target = media.path(f'{prefix}-v{item["version"]}.mp4')
            temp = media.path(prefix + '-render.tmp.mp4')
            temporary.extend([ass, temp])
            media.atomic_bytes(ass, export(item, 'ass').encode())
            # Escaped local server path, never an arbitrary client filter expression.
            escaped = str(ass).replace('\\', '\\\\').replace(':', '\\:').replace("'", "'\\''")
            await media.command(
                ffmpeg_path(),
                '-nostdin',
                '-v',
                'error',
                '-y',
                '-protocol_whitelist',
                'file,pipe',
                '-i',
                source,
                '-vf',
                f"ass=filename='{escaped}'",
                '-map',
                '0:v:0',
                '-map',
                '0:a:0',
                '-c:v',
                'libx264',
                '-preset',
                'medium',
                '-crf',
                '20',
                '-pix_fmt',
                'yuv420p',
                '-c:a',
                'copy',
                '-movflags',
                '+faststart',
                temp,
                timeout=3600,
            )
            await media.validate_video(temp, duration)
            digest = await asyncio.to_thread(media.digest, temp)
            async with studio.asset_lock():
                os.chmod(temp, 0o600)
                os.replace(temp, target)
                updated = await records.change(
                    item, 'completed', rendered_version=item['version'], render_asset=target.name, render_hash=digest
                )
                if updated:
                    for old in media.directory().glob(prefix + '-v*.mp4'):
                        if old != target:
                            old.unlink(missing_ok=True)
    except asyncio.CancelledError:
        await records.change(item, 'failed', error='字幕处理被中断，可重新操作')
        raise
    except Exception as exc:
        log.warning('Caption task failed id=%s operation=%s type=%s', item['id'], item['operation'], type(exc).__name__)
        error = (
            exc.detail
            if isinstance(exc, HTTPException)
            else str(exc)
            if isinstance(exc, ValueError)
            else '本地字幕处理失败，请检查字幕运行环境或重新操作'
        )
        await records.change(item, 'failed', error=error[:300])
    finally:
        for file in temporary:
            file.unlink(missing_ok=True)


async def worker():
    import fcntl

    with (media.directory() / 'captions.lock').open('a') as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        for item in await records.listing(kind='caption', statuses=['running'], limit=10000):
            await records.change(item, 'failed', error='服务重启中断字幕处理，请重试')
            for suffix in ('-audio.wav', '-request.json', '-result.json', '.ass', '-render.tmp.mp4'):
                try:
                    media.path(item['job_id'] + '-caption' + suffix).unlink(missing_ok=True)
                except OSError:
                    log.warning('Interrupted caption temporary file cleanup deferred')
        while True:
            try:
                for item in await records.listing(kind='caption', statuses=['queued'], oldest=True, limit=100):
                    await execute(item)
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('Caption worker unavailable (%s)', type(exc).__name__)
                await asyncio.sleep(5)
