"""
Rally Agent — Wake Word Detection
===================================
Multi-backend wake word detection with graceful fallbacks:
  1. Porcupine (Picovoice — commercial, high accuracy)
  2. OpenWakeWord (open source, local)
  3. Simple energy-based fallback

Features:
  - Configurable wake words
  - Always-listening mode with power optimization
  - Callback-based architecture
"""

from __future__ import annotations

import abc
import logging
import os
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("rally.voice.wakeword")


# ============================= Data Types ==================================

@dataclass
class WakeWordEvent:
    """Event fired when a wake word is detected."""
    keyword: str
    confidence: float
    timestamp: float
    engine: str
    audio_context: Optional[bytes] = None  # Audio snippet around detection


@dataclass
class WakeWordConfig:
    """Configuration for wake word detection."""
    sensitivity: float = 0.5         # 0.0–1.0
    keywords: List[str] = field(default_factory=lambda: ["hey rally"])
    sample_rate: int = 16000
    frame_length: int = 512
    buffer_seconds: float = 0.5      # Audio context to capture around detection
    power_save: bool = False          # Reduce CPU when idle
    power_save_interval: float = 0.1 # Seconds between checks in power-save mode


# ============================= Base Detector ================================

class WakeWordDetectorBase(abc.ABC):
    """Abstract base for wake word detectors."""

    def __init__(self, config: Optional[WakeWordConfig] = None) -> None:
        self._config = config or WakeWordConfig()
        self._callbacks: List[Callable[[WakeWordEvent], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._audio_buffer: deque = deque(
            maxlen=int(self._config.sample_rate * self._config.buffer_seconds / self._config.frame_length)
        )

    def on_wake_word(self, callback: Callable[[WakeWordEvent], None]) -> None:
        """Register a callback for wake word detection."""
        self._callbacks.append(callback)

    def _fire_event(self, event: WakeWordEvent) -> None:
        """Fire wake word event to all registered callbacks."""
        logger.info(
            "Wake word detected: '%s' (confidence=%.2f, engine=%s)",
            event.keyword, event.confidence, event.engine,
        )
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error("Wake word callback error: %s", e)

    @abc.abstractmethod
    def _detect(self, audio_frame: bytes) -> Optional[WakeWordEvent]:
        """Process a single audio frame and return event if detected."""
        ...

    @abc.abstractmethod
    def _setup(self) -> None:
        """Initialize the detector."""
        ...

    @abc.abstractmethod
    def _teardown(self) -> None:
        """Clean up resources."""
        ...

    def start(self) -> None:
        """Start listening for wake words in a background thread."""
        if self._running:
            return

        self._setup()
        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="rally-wakeword",
        )
        self._thread.start()
        logger.info("Wake word detection started (engine=%s)", self.name)

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._teardown()
        logger.info("Wake word detection stopped")

    def _listen_loop(self) -> None:
        """Main listening loop — reads audio and checks for wake words."""
        try:
            import pyaudio
        except ImportError:
            logger.error("pyaudio not installed — cannot listen for wake words")
            self._running = False
            return

        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self._config.sample_rate,
                input=True,
                frames_per_buffer=self._config.frame_length,
            )

            frame_bytes = self._config.frame_length * 2  # 16-bit = 2 bytes/sample

            while self._running and not self._stop_event.is_set():
                try:
                    data = stream.read(self._config.frame_length, exception_on_overflow=False)
                except Exception as e:
                    logger.warning("Audio read error: %s", e)
                    continue

                self._audio_buffer.append(data)

                event = self._detect(data)
                if event is not None:
                    # Attach audio context
                    context_frames = list(self._audio_buffer)
                    event.audio_context = b"".join(context_frames)
                    self._fire_event(event)

                # Power save: sleep between reads
                if self._config.power_save:
                    time.sleep(self._config.power_save_interval)

        except Exception as e:
            logger.error("Wake word listen loop error: %s", e)
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()

    def process_audio_frame(self, frame: bytes) -> Optional[WakeWordEvent]:
        """
        Process a single audio frame externally.
        Use this if you already have an audio pipeline.
        """
        self._audio_buffer.append(frame)
        event = self._detect(frame)
        if event:
            event.audio_context = b"".join(list(self._audio_buffer))
        return event

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @property
    def is_running(self) -> bool:
        return self._running


