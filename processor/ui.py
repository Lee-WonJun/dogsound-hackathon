"""Small terminal dashboard for live processor sessions."""

from __future__ import annotations

import shutil
import sys
import threading
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class TerminalDashboard:
    workspace: Path
    agent: str
    log_path: Path
    dry_run: bool
    open_permissions: bool
    model: str | None
    reasoning_effort: str | None
    instruction_path: Path | None
    agent_timeout_seconds: int | None
    agent_idle_timeout_seconds: int | None
    start_threshold: float
    stop_threshold: float
    refresh_seconds: float = 0.10
    level: float = 0.0
    recording: bool = False
    recording_ms: int = 0
    silent_tail_ms: int = 0
    silence_ms: int = 0
    utterance_index: int = 0
    tokens: str = ""
    token_count: int = 0
    status: str = "Waiting for sound"
    threshold_note: str = "configured"
    agent_status: str = "idle"
    queued_segments: int = 0
    agent_started_at: float | None = None
    agent_last_output_at: float | None = None
    agent_output: list[str] = field(default_factory=list)
    reply: str = ""
    error: str = ""
    _last_render: float = field(default=0.0, init=False)
    _force_render: bool = field(default=False, init=False)
    _running: bool = field(default=False, init=False)
    _render_event: threading.Event = field(default_factory=threading.Event, init=False)
    _render_thread: threading.Thread | None = field(default=None, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def start(self) -> None:
        self._running = True
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[H")
        sys.stdout.flush()
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()
        self.render(force=True)

    def stop(self) -> None:
        self._running = False
        self._render_event.set()
        if self._render_thread is not None:
            self._render_thread.join(timeout=1)
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()

    def update_calibration(self, *, level: float, elapsed_ms: int, total_ms: int) -> None:
        with self._lock:
            self.level = level
            self.recording = False
            self.status = f"Calibrating noise {elapsed_ms / 1000:.1f}/{total_ms / 1000:.1f}s; stay quiet"
            self.render()

    def update_thresholds(self, *, start_threshold: float, stop_threshold: float, note: str) -> None:
        with self._lock:
            self.start_threshold = start_threshold
            self.stop_threshold = stop_threshold
            self.threshold_note = note
            self.status = f"Ready; thresholds set from {note}"
            self.render(force=True)

    def update_meter(
        self,
        *,
        level: float,
        recording: bool,
        recording_ms: int = 0,
        silent_tail_ms: int = 0,
        silence_ms: int = 0,
    ) -> None:
        with self._lock:
            self.level = level
            self.recording = recording
            self.recording_ms = recording_ms
            self.silent_tail_ms = silent_tail_ms
            self.silence_ms = silence_ms
            if recording:
                if level < self.stop_threshold:
                    self.status = f"Ending: quiet {silent_tail_ms}/{silence_ms} ms"
                else:
                    self.status = "Recording; waiting for level below stop threshold"
            else:
                self.status = (
                    "Starting utterance"
                    if level >= self.start_threshold
                    else "Ready; make input above start threshold"
                )
            self.render()

    def update_utterance(self, *, utterance_index: int, tokens: str) -> None:
        with self._lock:
            self.utterance_index = utterance_index
            self.tokens = tokens
            self.token_count = len(tokens)
            self.status = f"Captured utterance #{utterance_index}"
            self.render(force=True)

    def update_queue_size(self, queued_segments: int) -> None:
        with self._lock:
            self.queued_segments = queued_segments
            self.render()

    def update_status(self, status: str, *, force: bool = False) -> None:
        with self._lock:
            self.status = status
            self.render(force=force)

    def update_agent_status(self, status: str) -> None:
        with self._lock:
            self.agent_status = status
            if status.startswith("running"):
                now = time.monotonic()
                self.agent_started_at = now
                self.agent_last_output_at = now
            self.render(force=True)

    def update_agent_output(self, line: str) -> None:
        cleaned = line.strip()
        if not cleaned:
            return
        with self._lock:
            self.agent_output.append(cleaned)
            self.agent_output = self.agent_output[-80:]
            self.agent_last_output_at = time.monotonic()
            self.render()

    def update_reply(self, reply: str) -> None:
        with self._lock:
            self.reply = reply.strip()
            self.agent_status = "done"
            self.agent_started_at = None
            self.agent_last_output_at = None
            self.status = "Agent finished"
            self.render(force=True)

    def update_error(self, error: str) -> None:
        with self._lock:
            self.error = error.strip()
            self.status = "Error"
            self.agent_started_at = None
            self.agent_last_output_at = None
            self.render(force=True)

    def render(self, *, force: bool = False) -> None:
        if force:
            self._force_render = True
        self._render_event.set()

    def _render_loop(self) -> None:
        while self._running:
            self._render_event.wait(self.refresh_seconds)
            self._render_event.clear()
            force = self._force_render
            self._force_render = False
            now = time.monotonic()
            if not force and now - self._last_render < self.refresh_seconds:
                continue
            self._draw()

    def _draw(self) -> None:
        now = time.monotonic()
        self._last_render = now
        with self._lock:
            rendered = "\n".join(self._lines())
        sys.stdout.write("\x1b[H\x1b[J")
        sys.stdout.write(rendered)
        sys.stdout.flush()

    def _lines(self) -> list[str]:
        width = max(72, min(shutil.get_terminal_size((96, 28)).columns, 120))
        inner = width - 4
        lines = [
            _box_top(width),
            _box_line("Token Input Processor", width),
            _box_sep(width),
            _box_line(f"Workspace: {self.workspace}", width),
            _box_line(
                f"Agent: {self.agent}   Model: {self.model or '(default)'}   Effort: {self.reasoning_effort or '(default)'}",
                width,
            ),
            _box_line(f"Dry run: {self.dry_run}   Open permissions: {self.open_permissions}", width),
            _box_line(f"Instructions: {self.instruction_path or '(dry run; not written)'}", width),
            _box_line(f"Agent timeout: {self.agent_timeout_seconds if self.agent_timeout_seconds is not None else 'off'} seconds", width),
            _box_line(f"Log: {self.log_path}", width),
            _box_sep(width),
            _box_line(f"Status: {self.status}", width),
            _box_line(f"Mic: {self._meter()}  {'REC' if self.recording else 'wait'}", width),
            _box_line(
                f"Thresholds: start {self.start_threshold:.4f} / stop {self.stop_threshold:.4f} ({self.threshold_note})",
                width,
            ),
            _box_line(f"Recording: {self.recording_ms} ms   Quiet tail: {self.silent_tail_ms}/{self.silence_ms or '-'} ms", width),
            _box_line(f"Utterance: #{self.utterance_index or '-'}   Tokens: {self.token_count or '-'}", width),
            _box_line(f"Token preview: {_clip_middle(self.tokens, inner - 15) if self.tokens else '-'}", width),
            _box_sep(width),
            _box_line(f"Agent status: {self._agent_status()}   queued: {self.queued_segments}", width),
        ]

        if self.reply:
            lines.append(_box_line("Agent reply:", width))
            lines.extend(_wrapped_box_lines(self.reply, width, max_lines=8))
        elif self.agent_output:
            lines.append(_box_line("Agent output:", width))
            output_text = "\n".join([*self.agent_output[-7:], self._agent_idle_line()])
            lines.extend(_wrapped_box_lines(output_text, width, max_lines=8, tail=True))
        elif self.error:
            lines.append(_box_line("Error:", width))
            lines.extend(_wrapped_box_lines(self.error, width, max_lines=8))
        else:
            lines.append(_box_line(f"Agent output: {self._agent_idle_line()}", width))

        lines.extend(
            [
                _box_sep(width),
                _box_line("Speak, then pause. p pauses mic, r resumes, q finishes; Ctrl-C interrupts.", width),
                _box_bottom(width),
            ]
        )
        return lines

    def _meter(self) -> str:
        width = 28
        filled = min(width, int(self.level / max(self.start_threshold, 1e-9) * width))
        return f"{self.level:0.4f} [" + "#" * filled + "-" * (width - filled) + "]"

    def _agent_status(self) -> str:
        if self.agent_started_at is None:
            return self.agent_status
        now = time.monotonic()
        elapsed = int(now - self.agent_started_at)
        idle = int(now - (self.agent_last_output_at or self.agent_started_at))
        return f"{self.agent_status} {elapsed}s; last output {idle}s ago"

    def _agent_idle_line(self) -> str:
        if self.agent_started_at is None:
            return "-"
        now = time.monotonic()
        idle = int(now - (self.agent_last_output_at or self.agent_started_at))
        if self.agent_idle_timeout_seconds is None:
            return f"waiting for agent output; idle {idle}s; idle timeout off"
        remaining = max(0, int(self.agent_idle_timeout_seconds - idle))
        return f"waiting for agent output; idle {idle}s; idle timeout in {remaining}s"


def _box_top(width: int) -> str:
    return "+" + "-" * (width - 2) + "+"


def _box_sep(width: int) -> str:
    return "|" + "-" * (width - 2) + "|"


def _box_bottom(width: int) -> str:
    return "+" + "-" * (width - 2) + "+"


def _box_line(text: str, width: int) -> str:
    content_width = width - 4
    clipped = text[:content_width]
    return "| " + clipped.ljust(content_width) + " |"


def _wrapped_box_lines(text: str, width: int, *, max_lines: int, tail: bool = False) -> list[str]:
    content_width = width - 4
    raw_lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        raw_lines.extend(textwrap.wrap(paragraph, width=content_width) or [""])

    if tail:
        shown = raw_lines[-max_lines:]
        if len(raw_lines) > max_lines and shown:
            shown[0] = "... " + shown[0]
    else:
        shown = raw_lines[:max_lines]
        if len(raw_lines) > max_lines and shown:
            shown[-1] = _clip_end(shown[-1], content_width - 4) + " ..."
    return [_box_line(line, width) for line in shown]


def _clip_middle(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    if max_length <= 5:
        return text[:max_length]
    left = (max_length - 3) // 2
    right = max_length - 3 - left
    return text[:left] + "..." + text[-right:]


def _clip_end(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length)]


def render_static_dashboard(lines: Iterable[str]) -> str:
    return "\n".join(lines)
