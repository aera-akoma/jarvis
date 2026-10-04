from __future__ import annotations


class VoiceManager:
    def __init__(self) -> None:
        self._stt_enabled = False
        self._tts_enabled = False

    def speech_to_text_available(self) -> bool:
        return self._stt_enabled

    def text_to_speech_available(self) -> bool:
        return self._tts_enabled

    def enable_speech(self) -> None:
        self._stt_enabled = True
        self._tts_enabled = True
