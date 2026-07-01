"""Codex and Claude Code adapters for repeated dogsound prompts."""

from __future__ import annotations

import json
import os
import queue
import signal
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

AgentName = Literal["codex", "claude"]
OutputCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class AgentResult:
    agent: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    session_id: str | None = None
    timed_out: bool = False
    idle_timed_out: bool = False

    @property
    def display_reply(self) -> str:
        return extract_display_reply(self.stdout, self.stderr)


@dataclass(frozen=True)
class AgentOptions:
    name: AgentName
    workspace: str | Path
    open_permissions: bool = True
    json_output: bool = True
    model: str | None = None
    reasoning_effort: str | None = None
    timeout_seconds: int | None = 600
    idle_timeout_seconds: int | None = 120


class ResumableAgent:
    def __init__(self, options: AgentOptions) -> None:
        self.options = options
        self.workspace = Path(options.workspace).expanduser().resolve()
        self.turn_count = 0
        self.session_id: str | None = None

    def submit(self, prompt: str, *, on_output: OutputCallback | None = None) -> AgentResult:
        if self.options.name == "codex":
            return self._submit_codex(prompt, on_output=on_output)
        if self.options.name == "claude":
            return self._submit_claude(prompt, on_output=on_output)
        raise ValueError(f"Unsupported agent: {self.options.name}")

    def _submit_codex(self, prompt: str, *, on_output: OutputCallback | None) -> AgentResult:
        _require_executable("codex")
        command = build_codex_command(
            resume=self.turn_count > 0,
            workspace=self.workspace,
            open_permissions=self.options.open_permissions,
            json_output=self.options.json_output,
            model=self.options.model,
            reasoning_effort=self.options.reasoning_effort,
            session_id=self.session_id,
        )
        result = _run_command(
            command,
            cwd=self.workspace,
            stdin=prompt,
            timeout_seconds=self.options.timeout_seconds,
            idle_timeout_seconds=self.options.idle_timeout_seconds,
            on_output=on_output,
        )
        self.turn_count += 1

        session_id = self.session_id or _extract_session_id(result.stdout) or _extract_session_id(result.stderr)
        self.session_id = session_id
        return AgentResult(
            agent="codex",
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=result.elapsed_seconds,
            session_id=session_id,
            timed_out=result.timed_out,
            idle_timed_out=result.idle_timed_out,
        )

    def _submit_claude(self, prompt: str, *, on_output: OutputCallback | None) -> AgentResult:
        _require_executable("claude")
        command = build_claude_command(
            resume=self.turn_count > 0,
            open_permissions=self.options.open_permissions,
            prompt=prompt,
        )
        result = _run_command(
            command,
            cwd=self.workspace,
            timeout_seconds=self.options.timeout_seconds,
            idle_timeout_seconds=self.options.idle_timeout_seconds,
            on_output=on_output,
        )
        self.turn_count += 1
        return AgentResult(
            agent="claude",
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=result.elapsed_seconds,
            session_id=None,
            timed_out=result.timed_out,
            idle_timed_out=result.idle_timed_out,
        )


def build_codex_command(
    *,
    resume: bool,
    workspace: str | Path,
    open_permissions: bool,
    json_output: bool = True,
    model: str | None = None,
    reasoning_effort: str | None = None,
    session_id: str | None = None,
) -> list[str]:
    if not resume:
        command = ["codex", "exec", "--skip-git-repo-check", "-C", str(Path(workspace))]
        if open_permissions:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        if model:
            command.extend(["--model", model])
        if reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
        if json_output:
            command.append("--json")
        command.append("-")
        return command

    command = ["codex", "exec", "resume", "--skip-git-repo-check"]
    if open_permissions:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    if json_output:
        command.append("--json")
    if session_id:
        command.append(session_id)
    else:
        command.append("--last")
    command.append("-")
    return command


def build_claude_command(*, resume: bool, open_permissions: bool, prompt: str) -> list[str]:
    command = ["claude"]
    if resume:
        command.append("-c")
    command.append("-p")
    if open_permissions:
        command.append("--dangerously-skip-permissions")
    command.append(prompt)
    return command


def shell_join(command: list[str]) -> str:
    return " ".join(_shell_quote(part) for part in command)


def extract_display_reply(stdout: str, stderr: str = "") -> str:
    json_texts: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        json_texts.extend(_collect_display_text(payload))

    cleaned_json_texts = _dedupe(_clean_text(text) for text in json_texts if _clean_text(text))
    if cleaned_json_texts:
        return "\n".join(cleaned_json_texts[-4:])

    plain = _plain_output_summary(stdout) or _plain_output_summary(stderr)
    return plain or "(no agent reply captured)"


