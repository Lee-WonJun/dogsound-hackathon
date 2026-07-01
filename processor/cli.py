"""Command line interface for dogsound processor."""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import threading
import time
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterator

try:
    import select
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows-native fallback
    select = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

from .agents import AgentOptions, ResumableAgent, format_stream_line, shell_join
from .audio import iter_microphone_frames
from .config import load_config
from .doctor import format_doctor_checks, run_doctor_checks
from .prompt import PromptInput, render_agent_instructions, render_prompt
from .segmenter import AudioSegmenter
from .tokenizer import summarize_tokens, tokenize_audio_file, tokenize_samples
from .ui import TerminalDashboard


@dataclass(frozen=True)
class _SegmentJob:
    samples: list[float]
    utterance_index: int


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m processor")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="check local dependencies and agent CLIs")
    doctor.set_defaults(handler=handle_doctor)

    calibrate = subparsers.add_parser("calibrate", help="show live microphone levels and suggest thresholds")
    calibrate.add_argument("--sample-rate", type=int, default=16000)
    calibrate.add_argument("--frame-ms", type=int, default=40)
    calibrate.add_argument("--duration", type=float, default=8.0)
    calibrate.add_argument("--device", default=None)
    calibrate.set_defaults(handler=handle_calibrate)

    tokenize = subparsers.add_parser("tokenize", help="tokenize an audio file")
    tokenize.add_argument("audio_path")
    tokenize.add_argument("--sample-rate", type=int, default=16000)
    tokenize.add_argument("--frame-ms", type=int, default=40)
    tokenize.add_argument("--hop-ms", type=int, default=None)
    tokenize.add_argument("--length", type=int, default=None)
    tokenize.set_defaults(handler=handle_tokenize)

    prompt = subparsers.add_parser("prompt", help="render the input text sent to the agent")
    prompt.add_argument("tokens")
    prompt.add_argument("--context", default="")
    prompt.add_argument("--workspace", default=".")
    prompt.add_argument("--utterance-index", type=int, default=1)
    prompt.set_defaults(handler=handle_prompt)

    listen = subparsers.add_parser(
        "listen",
        aliases=["record"],
        help="listen to the microphone and submit utterances to an agent",
    )
    listen.add_argument("--config", default=None)
    listen.add_argument("--agent", choices=["codex", "claude"], default=None)
    listen.add_argument("--model", default=None, help="model name passed to Codex")
    listen.add_argument("--reasoning-effort", default=None, help="Codex reasoning effort, e.g. low, medium, high, xhigh")
    listen.add_argument("--workspace", default=None)
    listen.add_argument("--context", default=None)
    listen.add_argument("--sample-rate", type=int, default=None)
    listen.add_argument("--frame-ms", type=int, default=None)
    listen.add_argument("--silence-ms", type=int, default=None)
    listen.add_argument("--min-utterance-ms", type=int, default=None)
    listen.add_argument("--calibration-ms", type=int, default=None, help="quiet calibration duration for automatic thresholds")
    listen.add_argument("--no-auto-threshold", action="store_true", help="use configured thresholds without live noise calibration")
    listen.add_argument("--start-threshold", type=float, default=None)
    listen.add_argument("--stop-threshold", type=float, default=None)
    listen.add_argument("--device", default=None)
    listen.add_argument("--log", default=None)
    listen.add_argument("--dry-run", action="store_true")
    listen.add_argument("--no-open-permissions", action="store_true")
    listen.add_argument("--agent-timeout-seconds", type=int, default=None)
    listen.add_argument(
        "--agent-idle-timeout-seconds",
        type=int,
        default=None,
        help="terminate the agent if it produces no stdout/stderr for this many seconds; 0 disables",
    )
    listen.add_argument("--max-utterances", type=int, default=None)
    listen.add_argument("--meter", action="store_true", help="show live microphone level while listening")
    listen.add_argument("--ui", action="store_true", help="show a terminal dashboard with level, status, and replies")
    listen.set_defaults(handler=handle_listen)

    return parser


def handle_doctor(_args: argparse.Namespace) -> int:
    print(format_doctor_checks(run_doctor_checks()))
    return 0


