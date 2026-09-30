"""Private immutable image/audio assets and bounded FFmpeg operations."""

import asyncio
import hashlib
import io
import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from fastapi import HTTPException
from open_webui.env import DATA_DIR

DIRECTORY = Path(DATA_DIR) / 'video-studio'


def directory():
    DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(DIRECTORY, 0o700)
    return DIRECTORY


def path(name):
    # Database-generated names only, but keep path traversal impossible at this boundary.
    if not name or Path(name).name != name or name.startswith('.'):
        raise ValueError('Invalid media reference')
    return directory() / name


def digest(source):
    with source.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_bytes(target, data):
    temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            os.chmod(temp, 0o600)
            stream.write(data)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def save_portrait(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1:
                raise ValueError()
            width, height = image.size
            if min(width, height) < 256 or width * height > 24_000_000:
                raise ValueError()
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((2048, 2048))
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=95)
            normalized = output.getvalue()
            version = uuid.uuid4().hex
            name = version + '.jpg'
            atomic_bytes(path(name), normalized)
            return dict(
                asset=name,
                version=version,
                asset_hash=hashlib.sha256(normalized).hexdigest(),
                width=image.width,
                height=image.height,
                input_type='image',
            )
    except (ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(400, '请上传可解码的单张 JPG/PNG；短边至少 256 像素，总像素不超过 2400 万') from None


async def command(tool, *args, timeout=120, stderr=False):
    process = await asyncio.create_subprocess_exec(
        shutil.which(tool) or f'/opt/homebrew/bin/{tool}',
        *map(str, args),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise ValueError('媒体处理失败，请检查素材或 FFmpeg 安装')
        return err if stderr else out
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise


async def probe(source):
    out = await command(
        'ffprobe',
        '-v',
        'error',
        '-protocol_whitelist',
        'file,pipe',
        '-show_format',
        '-show_streams',
        '-of',
        'json',
        source,
    )
    info = json.loads(out)
    duration = float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('无法读取媒体时长')
    return duration, info.get('streams', [])


async def preview_audio(source, target):
    # Find a pause close to 15 s when possible, with a hard 15 s bound.
    duration, _ = await probe(source)
    end = min(duration, 15)
    if duration > 15:
        pauses = await command(
            'ffmpeg',
            '-nostdin',
            '-v',
            'info',
            '-protocol_whitelist',
            'file,pipe',
            '-i',
            source,
            '-t',
            15,
            '-af',
            'silencedetect=noise=-35dB:d=0.18',
            '-f',
            'null',
            '-',
            stderr=True,
        )
        boundaries = [float(value) for value in re.findall(rb'silence_end: ([0-9.]+)', pauses)]
        end = max((value for value in boundaries if 12 <= value <= 15), default=15)
        # Speech boundaries are not guaranteed; a short fade avoids an abrupt click.
        fade = max(0, end - 0.06)
    else:
        fade = end
    temp = path(target.name + '.tmp.mp3')
    try:
        await command(
            'ffmpeg',
            '-nostdin',
            '-v',
            'error',
            '-y',
            '-protocol_whitelist',
            'file,pipe',
            '-i',
            source,
            '-t',
            end,
            '-af',
            f'afade=t=out:st={fade}:d=0.06',
            '-c:a',
            'libmp3lame',
            '-b:a',
            '128k',
            temp,
        )
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return end


async def validate_video(source, expected_duration):
    duration, streams = await probe(source)
    kinds = {stream.get('codec_type') for stream in streams}
    if not {'audio', 'video'}.issubset(kinds) or abs(duration - expected_duration) > max(2, expected_duration * 0.05):
        raise ValueError('视频轨道或时长异常，请重新下载已有视频')
    await command(
        'ffmpeg',
        '-nostdin',
        '-v',
        'error',
        '-xerror',
        '-protocol_whitelist',
        'file,pipe',
        '-i',
        source,
        '-f',
        'null',
        '-',
        timeout=600,
    )
    return duration