def format_stream_line(source: str, line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""

    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return _prefix_stream_line(source, stripped)
        formatted = _format_json_event(payload)
        if formatted:
            return formatted
        return _prefix_stream_line(source, stripped)

    return _prefix_stream_line(source, stripped)


@dataclass(frozen=True)
class _CompletedCommand:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool = False
    idle_timed_out: bool = False


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    stdin: str | None = None,
    timeout_seconds: int | None = None,
    idle_timeout_seconds: int | None = None,
    on_output: OutputCallback | None = None,
) -> _CompletedCommand:
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
        start_new_session=True,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

    if process.stdin is not None and stdin is not None:
        process.stdin.write(stdin)
        process.stdin.close()

    readers = [
        threading.Thread(
            target=_read_stream,
            args=("stdout", process.stdout, output_queue),
            daemon=True,
        ),
        threading.Thread(
            target=_read_stream,
            args=("stderr", process.stderr, output_queue),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    idle_timed_out = False
    deadline = None if timeout_seconds is None else start + timeout_seconds
    idle_deadline = None if idle_timeout_seconds is None else start + idle_timeout_seconds
    finished_readers = set()
    while True:
        now = time.monotonic()
        if deadline is not None and now >= deadline and process.poll() is None:
            timed_out = True
            _terminate_process_group(process)
        if idle_deadline is not None and now >= idle_deadline and process.poll() is None:
            idle_timed_out = True
            _terminate_process_group(process)

        try:
            source, line = output_queue.get(timeout=0.05)
        except queue.Empty:
            if process.poll() is not None and len(finished_readers) == len(readers):
                break
            continue

        if line is None:
            finished_readers.add(source)
            if process.poll() is not None and len(finished_readers) == len(readers):
                break
            continue

        if source == "stdout":
            stdout_lines.append(line)
        else:
            stderr_lines.append(line)
        if idle_timeout_seconds is not None:
            idle_deadline = time.monotonic() + idle_timeout_seconds
        if on_output is not None:
            on_output(source, line)

    for reader in readers:
        reader.join(timeout=1)

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)
    if timed_out:
        timeout_note = f"Command timed out after {timeout_seconds} seconds."
        stderr = f"{stderr.rstrip()}\n{timeout_note}\n" if stderr else timeout_note + "\n"
        if on_output is not None:
            on_output("stderr", timeout_note + "\n")
    if idle_timed_out:
        timeout_note = f"Command produced no output for {idle_timeout_seconds} seconds; terminated."
        stderr = f"{stderr.rstrip()}\n{timeout_note}\n" if stderr else timeout_note + "\n"
        if on_output is not None:
            on_output("stderr", timeout_note + "\n")

    elapsed = time.monotonic() - start
    return _CompletedCommand(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        idle_timed_out=idle_timed_out,
    )


def _read_stream(
    source: str,
    stream: Any,
    output_queue: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        if stream is None:
            return
        for line in stream:
            output_queue.put((source, line))
    finally:
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass
        output_queue.put((source, None))


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def _require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name!r} was not found on PATH.")


def _extract_session_id(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        found = _find_key(payload, {"session_id", "sessionId", "conversation_id", "conversationId"})
        if isinstance(found, str) and found:
            return found
    return None


def _collect_display_text(value: Any, *, parent_key: str = "") -> list[str]:
    if isinstance(value, dict):
        collected: list[str] = []
        role = str(value.get("role", "")).lower()
        value_type = str(value.get("type", "")).lower()
        relevant_container = role == "assistant" or any(
            marker in value_type for marker in ("message", "response", "output", "final", "result")
        )

        for key, item in value.items():
            key_lower = key.lower()
            if (
                key_lower in {"text", "message", "answer", "final_response"}
                and isinstance(item, str)
                and (relevant_container or parent_key in {"content", "output", "response", "result", "item"})
            ):
                collected.append(item)
            elif key_lower == "content":
                if isinstance(item, str):
                    collected.append(item)
                else:
                    collected.extend(_collect_display_text(item, parent_key=key_lower))
            elif relevant_container or key_lower in {"msg", "event", "item", "data", "result", "response", "output"}:
                collected.extend(_collect_display_text(item, parent_key=key_lower))
        return collected

    if isinstance(value, list):
        collected = []
        for item in value:
            collected.extend(_collect_display_text(item, parent_key=parent_key))
        return collected

    return []


def _clean_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line.strip())


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _plain_output_summary(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("{"):
            continue
        lines.append(stripped)
    return "\n".join(lines[-12:])


def _format_json_event(payload: dict[str, Any]) -> str:
    event_type = str(payload.get("type", "event"))

    if event_type == "thread.started":
        thread_id = payload.get("thread_id") or payload.get("threadId")
        return f"thread started {thread_id}" if thread_id else "thread started"

    if event_type == "turn.started":
        return "turn started"

    item = payload.get("item")
    if isinstance(item, dict):
        item_type = str(item.get("type", "item"))
        status = str(item.get("status", "") or payload.get("status", ""))

        if item_type == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

        if item_type == "command_execution":
            command = item.get("command")
            output = item.get("aggregated_output")
            prefix = "command"
            if event_type.endswith(".started") or status == "in_progress":
                prefix = "running"
            elif status:
                prefix = status
            if isinstance(command, str) and command:
                text = f"{prefix}: {_clip(command, 96)}"
                if isinstance(output, str) and output.strip() and status in {"completed", "failed"}:
                    text += f" -> {_clip(output.strip().replace(chr(10), ' | '), 96)}"
                return text

        if item_type == "error":
            message = item.get("message")
            return f"error: {message}" if isinstance(message, str) else "error"

        texts = _collect_display_text(item)
        if texts:
            return _clean_text(texts[-1])

    texts = _collect_display_text(payload)
    if texts:
        return _clean_text(texts[-1])

    message = payload.get("message")
    if isinstance(message, str) and message.strip() and event_type not in {"event"}:
        return f"{event_type}: {message.strip()}"

    return ""


def _prefix_stream_line(source: str, line: str) -> str:
    if source == "stderr":
        return f"stderr: {_clip(line, 160)}"
    return _clip(line, 160)


def _clip(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)] + "..."


def _find_key(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                return item
            found = _find_key(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_key(item, keys)
            if found is not None:
                return found
    return None


def _shell_quote(value: str) -> str:
    if value and all(ch.isalnum() or ch in "@%_+=:,./-" for ch in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
