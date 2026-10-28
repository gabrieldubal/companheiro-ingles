"""Fala -> texto com o Whisper rodando na CPU desta máquina."""
import io
import os
import threading
import time

from . import config
from .cpu import HEAVY

_model = None
_lock = threading.Lock()  # protege o carregamento; a transcrição usa a trava de CPU

# O Whisper usa este texto como "fala anterior". Com hesitações aqui, ele tende
# a transcrever do jeito que você falou, em vez de arrumar a frase.
_FILLERS = "Um, so... I work with, uh, data science. Yesterday I go to the office and, hmm, I talk with my boss."


def _vocab() -> list[str]:
    if not config.VOCAB.exists():
        return []
    lines = (l.strip() for l in config.VOCAB.read_text(encoding="utf-8").splitlines())
    return [l for l in lines if l and not l.startswith("#")][:40]


def _prompt(terms: list[str]) -> str:
    """Hesitações + o seu vocabulário (vocabulario.txt), para ele acertar nomes como Claude e Bedrock."""
    return _FILLERS + (" Words I use: " + ", ".join(terms) + "." if terms else "")


def _clean(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum() or ch in "'-.")


def load():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            t0 = time.time()
            _model = WhisperModel(
                config.WHISPER_MODEL, device="cpu", compute_type="int8",
                cpu_threads=os.cpu_count() or 4,
            )
            print(f"[stt] Whisper {config.WHISPER_MODEL} carregado em {time.time() - t0:.1f}s")
    return _model


def is_ready() -> bool:
    return _model is not None


def _decode(audio: bytes):
    """Áudio do celular (webm, mp4, wav) -> mono 16 kHz em float32, como o Whisper espera.
    Feito aqui porque o decode_audio do faster-whisper quebra com o PyAV 19."""
    import av
    import numpy as np

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    with av.open(io.BytesIO(audio), mode="r") as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):  # esvazia o que sobrou no resampler
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe(audio: bytes, conversation: bool = True) -> dict:
    """Texto + cada palavra com início, fim e confiança. A confiança baixa é a primeira
    pista de pronúncia: se o Whisper ficou em dúvida, um nativo provavelmente também ficaria.

    conversation=False (leitura em voz alta): sem dica nenhuma. As hesitações e o
    vocabulário atrapalham em frase curta e lida, e qualquer dica puxa o Whisper para longe
    do que você falou de fato."""
    return transcribe_samples(_decode(audio), conversation)


def transcribe_samples(samples, conversation: bool = False) -> dict:
    """O mesmo, para um trecho já decodificado (o Imitar corta a gravação do conjunto em pedaços)."""
    model = load()
    terms = _vocab() if conversation else []
    # Nomes próprios saem com confiança baixa mesmo quando certos ("Claude" deu 0,01): nunca marcar.
    known = {_clean(t).strip(".") for term in terms for t in term.split()}
    t0 = time.time()
    with HEAVY:
        segments, info = model.transcribe(
            # beam 5: nos testes, preservou "I go" onde o beam 1 inventou outra frase
            samples, language="en", beam_size=5, vad_filter=True,
            initial_prompt=_prompt(terms) if conversation else None, condition_on_previous_text=False,
            word_timestamps=True,
        )
        parts, words = [], []
        for seg in segments:
            parts.append(seg.text.strip())
            for w in seg.words or []:
                p = float(w.probability)  # vem como tipo do numpy, que o JSON não aceita
                words.append({
                    "w": w.word.strip(), "start": round(float(w.start), 2), "end": round(float(w.end), 2),
                    "p": round(p, 3),
                    "unsure": bool(p < config.UNSURE_PROB and _clean(w.word).strip(".") not in known),
                })
    took = time.time() - t0
    print(f"[stt] {info.duration:.1f}s de áudio em {took:.1f}s")
    return {
        "text": " ".join(parts).strip(), "words": words,
        "seconds": round(took, 1), "audio_seconds": round(info.duration, 1),
    }
