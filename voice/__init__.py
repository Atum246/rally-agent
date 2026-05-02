"""
Rally Agent — Voice Module
============================
Speech-to-text, text-to-speech, and wake word detection with
graceful fallbacks for optional dependencies.
"""

from __future__ import annotations

from typing import Optional

__all__ = ["STTEngine", "TTSEngine", "WakeWordDetector"]


def STTEngine(*args, **kwargs):  # noqa: N802
    """Factory: returns the best available STT engine."""
    from .stt import get_stt_engine
    return get_stt_engine(*args, **kwargs)


def TTSEngine(*args, **kwargs):  # noqa: N802
    """Factory: returns the best available TTS engine."""
    from .tts import get_tts_engine
    return get_tts_engine(*args, **kwargs)


def WakeWordDetector(*args, **kwargs):  # noqa: N802
    """Factory: returns the best available wake word detector."""
    from .wakeword import get_wake_word_detector
    return get_wake_word_detector(*args, **kwargs)
