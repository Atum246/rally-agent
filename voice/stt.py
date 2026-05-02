"""
Rally Agent — Speech-to-Text Engine
=====================================
Multi-backend STT with graceful fallbacks:
  1. Whisper (local, highest quality)
  2. Vosk (local, lightweight)
  3. External API fallback placeholder

Features:
  - WebRTC Voice Activity Detection (VAD)
  - Real-time streaming transcription
  - Multi-language support
"""

from __future__ import annotations

import abc
import audioop
import io
import json
import logging
import os
import struct
import tempfile
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger("rally.voice.stt")


# ============================= Data Types ==================================

@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    language: Optional[str] = None
    segments: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    engine: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A chunk of transcription from streaming."""
    text: str
    is_final: bool
    confidence: float = 0.0
    start_ms: int = 0
    end_ms: int = 0


# ============================= VAD ========================================

class VoiceActivityDetector:
    """
    Simple energy-based Voice Activity Detection.
    Falls back to webrtcvad if available.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 2,
        energy_threshold: float = 300.0,
        silence_timeout_ms: int = 1500,
        min_speech_ms: int = 300,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.aggressiveness = aggressiveness
        self.energy_threshold = energy_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.min_speech_ms = min_speech_ms

        self._webrtc_vad = None
        try:
            import webrtcvad
            self._webrtc_vad = webrtcvad.Vad(aggressiveness)
            logger.info("Using WebRTC VAD (aggressiveness=%d)", aggressiveness)
        except ImportError:
            logger.info("webrtcvad not available, using energy-based VAD")

    def is_speech(self, frame: bytes) -> bool:
        """Check if an audio frame contains speech."""
        if self._webrtc_vad is not None:
            try:
                return self._webrtc_vad.is_speech(frame, self.sample_rate)
            except Exception:
                pass

        # Energy-based fallback
        try:
            energy = audioop.rms(frame, 2)  # 16-bit samples
            return energy > self.energy_threshold
        except Exception:
            return False

    def process_audio(
        self,
        audio_stream: Generator[bytes, None, None],
    ) -> Generator[Tuple[bytes, bool], None, None]:
        """
        Process an audio stream and yield (frame, is_speech) tuples.
        Useful for separating speech from silence.
        """
        frame_size = int(self.sample_rate * self.frame_duration_ms / 1000) * 2  # bytes
        buffer = b""

        for chunk in audio_stream:
            buffer += chunk
            while len(buffer) >= frame_size:
                frame = buffer[:frame_size]
                buffer = buffer[frame_size:]
                yield frame, self.is_speech(frame)


# ============================= Base Engine =================================

