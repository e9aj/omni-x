from pathlib import Path
import wave

import pytest

from omnix.voice import VoiceService, VoiceUnavailable


def test_voice_capability_detection_is_local_first():
    service = VoiceService()
    capabilities = service.capabilities()
    assert capabilities["remote_upload"] is False
    assert capabilities["wake_word"] is False
    assert set(capabilities) == {"local_stt", "local_tts", "audio_devices", "wake_word", "remote_upload"}


def test_voice_requires_permission_before_transcription(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"not-a-real-audio-file")
    service = VoiceService(permission=lambda action: False)
    with pytest.raises(PermissionError):
        service.transcribe(source)


def test_voice_reports_missing_local_engine_without_upload(tmp_path: Path, monkeypatch):
    source = tmp_path / "sample.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x00\x00" * 160)
    monkeypatch.setattr("omnix.voice.importlib.util.find_spec", lambda name: None)
    with pytest.raises(VoiceUnavailable, match="not installed"):
        VoiceService().transcribe(source)


def test_voice_rejects_non_wav_before_optional_engine_lookup(tmp_path: Path):
    source = tmp_path / "sample.mp3"
    source.write_bytes(b"audio")
    with pytest.raises(ValueError, match="WAV"):
        VoiceService().transcribe(source)
