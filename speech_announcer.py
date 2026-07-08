from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
import time


LOG = logging.getLogger(__name__)


class SpeechAnnouncer:
    def __init__(self, cooldown_s: float = 3.5):
        self.cooldown_s = cooldown_s
        self._last_label = ""
        self._last_spoken_at = 0.0
        self._queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="speech-announcer", daemon=True)
        self._thread.start()

    def speak_label(self, label: str) -> None:
        label = label.strip()
        if not label or label.lower() in {"unknown", "initializing...", "stopped", "--"}:
            return
        now = time.monotonic()
        if label == self._last_label and now - self._last_spoken_at < self.cooldown_s:
            return
        self._last_label = label
        self._last_spoken_at = now
        self._replace_pending(label)

    def close(self) -> None:
        self._stop.set()
        self._replace_pending("")
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _replace_pending(self, text: str) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def _run(self) -> None:
        engine = None
        while not self._stop.is_set():
            try:
                text = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not text:
                continue
            if self._speak_with_speech_dispatcher(text):
                continue
            try:
                if engine is None:
                    import pyttsx3

                    engine = pyttsx3.init()
                    engine.setProperty("rate", 165)
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                LOG.debug("Text-to-speech unavailable: %s", exc)

    @staticmethod
    def _speak_with_speech_dispatcher(text: str) -> bool:
        if shutil.which("spd-say") is None:
            return False
        try:
            subprocess.run(
                ["spd-say", "-r", "-10", text],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            )
            return True
        except Exception:
            return False
