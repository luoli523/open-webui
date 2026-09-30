"""Isolated local alignment adapter. JSON files are private, server-generated paths."""

import json
import os
import sys
from pathlib import Path


def main():
    import torch
    import stable_whisper

    torch.set_num_threads(4)
    request = json.loads(Path(sys.argv[1]).read_text())
    checkpoint = Path(os.environ.get('STUDIO_WHISPER_MODEL', '~/.cache/whisper/small.pt')).expanduser()
    if not checkpoint.is_file():
        raise RuntimeError('Local Whisper checkpoint missing')
    # Local checkpoint only: never implicitly download a model or contact a cloud API.
    model = stable_whisper.load_model(str(checkpoint), device='cpu')
    language = request.get('language') or None
    text = request.get('text', '').strip()
    mode = 'asr'
    if text and request['align']:
        if not language:
            # Detect language from the actual audio, rather than guessing from characters.
            import whisper

            audio = whisper.load_audio(request['audio'])
            mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(audio), n_mels=model.dims.n_mels).to(model.device)
            _, probabilities = model.detect_language(mel)
            language = max(probabilities, key=probabilities.get)
        result = model.align(request['audio'], text, language=language, verbose=None)
        mode = 'alignment'
    else:
        result = model.transcribe(
            request['audio'],
            language=language,
            verbose=None,
            fp16=False,
            initial_prompt=text[:200] or None,
            condition_on_previous_text=False,
        )
    if result is None:
        raise RuntimeError('Alignment returned no speech')
    result.split_by_punctuation(['。', '！', '？', '.', '!', '?']).split_by_length(max_chars=32)
    cues = [dict(start=s.start, end=s.end, text=s.text.strip()) for s in result.segments if s.text.strip()]
    Path(sys.argv[2]).write_text(json.dumps(dict(cues=cues, mode=mode), ensure_ascii=False))
    os.chmod(sys.argv[2], 0o600)


if __name__ == '__main__':
    main()
