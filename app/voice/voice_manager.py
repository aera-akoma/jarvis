from __future__ import annotations

import importlib.util
import os
from typing import Any, Callable


class VoiceManager:
    """Optional one-shot voice interfaces: cloud speech recognition and local TTS."""

    def __init__(self, *, recognizer_factory: Callable[[], Any] | None = None,
                 microphone_factory: Callable[[], Any] | None = None,
                 speech_module: Any | None = None, tts_factory: Callable[[], Any] | None = None) -> None:
        self._stt_enabled = False
        self._tts_enabled = False
        self._recognizer_factory = recognizer_factory
        self._microphone_factory = microphone_factory
        self._speech_module = speech_module
        self._tts_factory = tts_factory

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def speech_to_text_available(self) -> bool:
        injected = self._recognizer_factory is not None and self._microphone_factory is not None and self._speech_module is not None
        return injected or (self._stt_enabled and self._module_available("speech_recognition") and self._module_available("pyaudio"))

    def text_to_speech_available(self) -> bool:
        return self._tts_factory is not None or (self._tts_enabled and self._module_available("pyttsx3"))

    def enable_speech(self) -> None:
        self._stt_enabled = True
        self._tts_enabled = True

    def listen_and_transcribe(self, *, language: str = "en-US", timeout: int = 6,
                              phrase_time_limit: int = 20, ambient_duration: float = 0.4) -> str:
        speech = self._speech_module
        if self._recognizer_factory and self._microphone_factory and self._speech_module:
            recognizer = self._recognizer_factory()
            microphone_factory = self._microphone_factory
            speech = self._speech_module
        else:
            if not self.speech_to_text_available():
                raise RuntimeError("Voice input needs SpeechRecognition and PyAudio. Install the voice extras from requirements.txt.")
            import speech_recognition as speech
            recognizer = speech.Recognizer()
            microphone_factory = speech.Microphone
        try:
            with microphone_factory() as source:
                if ambient_duration > 0:
                    recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            transcript = recognizer.recognize_google(audio, language=language)
        except Exception as exc:
            if speech is not None:
                if isinstance(exc, getattr(speech, "WaitTimeoutError", ())):
                    raise RuntimeError("No speech was detected before the listening timeout.") from exc
                if isinstance(exc, getattr(speech, "UnknownValueError", ())):
                    raise RuntimeError("The speech service could not understand that recording.") from exc
                if isinstance(exc, getattr(speech, "RequestError", ())):
                    raise RuntimeError(f"Speech transcription service error: {exc}") from exc
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Could not record or transcribe audio: {exc}") from exc
        if not transcript or not transcript.strip():
            raise RuntimeError("The speech service returned an empty transcript.")
        return transcript.strip()

    def speak(self, text: str) -> None:
        value = (text or "").strip()
        if not value:
            return
        if len(value) > 4000:
            value = value[:4000]
        if self._tts_factory is not None:
            engine = self._tts_factory()
        else:
            if not self.text_to_speech_available():
                raise RuntimeError("Voice output needs pyttsx3. Install the voice extras from requirements.txt.")
            import pyttsx3
            engine = pyttsx3.init("sapi5" if os.name == "nt" else None)
        engine.say(value)
        engine.runAndWait()
        engine.stop()
