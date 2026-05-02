"""
Rally Agent — Text-to-Speech Engine
=====================================
Multi-backend TTS with graceful fallbacks:
  1. Coqui TTS (local, free, high quality)
  2. ElevenLabs API (cloud, best quality, voice cloning)
  3. Edge TTS (free, good quality, Microsoft)

Features:
  - Voice cloning support
  - Emotional tone adjustment
  - SSML support
  - Audio streaming
"""

from __future__ import annotations

import abc
import asyncio
import io
import logging
import os
import re
import tempfile
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

logger = logging.getLogger("rally.voice.tts")


# ============================= Data Types ==================================

@dataclass
class VoiceInfo:
    voice_id: str
    name: str
    language: str = "en"
    gender: Optional[str] = None
    preview_url: Optional[str] = None
    engine: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpeechResult:
    audio_data: bytes
    sample_rate: int = 24000
    sample_width: int = 2
    channels: int = 1
    duration_seconds: float = 0.0
    engine: str = ""
    format: str = "wav"


@dataclass
class TTSSettings:
    """Settings for TTS synthesis."""
    voice_id: Optional[str] = None
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: Optional[str] = None  # "neutral", "happy", "sad", "angry", "excited"
    ssml: bool = False


# ============================= Base Engine =================================

class TTSEngineBase(abc.ABC):
    """Abstract base for TTS engines."""

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
    ) -> SpeechResult:
        """Synthesize text to audio."""
        ...

    def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        settings: Optional[TTSSettings] = None,
    ) -> str:
        """Synthesize text and save to a WAV file."""
        result = self.synthesize(text, settings)
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(result.channels)
            wf.setsampwidth(result.sample_width)
            wf.setframerate(result.sample_rate)
            wf.writeframes(result.audio_data)
        return output_path

    def stream_synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
        chunk_size: int = 4096,
    ) -> Generator[bytes, None, None]:
        """
        Stream synthesized audio in chunks.
        Default implementation: synthesize all, then yield chunks.
        Override for true streaming.
        """
        result = self.synthesize(text, settings)
        data = result.audio_data
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    @abc.abstractmethod
    def list_voices(self, language: Optional[str] = None) -> List[VoiceInfo]:
        """List available voices."""
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @property
    def supports_ssml(self) -> bool:
        return False

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def supports_voice_cloning(self) -> bool:
        return False


# ============================= Coqui TTS ===================================

class CoquiTTSEngine(TTSEngineBase):
    """Coqui TTS — local, free, high-quality."""

    def __init__(
        self,
        model_name: str = "tts_models/en/ljspeech/tacotron2-DDC",
        device: Optional[str] = None,
    ) -> None:
        try:
            from TTS.api import TTS as CoquiTTS
            self._tts = CoquiTTS(model_name=model_name, progress_bar=False)
            if device:
                self._tts.to(device)
            self._model_name = model_name
            logger.info("Coqui TTS loaded: %s", model_name)
        except ImportError:
            raise ImportError("TTS not installed: pip install TTS")
        except Exception as e:
            raise RuntimeError(f"Failed to load Coqui TTS: {e}")

    @property
    def name(self) -> str:
        return "coqui"

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return False

    def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
    ) -> SpeechResult:
        settings = settings or TTSSettings()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            kwargs: Dict[str, Any] = {}
            if settings.voice_id:
                kwargs["speaker"] = settings.voice_id
            if settings.language:
                kwargs["language"] = settings.language

            self._tts.tts_to_file(text=text, file_path=output_path, **kwargs)

            # Read the generated WAV
            with wave.open(output_path, "rb") as wf:
                audio_data = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                channels = wf.getnchannels()
                duration = wf.getnframes() / sample_rate

            return SpeechResult(
                audio_data=audio_data,
                sample_rate=sample_rate,
                sample_width=sample_width,
                channels=channels,
                duration_seconds=duration,
                engine=self.name,
            )
        finally:
            os.unlink(output_path)

    def clone_voice(
        self,
        reference_audio_path: str,
        text: str,
        settings: Optional[TTSSettings] = None,
    ) -> SpeechResult:
        """Clone a voice from reference audio and synthesize new text."""
        settings = settings or TTSSettings()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            self._tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker_wav=reference_audio_path,
            )

            with wave.open(output_path, "rb") as wf:
                audio_data = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
                duration = wf.getnframes() / sample_rate

            return SpeechResult(
                audio_data=audio_data,
                sample_rate=sample_rate,
                duration_seconds=duration,
                engine=f"{self.name}-clone",
            )
        finally:
            os.unlink(output_path)

    def list_voices(self, language: Optional[str] = None) -> List[VoiceInfo]:
        voices = []
        try:
            speakers = self._tts.speakers if hasattr(self._tts, 'speakers') else []
            for speaker in (speakers or []):
                voices.append(VoiceInfo(
                    voice_id=speaker if isinstance(speaker, str) else speaker.get("name", ""),
                    name=speaker if isinstance(speaker, str) else speaker.get("name", ""),
                    engine="coqui",
                ))
        except Exception:
            pass
        return voices