# ============================= Porcupine ====================================

class PorcupineDetector(WakeWordDetectorBase):
    """Picovoice Porcupine wake word engine."""

    def __init__(
        self,
        config: Optional[WakeWordConfig] = None,
        access_key: Optional[str] = None,
        keyword_paths: Optional[List[str]] = None,
    ) -> None:
        super().__init__(config)
        self._access_key = access_key or os.environ.get("PICOVOICE_ACCESS_KEY")
        if not self._access_key:
            raise ValueError(
                "Porcupine access key required. Set PICOVOICE_ACCESS_KEY or pass access_key."
            )
        self._keyword_paths = keyword_paths
        self._porcupine: Any = None

    @property
    def name(self) -> str:
        return "porcupine"

    def _setup(self) -> None:
        try:
            import pvporcupine
        except ImportError:
            raise ImportError("pvporcupine not installed: pip install pvporcupine")

        kwargs: Dict[str, Any] = {
            "access_key": self._access_key,
            "sensitivities": [self._config.sensitivity] * max(1, len(self._keyword_paths or self._config.keywords)),
        }

        if self._keyword_paths:
            kwargs["keyword_paths"] = self._keyword_paths
        else:
            # Use built-in keywords
            builtin = []
            for kw in self._config.keywords:
                kw_lower = kw.lower().strip()
                if kw_lower in ("porcupine", "bumblebee", "alexa", "hey google", "hey siri",
                                "jarvis", "ok google", "computer", "picovoice"):
                    builtin.append(kw_lower)
                else:
                    logger.warning(
                        "Keyword '%s' is not a Porcupine built-in. "
                        "Use keyword_paths for custom wake words.", kw
                    )
            if builtin:
                kwargs["keywords"] = builtin
            else:
                # Default to "picovoice"
                kwargs["keywords"] = ["picovoice"]

        self._porcupine = pvporcupine.create(**kwargs)
        logger.info(
            "Porcupine initialized (keywords=%s, sensitivity=%.2f)",
            self._config.keywords, self._config.sensitivity,
        )

    def _teardown(self) -> None:
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None

    def _detect(self, audio_frame: bytes) -> Optional[WakeWordEvent]:
        if self._porcupine is None:
            return None

        # Porcupine expects 16-bit PCM
        pcm = struct.unpack_from("h" * self._porcupine.frame_length, audio_frame)
        keyword_index = self._porcupine.process(pcm)

        if keyword_index >= 0:
            keyword = self._config.keywords[keyword_index] if keyword_index < len(self._config.keywords) else "unknown"
            return WakeWordEvent(
                keyword=keyword,
                confidence=1.0,  # Porcupine doesn't return confidence
                timestamp=time.time(),
                engine=self.name,
            )
        return None


# ============================= OpenWakeWord =================================