def handle_calibrate(args: argparse.Namespace) -> int:
    print("opening microphone")
    print(f"device: {args.device or '(auto)'}")
    print(f"duration: {args.duration:.1f}s")
    print("make the exact sound you want to use now")
    sys.stdout.flush()

    levels: list[float] = []
    started = time.monotonic()
    last_print = 0.0
    try:
        for frame in iter_microphone_frames(
            sample_rate=args.sample_rate,
            frame_ms=args.frame_ms,
            device=args.device,
        ):
            level = _frame_rms(frame)
            levels.append(level)
            now = time.monotonic()
            if now - last_print >= 0.10:
                last_print = now
                print(f"\rlevel {level:0.5f} {_level_bar(level)}", end="", flush=True)
            if now - started >= args.duration:
                break
    except Exception as exc:
        print(f"\ncalibrate failed: {exc}", file=sys.stderr)
        return 1

    print()
    if not levels:
        print("no microphone frames were captured", file=sys.stderr)
        return 1

    sorted_levels = sorted(levels)
    max_level = max(levels)
    p50 = _percentile(sorted_levels, 0.50)
    p90 = _percentile(sorted_levels, 0.90)
    p95 = _percentile(sorted_levels, 0.95)
    noise_floor = _percentile(sorted_levels, 0.20)
    suggested_start = max(noise_floor * 3.0, p90 * 0.55, 0.001)
    suggested_stop = max(noise_floor * 1.8, suggested_start * 0.55, 0.0005)

    print(f"frames: {len(levels)}")
    print(f"level min/p50/p90/p95/max: {sorted_levels[0]:0.5f} / {p50:0.5f} / {p90:0.5f} / {p95:0.5f} / {max_level:0.5f}")
    print(f"suggested: --start-threshold {suggested_start:0.5f} --stop-threshold {suggested_stop:0.5f}")
    if max_level < 0.001:
        print("warning: input is almost silent. Check Windows microphone permission/input device.")
    elif max_level < 0.008:
        print("warning: input is low. Use the suggested thresholds or move closer to the microphone.")
    return 0


def handle_tokenize(args: argparse.Namespace) -> int:
    try:
        tokens = tokenize_audio_file(
            args.audio_path,
            sample_rate=args.sample_rate,
            frame_ms=args.frame_ms,
            hop_ms=args.hop_ms,
            token_length=args.length,
        )
    except Exception as exc:
        print(f"tokenize failed: {exc}", file=sys.stderr)
        return 1

    print(tokens)
    return 0


def handle_prompt(args: argparse.Namespace) -> int:
    try:
        stats = summarize_tokens(args.tokens)
    except Exception as exc:
        print(f"prompt failed: {exc}", file=sys.stderr)
        return 1

    print(
        render_prompt(
            PromptInput(
                tokens=args.tokens,
                stats=stats,
                utterance_index=args.utterance_index,
                workspace=args.workspace,
                context=args.context,
            )
        )
    )
    return 0


