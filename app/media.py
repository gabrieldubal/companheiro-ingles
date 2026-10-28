"""Áudio: receber do navegador, guardar em data/audio/ e recortar trechos para ouvir de novo."""
import io
import wave
from datetime import datetime

from fastapi import HTTPException, UploadFile

from . import config

AUDIO_EXT = {"webm", "m4a", "mp4", "ogg", "wav"}


async def read_upload(file: UploadFile) -> bytes:
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "Áudio vazio.")
    if len(audio) > 20 * 1024 * 1024:
        raise HTTPException(413, "Áudio grande demais (máximo de uns 10 minutos).")
    return audio


def save_audio(audio: bytes, filename: str | None, folder: str, prefix: str = "") -> str:
    """Salva em data/audio/<pasta>/ e devolve o caminho relativo a data/."""
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    ext = ext if ext in AUDIO_EXT else "bin"
    target = config.AUDIO / folder
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{prefix}{datetime.now():%Y%m%d-%H%M%S-%f}.{ext}"
    path.write_bytes(audio)
    return str(path.relative_to(config.DATA))


def clip_wav(rel_path: str, start: float | None, end: float | None, pad: float = 0.25) -> bytes:
    """Um trecho da gravação em WAV (o webm do navegador não deixa pular para um segundo exato)."""
    import numpy as np

    from .stt import _decode

    samples = _decode((config.DATA / rel_path).read_bytes())
    sr = 16000
    a = int(max(0.0, (start or 0) - pad) * sr)
    b = int(((end + pad) if end is not None else len(samples) / sr) * sr)
    seg = np.clip(samples[a:b], -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((seg * 32767).astype("<i2").tobytes())
    return buf.getvalue()