class OpenWakeWordDetector(WakeWordDetectorBase):
    """OpenWakeWord — open source wake word detection."""

    def __init__(
        self,
        config: Optional[WakeWordConfig] = None,
        model_paths: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(config)
        self._model_paths = model_paths
        self._model: Any = None
        self._keyword_map: Dict[str, str] = {}  # model_name -> keyword

    @property
    def name(self) -> str:
        return "openwakeword"

    def _setup(self) -> None:
        try:
            from openwakeword.model import Model as OWWModel
        except ImportError:
            raise ImportError(
                "openwakeword not installed: pip install openwakeword\n"
                "Also run: python -m openwakeword.utils download_models"
            )

        if self._model_paths:
            self._model = OWWModel(wakeword_models=list(self._model_paths.values()))
            for name, path in self._model_paths.items():
                self._keyword_map[Path(path).stem.lower()] = name
        else:
            # Use default models
            self._model = OWWModel()
            # Map known model names to keywords
            for kw in self._config.keywords:
                self._keyword_map[kw.lower().replace(" ", "_")] = kw

        logger.info(
            "OpenWakeWord initialized (keywords=%s, sensitivity=%.2f)",
            self._config.keywords, self._config.sensitivity,
        )

    def _teardown(self) -> None:
        self._model = None

    def _detect(self, audio_frame: bytes) -> Optional[WakeWordEvent]:
        if self._model is None:
            return None

        # Convert bytes to numpy array
        try:
            import numpy as np
            audio_np = np.frombuffer(audio_frame, dtype=np.int16)
        except ImportError:
            return None

        prediction = self._model.predict(audio_np)

        best_keyword = None
        best_score = 0.0

        for model_name, score in prediction.items():
            if score > self._config.sensitivity and score > best_score:
                # Check if this model matches a configured keyword
                keyword = self._keyword_map.get(model_name.lower(), model_name)
                for configured_kw in self._config.keywords:
                    if configured_kw.lower() in keyword.lower() or keyword.lower() in configured_kw.lower():
                        best_keyword = configured_kw
                        best_score = score
                        break
                if best_keyword is None:
                    best_keyword = model_name
                    best_score = score

        if best_keyword and best_score > self._config.sensitivity:
            return WakeWordEvent(
                keyword=best_keyword,
                confidence=best_score,
                timestamp=time.time(),
                engine=self.name,
            )
        return None


# ============================= Energy Fallback ==============================

class EnergyWakeWordDetector(WakeWordDetectorBase):
    """
    Simple energy-based "wake word" detector.
    Not a real wake word engine — just detects when someone starts speaking
    after a period of silence. Useful as a fallback.
    """

    def __init__(
        self,
        config: Optional[WakeWordConfig] = None,
        energy_threshold: float = 500.0,
        min_speech_frames: int = 10,
    ) -> None:
        super().__init__(config)
        self._energy_threshold = energy_threshold
        self._min_speech_frames = min_speech_frames
        self._consecutive_speech = 0
        self._was_speaking = False

    @property
    def name(self) -> str:
        return "energy"

    def _setup(self) -> None:
        self._consecutive_speech = 0
        self._was_speaking = False

    def _teardown(self) -> None:
        pass

    def _detect(self, audio_frame: bytes) -> Optional[WakeWordEvent]:
        try:
            import audioop
            energy = audioop.rms(audio_frame, 2)
        except Exception:
            return None

        is_speech = energy > self._energy_threshold

        if is_speech:
            self._consecutive_speech += 1
        else:
            if self._consecutive_speech >= self._min_speech_frames and not self._was_speaking:
                # Speech started after silence
                self._was_speaking = True
                self._consecutive_speech = 0
                return WakeWordEvent(
                    keyword="<speech_detected>",
                    confidence=min(1.0, energy / (self._energy_threshold * 3)),
                    timestamp=time.time(),
                    engine=self.name,
                )
            self._consecutive_speech = 0
            self._was_speaking = False

        return None


# ============================= Detector Factory ==============================

def get_wake_word_detector(
    engine: str = "auto",
    config: Optional[WakeWordConfig] = None,
    **kwargs: Any,
) -> WakeWordDetectorBase:
    """
    Get the best available wake word detector.

    Priority: porcupine > openwakeword > energy (fallback)

    Args:
        engine: "porcupine", "openwakeword", "energy", or "auto"
        config: WakeWordConfig
        **kwargs: passed to detector constructor
    """
    config = config or WakeWordConfig()

    if engine == "porcupine" or engine == "auto":
        try:
            return PorcupineDetector(config=config, **kwargs)
        except (ImportError, ValueError) as e:
            if engine == "porcupine":
                raise
            logger.debug("Porcupine unavailable: %s", e)

    if engine == "openwakeword" or engine == "auto":
        try:
            return OpenWakeWordDetector(config=config, **kwargs)
        except (ImportError, RuntimeError) as e:
            if engine == "openwakeword":
                raise
            logger.debug("OpenWakeWord unavailable: %s", e)

    # Energy fallback always works
    logger.info("Using energy-based wake detection (fallback)")
    return EnergyWakeWordDetector(config=config, **kwargs)