def handle_listen(args: argparse.Namespace) -> int:
    options = _resolve_listen_options(args)
    workspace = Path(options["workspace"]).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if options["log"] is None:
        log_path = _default_log_path(workspace)
    else:
        log_path = Path(options["log"]).expanduser()
        if not log_path.is_absolute():
            log_path = workspace / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    dry_run = bool(options["dry_run"])
    open_permissions = bool(options["open_permissions"])
    instruction_path = None
    if not dry_run:
        instruction_path = _ensure_workspace_instructions(
            workspace=workspace,
            agent_name=options["agent"],
            context=options["context"],
        )
    agent = None
    if not dry_run:
        agent = ResumableAgent(
            AgentOptions(
                name=options["agent"],
                workspace=workspace,
                open_permissions=open_permissions,
                model=options["model"],
                reasoning_effort=options["reasoning_effort"],
                timeout_seconds=options["agent_timeout_seconds"],
                idle_timeout_seconds=options["agent_idle_timeout_seconds"],
            )
        )

    dashboard = None
    if options["ui"]:
        dashboard = TerminalDashboard(
            workspace=workspace,
            agent=options["agent"],
            log_path=log_path,
            dry_run=dry_run,
            open_permissions=open_permissions,
            model=options["model"],
            reasoning_effort=options["reasoning_effort"],
            instruction_path=instruction_path,
            agent_timeout_seconds=options["agent_timeout_seconds"],
            agent_idle_timeout_seconds=options["agent_idle_timeout_seconds"],
            start_threshold=options["start_threshold"],
            stop_threshold=options["stop_threshold"],
        )
        dashboard.start()
    else:
        _print_listen_header(
            options,
            workspace=workspace,
            log_path=log_path,
            dry_run=dry_run,
            open_permissions=open_permissions,
            instruction_path=instruction_path,
        )

    segment_queue: queue.Queue[_SegmentJob | None] = queue.Queue()
    worker = threading.Thread(
        target=_segment_worker,
        kwargs={
            "segment_queue": segment_queue,
            "options": options,
            "workspace": workspace,
            "agent": agent,
            "log_path": log_path,
            "dry_run": dry_run,
            "dashboard": dashboard,
        },
        daemon=True,
    )
    worker.start()

    utterance_index = 0
    last_meter_update = 0.0
    segmenter: AudioSegmenter | None = None
    frame_iter: Iterator[list[float]] | None = None
    interrupted = False
    max_utterances_reached = False
    finish_requested = False
    try:
        with _ListenKeyWatcher(enabled=bool(options["ui"])) as keys:
            frame_iter = iter_microphone_frames(
                sample_rate=options["sample_rate"],
                frame_ms=options["frame_ms"],
                device=options["device"],
            )
            _maybe_auto_calibrate_thresholds(frame_iter, options=options, dashboard=dashboard)

            segmenter = AudioSegmenter(
                sample_rate=options["sample_rate"],
                frame_ms=options["frame_ms"],
                silence_ms=options["silence_ms"],
                min_utterance_ms=options["min_utterance_ms"],
                start_threshold=options["start_threshold"],
                stop_threshold=options["stop_threshold"],
            )

            while True:
                action = keys.pop_action()
                if action == "finish":
                    finish_requested = True
                    if dashboard is not None:
                        dashboard.update_status("Finish requested; stopping microphone input", force=True)
                    break
                if action == "pause":
                    for segment in segmenter.flush():
                        utterance_index += 1
                        segment_queue.put(_SegmentJob(samples=segment.samples, utterance_index=utterance_index))
                        if dashboard is not None:
                            dashboard.update_queue_size(segment_queue.qsize())
                    close = getattr(frame_iter, "close", None)
                    if callable(close):
                        close()
                    frame_iter = None
                    if dashboard is not None:
                        dashboard.update_status("Listening paused; press r to resume or q to finish", force=True)

                    while True:
                        paused_action = keys.pop_action()
                        if paused_action == "finish":
                            finish_requested = True
                            if dashboard is not None:
                                dashboard.update_status("Finish requested; waiting for queued agent work", force=True)
                            break
                        if paused_action == "resume":
                            if dashboard is not None:
                                dashboard.update_status("Resuming microphone input", force=True)
                            frame_iter = iter_microphone_frames(
                                sample_rate=options["sample_rate"],
                                frame_ms=options["frame_ms"],
                                device=options["device"],
                            )
                            segmenter = AudioSegmenter(
                                sample_rate=options["sample_rate"],
                                frame_ms=options["frame_ms"],
                                silence_ms=options["silence_ms"],
                                min_utterance_ms=options["min_utterance_ms"],
                                start_threshold=options["start_threshold"],
                                stop_threshold=options["stop_threshold"],
                            )
                            break
                        time.sleep(0.05)
                    if finish_requested:
                        break
                    if frame_iter is None:
                        continue

                frame = next(frame_iter)

                level = _frame_rms(frame)
                segments = segmenter.process_frame(frame)
                if dashboard is not None:
                    dashboard.update_meter(
                        level=level,
                        recording=segmenter.is_recording,
                        recording_ms=segmenter.recording_ms,
                        silent_tail_ms=segmenter.silent_tail_ms,
                        silence_ms=segmenter.silence_ms,
                    )
                elif options["meter"]:
                    last_meter_update = _maybe_print_meter(
                        frame,
                        segmenter=segmenter,
                        start_threshold=options["start_threshold"],
                        last_update=last_meter_update,
                    )

                for segment in segments:
                    if options["meter"]:
                        print()
                    utterance_index += 1
                    segment_queue.put(_SegmentJob(samples=segment.samples, utterance_index=utterance_index))
                    if dashboard is not None:
                        dashboard.update_queue_size(segment_queue.qsize())
                    if options["max_utterances"] and utterance_index >= options["max_utterances"]:
                        max_utterances_reached = True
                        if dashboard is not None:
                            dashboard.update_status(
                                f"Max utterances ({options['max_utterances']}) reached; waiting for agent",
                                force=True,
                            )
                        break
                if options["max_utterances"] and utterance_index >= options["max_utterances"]:
                    break

            if finish_requested and segmenter is not None:
                for segment in segmenter.flush():
                    utterance_index += 1
                    segment_queue.put(_SegmentJob(samples=segment.samples, utterance_index=utterance_index))
                    if dashboard is not None:
                        dashboard.update_queue_size(segment_queue.qsize())
    except KeyboardInterrupt:
        interrupted = True
        pending_segments = segmenter.flush() if segmenter is not None else []
        for segment in pending_segments:
            utterance_index += 1
            segment_queue.put(_SegmentJob(samples=segment.samples, utterance_index=utterance_index))
            if dashboard is not None:
                dashboard.update_queue_size(segment_queue.qsize())
        print("\nstopped")
        return 0
    except Exception as exc:
        if dashboard is not None:
            dashboard.update_error(str(exc))
        print(f"listen failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if frame_iter is not None:
            close = getattr(frame_iter, "close", None)
            if callable(close):
                close()
        segment_queue.put(None)
        if not interrupted:
            if dashboard is not None:
                if finish_requested:
                    dashboard.update_status("Microphone stopped; waiting for queued agent work", force=True)
                elif max_utterances_reached:
                    dashboard.update_status(
                        f"Listening stopped by --max-utterances {options['max_utterances']}; waiting for agent",
                        force=True,
                    )
            segment_queue.join()
            worker.join(timeout=1)
        else:
            worker.join(timeout=1)
        if dashboard is not None:
            dashboard.stop()
    return 0


def _segment_worker(
    *,
    segment_queue: queue.Queue[_SegmentJob | None],
    options: dict[str, Any],
    workspace: Path,
    agent: ResumableAgent | None,
    log_path: Path,
    dry_run: bool,
    dashboard: TerminalDashboard | None,
) -> None:
    while True:
        job = segment_queue.get()
        try:
            if job is None:
                return
            if dashboard is not None:
                dashboard.update_queue_size(segment_queue.qsize())
            _handle_segment(
                job.samples,
                utterance_index=job.utterance_index,
                options=options,
                workspace=workspace,
                agent=agent,
                log_path=log_path,
                dry_run=dry_run,
                dashboard=dashboard,
            )
        except Exception as exc:
            if dashboard is not None:
                dashboard.update_error(f"agent worker failed: {exc}")
            else:
                print(f"agent worker failed: {exc}", file=sys.stderr)
        finally:
            segment_queue.task_done()
            if dashboard is not None:
                dashboard.update_queue_size(segment_queue.qsize())


class _ListenKeyWatcher:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self._actions: queue.Queue[str] = queue.Queue()
        self._fd: int | None = None
        self._original_attrs: list[Any] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def __enter__(self) -> "_ListenKeyWatcher":
        if not self.enabled or not sys.stdin.isatty() or select is None or termios is None or tty is None:
            return self

        self._fd = sys.stdin.fileno()
        self._original_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self._fd is not None and self._original_attrs is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_attrs)

    def pop_action(self) -> str | None:
        try:
            return self._actions.get_nowait()
        except queue.Empty:
            return None

    def _watch(self) -> None:
        while not self._stop_event.is_set():
            readable, _, _ = select.select([sys.stdin], [], [], 0.10)
            if not readable:
                continue
            key = sys.stdin.read(1)
            if key in {"p", "P"}:
                self._actions.put("pause")
            elif key in {"r", "R"}:
                self._actions.put("resume")
            elif key in {"q", "Q"}:
                self._actions.put("finish")


