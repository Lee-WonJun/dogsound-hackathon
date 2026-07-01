# [개ː소리]

<img width="970" height="663" alt="개솔" src="https://github.com/user-attachments/assets/4cfbd697-ef08-4a4f-bf2b-6532876f869c" />

A PoC for turning dogsound input into game-building instructions for coding agents.

[한국어 README](./README.md)

- Demo: https://lee-wonjun.github.io/dogsound-hackathon/
- Generated game source: [docs/](./docs/)
- Game interpretation log: [docs/ANALYSIS.md](./docs/ANALYSIS.md)
- Processor documentation: [processor/README.md](./processor/README.md)

## What This Is

`processor/` records microphone input in real time, segments it by silence, converts each captured utterance into compact text, and sends that input to Codex or Claude Code.

`docs/` contains a generated Phaser game built through this process. The repository is configured so GitHub Pages can serve `/docs` directly.

## Inspiration

This PoC was inspired by Caleb Leak's [I Taught My Dog to Vibe Code Games](https://www.calebleak.com/posts/dog-game/) and Korea's voice-coding hackathon [천하제일 입코딩 대회](https://lipcoding.kr/).

The important part of Caleb Leak's post was not the meaningless input itself, but the prompt and feedback loop that made the agent read that input as game design direction. The lipcoding hackathon suggested the event format: building software through voice instead of a keyboard.

So this project is a small experiment in making games from dogsound. The tokenizer is intentionally rough and vibe-coded for the PoC; it is not claiming to decode a real language.

## What Happened So Far

Running the process end to end does make games. The current weak point is the harness: generated games can still be impossible to clear.

The next serious work is not just more prompt text. The system needs sharper feedback:

- automated playability checks
- win-condition reachability checks
- screenshots visible to the agent
- scripted input playback
- a loop that rejects impossible builds and makes the agent fix them

With that harness, this could become a real dogsound hackathon. The funny part is the input, but the core is the feedback loop that turns that input into something playable.

## Run The Processor

```bash
cd /home/dldnjs1013/projects/dogsound
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r processor/requirements.txt
python -m processor doctor
```

Example live run with GPT-5.5 low reasoning:

```bash
python -m processor listen \
  --ui \
  --agent codex \
  --model gpt-5.5 \
  --reasoning-effort low \
  --workspace /home/dldnjs1013/projects/game \
  --silence-ms 2500 \
  --min-utterance-ms 80 \
  --agent-idle-timeout-seconds 0
```

## Run The Demo Game Locally

```bash
cd docs
python3 -m http.server 4174
```

Open `http://localhost:4174`.

Checks:

```bash
cd docs
npm test
npm run build
```

## Analysis Example

The generated game keeps a project-facing interpretation record before implementation changes. Full history is in [docs/ANALYSIS.md](./docs/ANALYSIS.md).

Example excerpt:

```md
# Input Analysis

Input: `fjdjvtpkplanztunk`

Possible readings considered:

- `dj` and the hard consonants could imply rhythm-first play, with beats and impact timing.
- `vtpk` can be read as compact movement notation: vertical, turn, parkour, kick.
- `plan z tunk` is the clearest semantic cluster: an emergency plan, a final zone, and a heavy dunk/thunk action.

Chosen reading:

Build `Plan Z: Tunk`, a small vertical action-puzzle where the player gathers plan shards in order, then slams the completed plan core into the Zone Z exit. This fits the readable center of the input while using the surrounding hard consonants as movement and collision feel. The scope is a complete single-screen browser game rather than a map-only update because the repository has no existing implementation.
```

## GitHub Pages

This repository publishes GitHub Pages from the `main` branch `/docs` directory.
