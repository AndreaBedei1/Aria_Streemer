from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time

from label_translations import translate_label_it


LOG = logging.getLogger(__name__)


class SpeechAnnouncer:
    def __init__(self, cooldown_s: float = 3.5):
        self.cooldown_s = cooldown_s
        self.audio_sink = os.getenv("ARIA_TTS_SINK", "").strip()
        self.sink_keywords = _split_keywords(os.getenv("ARIA_TTS_SINK_KEYWORDS", "aria,glasses,andrea"))
        self.output_mode = os.getenv("ARIA_TTS_OUTPUT", "both").strip().lower()
        if self.output_mode not in {"both", "default", "glasses"}:
            self.output_mode = "both"
        self._auto_sink = ""
        self._auto_sink_checked_at = 0.0
        self._last_label = ""
        self._last_spoken_at = 0.0
        self._queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="speech-announcer", daemon=True)
        self._thread.start()

    def speak_label(self, label: str) -> None:
        label = label.strip()
        if not label or label.lower() in {"unknown", "initializing...", "stopped", "--", "no gesture"}:
            return
        now = time.monotonic()
        if label == self._last_label and now - self._last_spoken_at < self.cooldown_s:
            return
        self._last_label = label
        self._last_spoken_at = now
        self._replace_pending(translate_label_it(label))

    def close(self) -> None:
        self._stop.set()
        self._replace_pending("")
        self.cancel()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def cancel(self) -> None:
        self._replace_pending("")
        self._cancel_speech_dispatcher()

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
            audio_sink = self._resolve_audio_sink()
            spoken = False
            if self.output_mode in {"both", "default"}:
                default_sink = self._find_default_pipewire_sink()
                if default_sink:
                    self._move_speech_dispatcher_streams(default_sink)
                spoken = self._speak_with_speech_dispatcher(text) or spoken
            if self.output_mode in {"both", "glasses"}:
                if audio_sink:
                    spoken = self._speak_with_speech_dispatcher(text, audio_sink, move_stream=True) or spoken
                elif self.output_mode == "glasses":
                    LOG.info("TTS skipped because glasses audio sink is not connected")
            if spoken:
                continue
            try:
                if self.output_mode == "glasses" and not audio_sink:
                    continue
                if engine is None:
                    if audio_sink and self.output_mode == "glasses":
                        os.environ["PULSE_SINK"] = audio_sink
                    import pyttsx3

                    engine = pyttsx3.init()
                    engine.setProperty("rate", 165)
                    self._select_italian_voice(engine)
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                LOG.debug("Text-to-speech unavailable: %s", exc)

    def _resolve_audio_sink(self) -> str:
        if self.audio_sink:
            return self.audio_sink
        if shutil.which("wpctl") is None:
            return ""
        now = time.monotonic()
        if now - self._auto_sink_checked_at < 2.0:
            return self._auto_sink
        self._auto_sink_checked_at = now
        self._auto_sink = self._find_pipewire_sink(self.sink_keywords)
        return self._auto_sink

    @staticmethod
    def _speak_with_speech_dispatcher(text: str, audio_sink: str = "", move_stream: bool = False) -> bool:
        if shutil.which("spd-say") is None:
            return False
        try:
            env = None
            if audio_sink:
                env = os.environ.copy()
                env["PULSE_SINK"] = audio_sink
            result = subprocess.run(
                ["spd-say", "-l", "it", "-r", "-10", text],
                check=False,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            )
            if result.returncode == 0 and audio_sink and move_stream:
                SpeechAnnouncer._move_speech_dispatcher_streams(audio_sink)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _cancel_speech_dispatcher() -> None:
        if shutil.which("spd-say") is None:
            return
        try:
            subprocess.run(
                ["spd-say", "-C"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
        except Exception:
            pass

    @staticmethod
    def _select_italian_voice(engine) -> None:
        try:
            voices = engine.getProperty("voices") or []
            for voice in voices:
                fields = [str(getattr(voice, "id", "")), str(getattr(voice, "name", ""))]
                languages = getattr(voice, "languages", []) or []
                fields.extend(str(item) for item in languages)
                searchable = " ".join(fields).lower()
                markers = ("it_it", "it-it", "italian", "italiano", "italia")
                if any(marker in searchable for marker in markers):
                    engine.setProperty("voice", voice.id)
                    return
        except Exception as exc:
            LOG.debug("Could not select Italian TTS voice: %s", exc)

    @staticmethod
    def _move_speech_dispatcher_streams(audio_sink: str) -> None:
        if shutil.which("wpctl") is None:
            return
        try:
            status = subprocess.run(
                ["wpctl", "status"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            ).stdout
            for line in status.splitlines():
                if "speech-dispatcher" not in line:
                    continue
                match = re.search(r"^\s*(\d+)\.", line)
                if not match:
                    continue
                subprocess.run(
                    ["wpctl", "move-node", match.group(1), audio_sink],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
        except Exception as exc:
            LOG.debug("Could not move TTS stream to %s: %s", audio_sink, exc)

    @staticmethod
    def _find_pipewire_sink(keywords: list[str]) -> str:
        try:
            status = subprocess.run(
                ["wpctl", "status"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            ).stdout
            for sink_id, description in _parse_wpctl_sinks(status):
                searchable = description.lower()
                inspect = subprocess.run(
                    ["wpctl", "inspect", sink_id],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1.0,
                ).stdout.lower()
                searchable = f"{searchable}\n{inspect}"
                if any(keyword in searchable for keyword in keywords):
                    return sink_id
        except Exception as exc:
            LOG.debug("Could not discover PipeWire sinks: %s", exc)
        return ""

    @staticmethod
    def _find_default_pipewire_sink() -> str:
        if shutil.which("wpctl") is None:
            return ""
        try:
            status = subprocess.run(
                ["wpctl", "status"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            ).stdout
            return _parse_wpctl_default_sink(status)
        except Exception as exc:
            LOG.debug("Could not discover default PipeWire sink: %s", exc)
        return ""


def _split_keywords(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _parse_wpctl_sinks(status: str) -> list[tuple[str, str]]:
    sinks: list[tuple[str, str]] = []
    in_sinks = False
    for line in status.splitlines():
        if "Sinks:" in line:
            in_sinks = True
            continue
        if in_sinks and "Sink endpoints:" in line:
            break
        if not in_sinks:
            continue
        match = re.search(r"\*?\s*(\d+)\.\s+(.+?)(?:\s+\[|$)", line)
        if match:
            sinks.append((match.group(1), match.group(2).strip()))
    return sinks


def _parse_wpctl_default_sink(status: str) -> str:
    in_sinks = False
    for line in status.splitlines():
        if "Sinks:" in line:
            in_sinks = True
            continue
        if in_sinks and "Sink endpoints:" in line:
            break
        if not in_sinks or "*" not in line:
            continue
        match = re.search(r"\*\s*(\d+)\.", line)
        if match:
            return match.group(1)
    return ""