def _handle_segment(
    samples: list[float],
    *,
    utterance_index: int,
    options: dict[str, Any],
    workspace: Path,
    agent: ResumableAgent | None,
    log_path: Path,
    dry_run: bool,
    dashboard: TerminalDashboard | None = None,
) -> None:
    try:
        tokens = tokenize_samples(
            samples,
            sample_rate=options["sample_rate"],
            frame_ms=options["frame_ms"],
        )
        stats = summarize_tokens(tokens)
        prompt_text = render_prompt(
            PromptInput(
                tokens=tokens,
                stats=stats,
                utterance_index=utterance_index,
                workspace=workspace,
                context=options["context"],
            )
        )
    except Exception as exc:
        _append_jsonl(
            log_path,
            {
                "type": "tokenize_error",
                "utterance_index": utterance_index,
                "error": str(exc),
                "timestamp": time.time(),
            },
        )
        print(f"utterance #{utterance_index}: tokenization failed: {exc}", file=sys.stderr)
        if dashboard is not None:
            dashboard.update_error(f"utterance #{utterance_index}: tokenization failed: {exc}")
        return

    if dashboard is None:
        print(f"utterance #{utterance_index}: {len(tokens)} tokens")
    if dashboard is not None:
        dashboard.update_utterance(utterance_index=utterance_index, tokens=tokens)
    event: dict[str, Any] = {
        "type": "utterance",
        "utterance_index": utterance_index,
        "tokens": tokens,
        "stats": stats,
        "prompt": prompt_text,
        "agent": options["agent"],
        "model": options["model"],
        "reasoning_effort": options["reasoning_effort"],
        "dry_run": dry_run,
        "timestamp": time.time(),
    }

    if dry_run:
        if dashboard is None:
            print(prompt_text)
        event["submit_status"] = "dry_run"
        event["reply"] = "Dry run: prompt rendered; no agent was called."
        _append_jsonl(log_path, event)
        if dashboard is not None:
            dashboard.update_reply(_prompt_preview(prompt_text))
        return

    assert agent is not None
    if dashboard is not None:
        dashboard.update_agent_status(f"running {options['agent']}")
        dashboard.update_agent_output("processor: prompt submitted; waiting for agent stream")
    result = agent.submit(prompt_text, on_output=_make_output_callback(dashboard))
    reply = result.display_reply
    event.update(
        {
            "submit_status": "ok" if result.exit_code == 0 else "error",
            "command": result.command,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "reply": reply,
            "elapsed_seconds": result.elapsed_seconds,
            "session_id": result.session_id,
            "timed_out": result.timed_out,
            "idle_timed_out": result.idle_timed_out,
        }
    )
    _append_jsonl(log_path, event)
    if dashboard is None:
        print(f"agent exit: {result.exit_code} ({result.elapsed_seconds:.1f}s)")
        if result.timed_out:
            print("agent timed out")
        if result.idle_timed_out:
            print("agent idle timed out")
        print("agent reply:")
        print(reply)
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
    if dashboard is not None:
        timeout_text = " timed out" if result.timed_out else " idle timed out" if result.idle_timed_out else ""
        dashboard.update_reply(f"exit {result.exit_code}{timeout_text} in {result.elapsed_seconds:.1f}s\n{reply}")