# ============================= ElevenLabs ==================================

class ElevenLabsTTSEngine(TTSEngineBase):
    """ElevenLabs API — cloud, best quality, voice cloning."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self._api_key:
            raise ValueError(
                "ElevenLabs API key required. Set ELEVENLABS_API_KEY or pass api_key."
            )
        self._base_url = "https://api.elevenlabs.io/v1"
        logger.info("ElevenLabs TTS initialized")

    @property
    def name(self) -> str:
        return "elevenlabs"

    @property
    def supports_ssml(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
    ) -> SpeechResult:
        import urllib.request
        import urllib.error

        settings = settings or TTSSettings()
        voice_id = settings.voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel

        url = f"{self._base_url}/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        body: Dict[str, Any] = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        if settings.emotion:
            # Map emotion to voice settings
            emotion_map = {
                "happy": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.5},
                "sad": {"stability": 0.8, "similarity_boost": 0.6, "style": 0.3},
                "angry": {"stability": 0.2, "similarity_boost": 0.9, "style": 0.8},
                "excited": {"stability": 0.2, "similarity_boost": 0.9, "style": 0.7},
                "neutral": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0},
            }
            if settings.emotion in emotion_map:
                body["voice_settings"].update(emotion_map[settings.emotion])

        req = urllib.request.Request(
            url,
            data=__import__("json").dumps(body).encode(),
            headers=headers,
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_data = resp.read()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"ElevenLabs API error {e.code}: {error_body}")

        # ElevenLabs returns MP3, need to convert to WAV
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(io.BytesIO(audio_data))
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_data = wav_io.getvalue()
            return SpeechResult(
                audio_data=wav_data,
                sample_rate=audio.frame_rate,
                sample_width=audio.sample_width,
                channels=audio.channels,
                duration_seconds=len(audio) / 1000.0,
                engine=self.name,
                format="wav",
            )
        except ImportError:
            # No pydub — return raw MP3
            return SpeechResult(
                audio_data=audio_data,
                engine=self.name,
                format="mp3",
            )

    def stream_synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
        chunk_size: int = 4096,
    ) -> Generator[bytes, None, None]:
        """Stream audio from ElevenLabs."""
        import urllib.request
        import json as _json

        settings = settings or TTSSettings()
        voice_id = settings.voice_id or "21m00Tcm4TlvDq8ikWAM"

        url = f"{self._base_url}/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        req = urllib.request.Request(
            url,
            data=_json.dumps(body).encode(),
            headers=headers,
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def clone_voice(
        self,
        name: str,
        description: str,
        audio_files: List[str],
    ) -> str:
        """Clone a voice from audio samples. Returns voice_id."""
        import urllib.request
        from email.mime.multipart import MIMEMultipart

        url = f"{self._base_url}/voices/add"
        boundary = "----RallyBoundary"

        body_parts = []
        body_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{name}')
        if description:
            body_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="description"\r\n\r\n{description}')

        body = "\r\n".join(body_parts).encode()

        for i, audio_path in enumerate(audio_files):
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            ext = Path(audio_path).suffix.lstrip(".") or "wav"
            part = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="files"; filename="sample{i}.{ext}"\r\n'
                f'Content-Type: audio/{ext}\r\n\r\n'
            ).encode() + audio_data + b"\r\n"
            body += part

        body += f'--{boundary}--\r\n'.encode()

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = __import__("json").loads(resp.read())
            return result.get("voice_id", "")

    def list_voices(self, language: Optional[str] = None) -> List[VoiceInfo]:
        import urllib.request

        req = urllib.request.Request(
            f"{self._base_url}/voices",
            headers={"xi-api-key": self._api_key},
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = __import__("json").loads(resp.read())

        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels", {})
            lang = labels.get("language", "en")
            if language and lang != language:
                continue
            voices.append(VoiceInfo(
                voice_id=v["voice_id"],
                name=v["name"],
                language=lang,
                gender=labels.get("gender"),
                engine="elevenlabs",
                extra={
                    "category": v.get("category", ""),
                    "description": v.get("description", ""),
                },
            ))
        return voices


# ============================= Edge TTS ====================================

class EdgeTTSEngine(TTSEngineBase):
    """Microsoft Edge TTS — free, good quality, many voices."""

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        try:
            import edge_tts
            self._edge_tts = edge_tts
        except ImportError:
            raise ImportError("edge-tts not installed: pip install edge-tts")
        self._default_voice = voice
        logger.info("Edge TTS initialized (default voice: %s)", voice)

    @property
    def name(self) -> str:
        return "edge-tts"

    @property
    def supports_ssml(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True

    def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
    ) -> SpeechResult:
        settings = settings or TTSSettings()
        voice = settings.voice_id or self._default_voice

        # Run async edge_tts in sync context
        audio_data = self._run_async(self._synthesize_async(text, voice, settings))

        # Parse WAV data
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wf:
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())
                duration = wf.getnframes() / sample_rate
        except Exception:
            # Raw audio, assume defaults
            sample_rate = 24000
            sample_width = 2
            channels = 1
            frames = audio_data
            duration = len(audio_data) / (sample_rate * sample_width * channels)

        return SpeechResult(
            audio_data=frames,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
            duration_seconds=duration,
            engine=self.name,
        )

    async def _synthesize_async(
        self,
        text: str,
        voice: str,
        settings: TTSSettings,
    ) -> bytes:
        """Async synthesis using edge-tts."""
        communicate = self._edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=f"{int((settings.speed - 1.0) * 100):+d}%",
            volume=f"{int((settings.volume - 1.0) * 100):+d}%",
        )

        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        return b"".join(audio_chunks)

    def stream_synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
        chunk_size: int = 4096,
    ) -> Generator[bytes, None, None]:
        """Stream synthesized audio from Edge TTS."""
        settings = settings or TTSSettings()
        voice = settings.voice_id or self._default_voice

        # We need to run async in sync context
        queue: List[bytes] = []
        done = threading.Event()

        async def _stream():
            communicate = self._edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=f"{int((settings.speed - 1.0) * 100):+d}%",
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    queue.append(chunk["data"])
            done.set()

        # Run in background thread
        def _run():
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_stream())
            loop.close()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # Yield chunks as they arrive
        while not done.is_set() or queue:
            if queue:
                data = queue.pop(0)
                for i in range(0, len(data), chunk_size):
                    yield data[i:i + chunk_size]
            else:
                done.wait(timeout=0.1)

    def list_voices(self, language: Optional[str] = None) -> List[VoiceInfo]:
        voices = self._run_async(self._list_voices_async(language))
        return voices

    async def _list_voices_async(self, language: Optional[str] = None) -> List[VoiceInfo]:
        voices_data = await self._edge_tts.list_voices()
        result = []
        for v in voices_data:
            locale = v.get("Locale", "")
            lang = locale.split("-")[0] if locale else "en"
            if language and lang != language:
                continue
            result.append(VoiceInfo(
                voice_id=v.get("ShortName", ""),
                name=v.get("FriendlyName", v.get("ShortName", "")),
                language=locale,
                gender=v.get("Gender", "").lower(),
                engine="edge-tts",
                extra={
                    "locale": locale,
                    "voice_type": v.get("VoiceType", ""),
                },
            ))
        return result

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in an async context — use a new thread
                result = [None]
                def _target():
                    new_loop = asyncio.new_event_loop()
                    result[0] = new_loop.run_until_complete(coro)
                    new_loop.close()
                t = threading.Thread(target=_target, daemon=True)
                t.start()
                t.join()
                return result[0]
            return loop.run_until_complete(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()


# ============================= SSML Helper =================================

def build_ssml(
    text: str,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    pitch: Optional[str] = None,
    volume: Optional[str] = None,
    emphasis: Optional[str] = None,
    break_after: Optional[str] = None,
) -> str:
    """Build SSML markup for fine-grained control."""
    parts = ['<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">']

    if voice:
        parts.append(f'<voice name="{voice}">')
    if rate or pitch or volume:
        prosody_attrs = []
        if rate:
            prosody_attrs.append(f'rate="{rate}"')
        if pitch:
            prosody_attrs.append(f'pitch="{pitch}"')
        if volume:
            prosody_attrs.append(f'volume="{volume}"')
        parts.append(f'<prosody {" ".join(prosody_attrs)}>')

    if emphasis:
        parts.append(f'<emphasis level="{emphasis}">')

    parts.append(text)

    if emphasis:
        parts.append('</emphasis>')
    if rate or pitch or volume:
        parts.append('</prosody>')
    if voice:
        parts.append('</voice>')
    if break_after:
        parts.append(f'<break time="{break_after}"/>')

    parts.append('</speak>')
    return "".join(parts)


# ============================= Engine Factory ===============================

def get_tts_engine(
    engine: str = "auto",
    **kwargs: Any,
) -> TTSEngineBase:
    """
    Get the best available TTS engine.

    Priority: edge-tts (free, always available) > coqui > elevenlabs > error

    Args:
        engine: "coqui", "elevenlabs", "edge-tts", or "auto" (default)
        **kwargs: passed to engine constructor
    """
    if engine == "edge-tts" or engine == "auto":
        try:
            return EdgeTTSEngine(**kwargs)
        except (ImportError, RuntimeError) as e:
            if engine == "edge-tts":
                raise
            logger.debug("Edge TTS unavailable: %s", e)

    if engine == "coqui" or engine == "auto":
        try:
            return CoquiTTSEngine(**kwargs)
        except (ImportError, RuntimeError) as e:
            if engine == "coqui":
                raise
            logger.debug("Coqui TTS unavailable: %s", e)

    if engine == "elevenlabs" or engine == "auto":
        try:
            return ElevenLabsTTSEngine(**kwargs)
        except (ImportError, ValueError, RuntimeError) as e:
            if engine == "elevenlabs":
                raise
            logger.debug("ElevenLabs unavailable: %s", e)

    raise RuntimeError(
        "No TTS engine available. Install one of:\n"
        "  pip install edge-tts\n"
        "  pip install TTS  (Coqui)\n"
        "  pip install elevenlabs"
    )


# ============================= Audio Playback ===============================

def play_audio(
    audio_data: bytes,
    sample_rate: int = 24000,
    sample_width: int = 2,
    channels: int = 1,
) -> None:
    """Play audio through the default output device."""
    try:
        import pyaudio
    except ImportError:
        raise ImportError("pyaudio not installed: pip install pyaudio")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pa.get_format_from_width(sample_width),
        channels=channels,
        rate=sample_rate,
        output=True,
    )

    chunk_size = 1024
    for i in range(0, len(audio_data), chunk_size):
        stream.write(audio_data[i:i + chunk_size])

    stream.stop_stream()
    stream.close()
    pa.terminate()
