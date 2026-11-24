"""Local-first voice capability and execution boundary.

Optional engines are detected, never installed implicitly, and receive audio
only after the caller's microphone/filesystem permission callback approves it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable


class VoiceUnavailable(RuntimeError):
    pass


class VoiceService:
    def __init__(self, *, permission: Callable[[str], bool] | None = None,
                 audit: Callable[[str, str], None] | None = None):
        self.permission, self.audit = permission, audit

    def _allow(self, action: str) -> None:
        if self.permission and not self.permission(action):
            self._record("denied", action)
            raise PermissionError("voice permission denied")

    def _record(self, event: str, detail: str = "") -> None:
        if self.audit:
            self.audit(event, detail[:200])

    def capabilities(self) -> dict[str, Any]:
        return {"local_stt": importlib.util.find_spec("faster_whisper") is not None,
                "local_tts": importlib.util.find_spec("pyttsx3") is not None,
                "audio_devices": importlib.util.find_spec("sounddevice") is not None,
                "wake_word": False, "remote_upload": False}

    def devices(self) -> list[dict[str, Any]]:
        self._allow("microphone.devices")
        if importlib.util.find_spec("sounddevice") is None:
            raise VoiceUnavailable("local audio device support is not installed")
        import sounddevice  # type: ignore[import-not-found]
        return [{"name": str(item.get("name", "")), "index": item.get("index"), "max_input_channels": item.get("max_input_channels", 0)}
                for item in sounddevice.query_devices() if item.get("max_input_channels", 0) > 0]

    def transcribe(self, audio_path: Path, *, model: str = "base") -> str:
        self._allow("microphone.transcribe")
        audio_path = audio_path.expanduser().resolve()
        if not audio_path.is_file() or audio_path.stat().st_size > 50_000_000:
            raise ValueError("audio file is missing or exceeds the 50 MB limit")
        if importlib.util.find_spec("faster_whisper") is None:
            raise VoiceUnavailable("faster-whisper is not installed; no audio was uploaded")
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        engine = WhisperModel(model, device="cpu", compute_type="int8")
        segments, _ = engine.transcribe(str(audio_path), vad_filter=True)
        result = " ".join(segment.text.strip() for segment in segments).strip()
        self._record("transcribed", "local")
        return result

    def speak(self, text: str, *, output_path: Path | None = None) -> str | None:
        self._allow("audio.output")
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            raise ValueError("speech text is invalid")
        if importlib.util.find_spec("pyttsx3") is None:
            raise VoiceUnavailable("pyttsx3 is not installed; no audio was generated")
        import pyttsx3  # type: ignore[import-not-found]
        engine = pyttsx3.init()
        if output_path is not None:
            output_path = output_path.expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            engine.save_to_file(text, str(output_path))
        else:
            engine.say(text)
        engine.runAndWait()
        self._record("spoken", "local")
        return str(output_path) if output_path else None