def _resolve_listen_options(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    audio = config["audio"]
    agent = config["agent"]
    prompt = config["prompt"]
    logging = config["logging"]

    dry_run = bool(agent["dry_run"])
    if args.dry_run:
        dry_run = True

    open_permissions = bool(agent["open_permissions"])
    if args.no_open_permissions:
        open_permissions = False

    agent_timeout = args.agent_timeout_seconds
    if agent_timeout is None:
        agent_timeout = agent.get("timeout_seconds", 600)
    if agent_timeout is not None and agent_timeout <= 0:
        agent_timeout = None

    agent_idle_timeout = args.agent_idle_timeout_seconds
    if agent_idle_timeout is None:
        agent_idle_timeout = agent.get("idle_timeout_seconds", 120)
    if agent_idle_timeout is not None and agent_idle_timeout <= 0:
        agent_idle_timeout = None

    explicit_thresholds = args.start_threshold is not None or args.stop_threshold is not None

    return {
        "agent": args.agent or agent["name"],
        "model": args.model if args.model is not None else agent.get("model"),
        "reasoning_effort": args.reasoning_effort if args.reasoning_effort is not None else agent.get("reasoning_effort"),
        "workspace": args.workspace or agent["workspace"],
        "context": prompt["context"] if args.context is None else args.context,
        "sample_rate": args.sample_rate or audio["sample_rate"],
        "frame_ms": args.frame_ms or audio["frame_ms"],
        "silence_ms": args.silence_ms or audio["silence_ms"],
        "min_utterance_ms": args.min_utterance_ms or audio["min_utterance_ms"],
        "auto_threshold": bool(audio.get("auto_threshold", True)) and not bool(args.no_auto_threshold) and not explicit_thresholds,
        "calibration_ms": args.calibration_ms if args.calibration_ms is not None else int(audio.get("calibration_ms", 1200)),
        "start_threshold": args.start_threshold if args.start_threshold is not None else audio["start_threshold"],
        "stop_threshold": args.stop_threshold if args.stop_threshold is not None else audio["stop_threshold"],
        "device": args.device,
        "log": args.log or logging["path"],
        "dry_run": dry_run,
        "open_permissions": open_permissions,
        "agent_timeout_seconds": agent_timeout,
        "agent_idle_timeout_seconds": agent_idle_timeout,
        "max_utterances": args.max_utterances,
        "meter": bool(args.meter),
        "ui": bool(args.ui),
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


_INSTRUCTIONS_START = "<!-- generated-game-input-instructions:start -->"
_INSTRUCTIONS_END = "<!-- generated-game-input-instructions:end -->"


def _instruction_file_name(agent_name: str) -> str:
    if agent_name == "claude":
        return "CLAUDE.md"
    return "AGENTS.md"


def _ensure_workspace_instructions(*, workspace: Path, agent_name: str, context: str) -> Path:
    path = workspace / _instruction_file_name(agent_name)
    instructions = render_agent_instructions(context).rstrip()
    block = f"{_INSTRUCTIONS_START}\n{instructions}\n{_INSTRUCTIONS_END}\n"

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        start = existing.find(_INSTRUCTIONS_START)
        end = existing.find(_INSTRUCTIONS_END)
        if start != -1 and end != -1 and start < end:
            end += len(_INSTRUCTIONS_END)
            updated = existing[:start] + block.rstrip() + existing[end:]
            if not updated.endswith("\n"):
                updated += "\n"
        else:
            separator = "\n\n" if existing.strip() else ""
            updated = existing.rstrip() + separator + block
    else:
        updated = f"# Project Instructions\n\n{block}"

    if not path.exists() or path.read_text(encoding="utf-8") != updated:
        path.write_text(updated, encoding="utf-8")
    return path


def _default_log_path(workspace: Path) -> Path:
    digest = sha1(str(workspace).encode("utf-8")).hexdigest()[:10]
    workspace_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in workspace.name) or "workspace"
    return Path.home() / ".cache" / "processor-sessions" / f"{workspace_name}-{digest}" / "session.jsonl"


def _maybe_auto_calibrate_thresholds(
    frame_iter: Iterator[list[float]],
    *,
    options: dict[str, Any],
    dashboard: TerminalDashboard | None,
) -> None:
    if not options["auto_threshold"] or options["calibration_ms"] <= 0:
        if dashboard is not None:
            dashboard.update_thresholds(
                start_threshold=options["start_threshold"],
                stop_threshold=options["stop_threshold"],
                note="configured",
            )
        return

    total_ms = max(options["frame_ms"], int(options["calibration_ms"]))
    frame_count = max(1, math.ceil(total_ms / options["frame_ms"]))
    levels: list[float] = []
    last_meter_update = 0.0

    if dashboard is None:
        print(f"calibrating noise for {total_ms} ms; stay quiet")

    for index in range(frame_count):
        frame = next(frame_iter)
        level = _frame_rms(frame)
        levels.append(level)
        elapsed_ms = min(total_ms, (index + 1) * options["frame_ms"])
        if dashboard is not None:
            dashboard.update_calibration(level=level, elapsed_ms=elapsed_ms, total_ms=total_ms)
        elif options["meter"]:
            last_meter_update = _maybe_print_calibration_meter(
                level=level,
                elapsed_ms=elapsed_ms,
                total_ms=total_ms,
                last_update=last_meter_update,
            )

    thresholds = _suggest_thresholds_from_noise(
        levels,
        configured_start=options["start_threshold"],
        configured_stop=options["stop_threshold"],
    )
    options["start_threshold"] = thresholds["start_threshold"]
    options["stop_threshold"] = thresholds["stop_threshold"]
    note = f"auto noise p95={thresholds['p95']:.4f}"

    if dashboard is not None:
        dashboard.update_thresholds(
            start_threshold=options["start_threshold"],
            stop_threshold=options["stop_threshold"],
            note=note,
        )
    else:
        if options["meter"]:
            print()
        print(
            "auto thresholds: "
            f"start {options['start_threshold']:.5f}, stop {options['stop_threshold']:.5f} "
            f"(noise p50/p90/p95/max "
            f"{thresholds['p50']:.5f}/{thresholds['p90']:.5f}/{thresholds['p95']:.5f}/{thresholds['max']:.5f})"
        )


def _suggest_thresholds_from_noise(
    levels: list[float],
    *,
    configured_start: float,
    configured_stop: float,
) -> dict[str, float]:
    sorted_levels = sorted(levels)
    p50 = _percentile(sorted_levels, 0.50)
    p90 = _percentile(sorted_levels, 0.90)
    p95 = _percentile(sorted_levels, 0.95)
    max_level = max(sorted_levels) if sorted_levels else 0.0

    stop_threshold = max(configured_stop, p90 * 1.20, p50 * 1.60)
    start_threshold = max(configured_start, stop_threshold * 1.35, p95 * 1.20)

    return {
        "p50": p50,
        "p90": p90,
        "p95": p95,
        "max": max_level,
        "start_threshold": start_threshold,
        "stop_threshold": stop_threshold,
    }


def _make_output_callback(dashboard: TerminalDashboard | None):
    def on_output(source: str, line: str) -> None:
        formatted = format_stream_line(source, line)
        if not formatted:
            return
        if dashboard is not None:
            dashboard.update_agent_output(formatted)
        else:
            print(formatted, flush=True)

    return on_output


def _print_listen_header(
    options: dict[str, Any],
    *,
    workspace: Path,
    log_path: Path,
    dry_run: bool,
    open_permissions: bool,
    instruction_path: Path | None,
) -> None:
    print("dogsound processor listening")
    print(f"workspace: {workspace}")
    print(f"agent: {options['agent']}")
    print(f"model: {options['model'] or '(default)'}")
    print(f"reasoning effort: {options['reasoning_effort'] or '(default)'}")
    print(f"instructions: {instruction_path or '(dry run; not written)'}")
    print(f"open permissions: {open_permissions}")
    print(f"dry run: {dry_run}")
    print(f"agent timeout: {options['agent_timeout_seconds']}")
    print(f"agent idle timeout: {options['agent_idle_timeout_seconds'] if options['agent_idle_timeout_seconds'] is not None else 'off'}")
    print(f"auto threshold: {options['auto_threshold']} ({options['calibration_ms']} ms quiet calibration)")
    print(f"thresholds: start {options['start_threshold']:.5f} / stop {options['stop_threshold']:.5f}")
    print(f"log: {log_path}")
    if options["meter"]:
        print("meter: enabled (speak until the state changes to REC, then pause for silence detection)")
    if open_permissions and not dry_run:
        print("warning: the selected agent can run commands and edit files without approval.")
    sys.stdout.flush()


def _prompt_preview(prompt_text: str) -> str:
    lines = [line for line in prompt_text.splitlines() if line.strip()]
    return "Dry run: prompt rendered; no agent was called.\n" + "\n".join(lines[:10])


def _maybe_print_meter(
    frame: list[float],
    *,
    segmenter: AudioSegmenter,
    start_threshold: float,
    last_update: float,
) -> float:
    now = time.monotonic()
    if now - last_update < 0.20:
        return last_update

    level = _frame_rms(frame)
    width = 24
    filled = min(width, int(level / max(start_threshold, 1e-9) * width))
    bar = "#" * filled + "-" * (width - filled)
    state = "REC" if segmenter.is_recording else "wait"
    print(f"\rlevel {level:0.4f} [{bar}] {state}", end="", flush=True)
    return now


def _maybe_print_calibration_meter(
    *,
    level: float,
    elapsed_ms: int,
    total_ms: int,
    last_update: float,
) -> float:
    now = time.monotonic()
    if now - last_update < 0.20:
        return last_update

    width = 24
    filled = min(width, int(level / 0.10 * width))
    bar = "#" * filled + "-" * (width - filled)
    print(f"\rnoise {level:0.4f} [{bar}] calibrating {elapsed_ms}/{total_ms} ms", end="", flush=True)
    return now


def _frame_rms(frame: list[float]) -> float:
    if not frame:
        return 0.0
    return (sum(value * value for value in frame) / len(frame)) ** 0.5


def _level_bar(level: float) -> str:
    width = 32
    filled = min(width, int(level / 0.03 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round((len(sorted_values) - 1) * ratio)))
    return sorted_values[index]
