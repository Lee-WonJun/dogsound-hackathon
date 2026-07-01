# Dogsound Processor

Real-time dogsound control for coding agents.

Pipeline:

```text
microphone -> silence-ended utterance -> a-z tokens -> raw agent input -> Codex or Claude Code
```

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r processor/requirements.txt
python -m processor doctor
```

Linux live recording needs either a working PortAudio runtime for
`sounddevice` or an ALSA capture device. If `doctor` reports `PortAudio library
not found`, install the system package usually named `libportaudio2`, or run on a
machine/container where ALSA exposes a microphone such as `default`.

On WSL, the processor automatically falls back to Windows DirectShow through
`ffmpeg.exe` when PortAudio is unavailable. Check the detected device with:

```bash
python -m processor doctor
```

If multiple Windows microphones exist, pass the DirectShow device name:

```bash
python -m processor listen --device "Microphone Array(Intel® Smart Sound Technology for Digital Microphones)"
```

## Commands

```bash
python -m processor doctor
python -m processor tokenize poc/sound.mp3
python -m processor prompt abcxyz
python -m processor listen --agent codex --workspace /home/dldnjs1013/projects/dogsound
```

By default, `listen` writes its JSONL session log outside the target workspace
under `~/.cache/processor-sessions/.../session.jsonl`. This keeps agent-visible
project folders free of processor bookkeeping. Override this with `--log PATH`
when you want the log elsewhere; relative `--log` paths are resolved inside the
target workspace.

Use `--ui` to show a terminal dashboard with microphone level, recording state,
token preview, live agent stdout/stderr, agent status, and the last agent reply:

```bash
python -m processor listen --ui --agent codex --workspace /path/to/project
```

Pass a Codex model when needed:

```bash
python -m processor listen --ui --agent codex --model gpt-5.3-codex-spark --workspace /path/to/project
```

Use GPT-5.5 with low reasoning effort:

```bash
python -m processor listen --ui --agent codex --model gpt-5.5 --reasoning-effort low --workspace /path/to/project
```

In UI mode, use the keyboard controls for session flow:

- `p`: pause microphone input. If a recording is active, it is flushed and
  queued before pausing.
- `r`: resume microphone input after a pause.
- `q`: finish the session. This stops microphone input, flushes the current
  recording if one is active, waits for queued agent work to finish, then exits
  normally.

`Ctrl-C` is still available as an interrupt.

Do not pass `--max-utterances 1` for normal live use. That option intentionally
stops listening after the first captured utterance and waits for the queued
agent run to finish. Use it only for one-shot tests.

By default, `listen` first performs a short live noise calibration. Stay quiet
for the first `1200 ms`; the processor raises `start_threshold` and
`stop_threshold` from the measured idle RMS so normal room or WSL microphone
noise does not keep the recorder stuck in `REC`. The UI shows the calibrated
thresholds and the current quiet tail. Submission happens only after the input
falls below `stop_threshold` for `--silence-ms`; there is no timed auto-submit.
The default minimum accepted utterance is `120 ms`; use
`--min-utterance-ms 80` if you need very short inputs.

Disable calibration when passing fixed thresholds yourself:

```bash
python -m processor listen --ui --no-auto-threshold --start-threshold 0.12 --stop-threshold 0.08
```

Agent execution streams output into the dashboard while it runs. The processor
also prints its own heartbeat line such as `waiting for agent output; idle 12s`
because Codex or Claude Code may produce no stdout/stderr while a child command
is still running. Agent runs have a default 600 second wall-clock timeout and a
default 120 second no-output timeout. Use `--agent-timeout-seconds 0` or
`--agent-idle-timeout-seconds 0` to disable either timeout. Captured utterances
are handed to a background worker, so the microphone and UI loop keep running
while Codex or Claude Code processes the queued input.

Before the first agent run, `listen` writes the game-building instructions into
the target workspace: `AGENTS.md` for Codex, `CLAUDE.md` for Claude Code. If the
file already exists, processor-managed instructions are added or replaced inside
a marked block and the rest of the file is preserved.

Those workspace instructions define the input as game design direction written
by a brilliant game designer in a cipher-like shorthand. The downstream agent
translates it into product planning and game design requirements, then chooses
the implementation work that best fits the project. The input and project needs
decide the scope instead of a fixed type of change. The instructions also
require the downstream project to keep a root `README.md`, and to write a
compact analysis note before changing implementation code. That note should
consider multiple possible readings, record the chosen reading and why it fits,
and avoid defaulting to a map update unless map work is the best fit. The note
should live in `README.md` or `ANALYSIS.md`.

The text sent to Codex or Claude is only the captured input value. There is no
repeated instruction wrapper in the agent message.

`listen` runs with open permissions by default. For Codex, the adapter uses
`codex exec` and `codex exec resume` with `--dangerously-bypass-approvals-and-sandbox`.
For Claude Code, it uses print mode with `--dangerously-skip-permissions` and
continues with `-c`.

Use `--dry-run` to print captured inputs without calling an agent or writing
workspace instructions:

```bash
python -m processor listen --dry-run
```

## Safety

This tool is designed for a user who cannot approve prompts manually. That means
the default mode lets the selected agent edit files and run commands without
approval. Use a disposable workspace or version control when testing real agent
execution.