class STTEngineBase(abc.ABC):
    """Abstract base for STT engines."""

    @abc.abstractmethod
    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file."""
        ...

    def transcribe_bytes(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe raw audio bytes. Default: write to temp file."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            # Write WAV header + data
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data)
            path = f.name
        try:
            return self.transcribe_file(path, language=language)
        finally:
            os.unlink(path)

    def stream_transcribe(
        self,
        audio_stream: Generator[bytes, None, None],
        sample_rate: int = 16000,
        language: Optional[str] = None,
        chunk_seconds: float = 3.0,
    ) -> Generator[StreamChunk, None, None]:
        """
        Streaming transcription — collects audio chunks and transcribes them.
        Override for true streaming support.
        """
        frame_size = int(sample_rate * chunk_seconds) * 2  # 16-bit = 2 bytes/sample
        buffer = b""
        offset_ms = 0

        for chunk in audio_stream:
            buffer += chunk
            while len(buffer) >= frame_size:
                segment = buffer[:frame_size]
                buffer = buffer[frame_size:]
                result = self.transcribe_bytes(segment, sample_rate=sample_rate, language=language)
                yield StreamChunk(
                    text=result.text,
                    is_final=True,
                    confidence=result.confidence,
                    start_ms=offset_ms,
                    end_ms=offset_ms + int(chunk_seconds * 1000),
                )
                offset_ms += int(chunk_seconds * 1000)

        # Handle remaining buffer
        if buffer:
            result = self.transcribe_bytes(buffer, sample_rate=sample_rate, language=language)
            yield StreamChunk(
                text=result.text,
                is_final=True,
                confidence=result.confidence,
                start_ms=offset_ms,
                end_ms=offset_ms + len(buffer) // (sample_rate * 2 // 1000),
            )

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def supported_languages(self) -> List[str]:
        return ["en"]


# ============================= Whisper Engine ==============================

class WhisperSTT(STTEngineBase):
    """OpenAI Whisper local STT engine."""

    def __init__(self, model_name: str = "base", device: Optional[str] = None) -> None:
        try:
            import whisper
            self._model = whisper.load_model(model_name, device=device)
            self._model_name = model_name
            logger.info("Whisper model '%s' loaded", model_name)
        except ImportError:
            raise ImportError("openai-whisper not installed: pip install openai-whisper")
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}")

    @property
    def name(self) -> str:
        return f"whisper-{self._model_name}"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        # Whisper supports 99 languages
        return [
            "en", "zh", "de", "es", "ru", "ko", "fr", "ja", "pt", "tr",
            "pl", "ca", "nl", "ar", "sv", "it", "id", "hi", "fi", "vi",
            "he", "uk", "el", "ms", "cs", "ro", "da", "hu", "ta", "no",
            "th", "ur", "hr", "bg", "lt", "la", "mi", "ml", "cy", "sk",
            "te", "fa", "lv", "bn", "sr", "az", "sl", "kn", "et", "mk",
            "br", "eu", "is", "hy", "ne", "mn", "bs", "kk", "sq", "sw",
            "gl", "mr", "pa", "si", "km", "sn", "yo", "so", "af", "oc",
            "ka", "be", "tg", "sd", "gu", "am", "yi", "lo", "uz", "fo",
            "ht", "ps", "tk", "nn", "mt", "sa", "lb", "my", "bo", "tl",
            "mg", "as", "tt", "haw", "ln", "ha", "ba", "jw", "su",
        ]

    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        import whisper

        kwargs: Dict[str, Any] = {}
        if language:
            kwargs["language"] = language

        result = self._model.transcribe(audio_path, **kwargs)

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "avg_logprob": seg.get("avg_logprob", 0),
            })

        # Average confidence from segments
        confidences = [s.get("avg_logprob", -1) for s in result.get("segments", [])]
        avg_conf = 0.0
        if confidences:
            # Convert log prob to 0-1 scale
            avg_conf = max(0.0, min(1.0, 1.0 + sum(confidences) / len(confidences)))

        duration = 0.0
        if segments:
            duration = segments[-1]["end"]

        return TranscriptionResult(
            text=result["text"].strip(),
            confidence=avg_conf,
            language=result.get("language"),
            segments=segments,
            duration_seconds=duration,
            engine=self.name,
            raw=result,
        )

    def stream_transcribe(
        self,
        audio_stream: Generator[bytes, None, None],
        sample_rate: int = 16000,
        language: Optional[str] = None,
        chunk_seconds: float = 5.0,
    ) -> Generator[StreamChunk, None, None]:
        """Whisper streaming with VAD-based endpointing."""
        import numpy as np

        vad = VoiceActivityDetector(sample_rate=sample_rate)
        buffer = b""
        speech_buffer = b""
        silence_frames = 0
        chunk_samples = int(sample_rate * chunk_seconds)

        for frame, is_speech in vad.process_audio(audio_stream):
            if is_speech:
                speech_buffer += frame
                silence_frames = 0
            else:
                silence_frames += 1

            # End of speech segment
            if silence_frames > 30 and speech_buffer:  # ~1s silence
                result = self.transcribe_bytes(speech_buffer, sample_rate=sample_rate, language=language)
                if result.text.strip():
                    yield StreamChunk(
                        text=result.text,
                        is_final=True,
                        confidence=result.confidence,
                    )
                speech_buffer = b""
                silence_frames = 0

            # Also yield if buffer gets too long
            if len(speech_buffer) >= chunk_samples * 2:
                result = self.transcribe_bytes(speech_buffer, sample_rate=sample_rate, language=language)
                yield StreamChunk(
                    text=result.text,
                    is_final=False,
                    confidence=result.confidence,
                )
                speech_buffer = b""

        # Final flush
        if speech_buffer:
            result = self.transcribe_bytes(speech_buffer, sample_rate=sample_rate, language=language)
            if result.text.strip():
                yield StreamChunk(
                    text=result.text,
                    is_final=True,
                    confidence=result.confidence,
                )


# ============================= Vosk Engine =================================

class VoskSTT(STTEngineBase):
    """Vosk offline STT engine (lightweight)."""

    def __init__(self, model_path: Optional[str] = None, lang: str = "en") -> None:
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError:
            raise ImportError("vosk not installed: pip install vosk")

        if model_path:
            self._model = Model(model_path)
        else:
            # Try to use a pre-downloaded model
            default_path = os.path.expanduser(f"~/.rally/models/vosk-{lang}")
            if os.path.isdir(default_path):
                self._model = Model(default_path)
            else:
                raise RuntimeError(
                    f"Vosk model not found at {default_path}. "
                    f"Download from https://alphacephei.com/vosk/models"
                )

        self._lang = lang
        self._KaldiRecognizer = KaldiRecognizer
        logger.info("Vosk model loaded (lang=%s)", lang)

    @property
    def name(self) -> str:
        return f"vosk-{self._lang}"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        return [
            "en", "zh", "ru", "fr", "de", "es", "pt", "vi", "it", "nl",
            "uk", "ja", "hi", "ar", "ko", "tr", "pl", "ca", "fa", "sv",
            "mn", "tl", "th", "uz", "ta", "te",
        ]

    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        wf = wave.open(audio_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("Vosk requires mono 16-bit WAV audio")

        sample_rate = wf.getframerate()
        rec = self._KaldiRecognizer(self._model, sample_rate)
        rec.SetWords(True)

        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result.get("text"):
                    results.append(result)

        # Final result
        final = json.loads(rec.FinalResult())
        if final.get("text"):
            results.append(final)

        full_text = " ".join(r.get("text", "") for r in results).strip()

        # Aggregate confidence
        confidences = []
        for r in results:
            for word_info in r.get("result", []):
                confidences.append(word_info.get("conf", 0))
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5

        segments = []
        for r in results:
            for word_info in r.get("result", []):
                segments.append({
                    "start": word_info.get("start", 0),
                    "end": word_info.get("end", 0),
                    "text": word_info.get("word", ""),
                    "conf": word_info.get("conf", 0),
                })

        duration = segments[-1]["end"] if segments else 0.0

        return TranscriptionResult(
            text=full_text,
            confidence=avg_conf,
            language=language or self._lang,
            segments=segments,
            duration_seconds=duration,
            engine=self.name,
        )

    def stream_transcribe(
        self,
        audio_stream: Generator[bytes, None, None],
        sample_rate: int = 16000,
        language: Optional[str] = None,
        chunk_seconds: float = 0.5,
    ) -> Generator[StreamChunk, None, None]:
        """True streaming transcription with Vosk."""
        rec = self._KaldiRecognizer(self._model, sample_rate)
        rec.SetWords(True)

        for chunk in audio_stream:
            if rec.AcceptWaveform(chunk):
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                if text:
                    confs = [w.get("conf", 0) for w in result.get("result", [])]
                    yield StreamChunk(
                        text=text,
                        is_final=True,
                        confidence=sum(confs) / len(confs) if confs else 0.5,
                    )
            else:
                partial = json.loads(rec.PartialResult())
                text = partial.get("partial", "").strip()
                if text:
                    yield StreamChunk(
                        text=text,
                        is_final=False,
                        confidence=0.3,
                    )

        # Final flush
        final = json.loads(rec.FinalResult())
        text = final.get("text", "").strip()
        if text:
            yield StreamChunk(
                text=text,
                is_final=True,
                confidence=0.5,
            )


# ============================= Engine Factory ===============================

def get_stt_engine(
    engine: str = "auto",
    **kwargs: Any,
) -> STTEngineBase:
    """
    Get the best available STT engine.

    Priority: whisper > vosk > error

    Args:
        engine: "whisper", "vosk", or "auto" (default)
        **kwargs: passed to engine constructor
    """
    if engine == "whisper" or engine == "auto":
        try:
            return WhisperSTT(**kwargs)
        except (ImportError, RuntimeError) as e:
            if engine == "whisper":
                raise
            logger.debug("Whisper unavailable: %s", e)

    if engine == "vosk" or engine == "auto":
        try:
            return VoskSTT(**kwargs)
        except (ImportError, RuntimeError) as e:
            if engine == "vosk":
                raise
            logger.debug("Vosk unavailable: %s", e)

    raise RuntimeError(
        "No STT engine available. Install one of:\n"
        "  pip install openai-whisper\n"
        "  pip install vosk"
    )


# ============================= Audio Utilities ==============================

def record_audio(
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    channels: int = 1,
) -> bytes:
    """Record audio from the default microphone."""
    try:
        import pyaudio
    except ImportError:
        raise ImportError("pyaudio not installed: pip install pyaudio")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=1024,
    )

    frames = []
    num_frames = int(sample_rate / 1024 * duration_seconds)
    for _ in range(num_frames):
        frames.append(stream.read(1024))

    stream.stop_stream()
    stream.close()
    pa.terminate()

    return b"".join(frames)


def record_until_silence(
    sample_rate: int = 16000,
    silence_timeout_ms: int = 2000,
    min_record_ms: int = 500,
    energy_threshold: float = 300.0,
) -> bytes:
    """Record audio until silence is detected."""
    try:
        import pyaudio
    except ImportError:
        raise ImportError("pyaudio not installed: pip install pyaudio")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=1024,
    )

    vad = VoiceActivityDetector(
        sample_rate=sample_rate,
        energy_threshold=energy_threshold,
        silence_timeout_ms=silence_timeout_ms,
    )

    frames = []
    speech_started = False
    silence_start = 0.0
    record_start = time.time()

    try:
        while True:
            data = stream.read(1024, exception_on_overflow=False)
            is_speech = vad.is_speech(data)

            if is_speech:
                speech_started = True
                silence_start = 0
                frames.append(data)
            elif speech_started:
                frames.append(data)
                if silence_start == 0:
                    silence_start = time.time()
                elif (time.time() - silence_start) * 1000 > silence_timeout_ms:
                    # Check minimum recording time
                    if (time.time() - record_start) * 1000 >= min_record_ms:
                        break

            # Timeout if no speech starts
            if not speech_started and (time.time() - record_start) > 10:
                break
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    return b"".join(frames)
