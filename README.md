# Dogsound Hackathon

Live input-to-agent processor plus a generated Phaser game demo.

- GitHub Pages demo: https://lee-wonjun.github.io/dogsound-hackathon/
- Generated game source: [docs/](./docs/)
- Full game interpretation log: [docs/ANALYSIS.md](./docs/ANALYSIS.md)
- Processor documentation: [processor/README.md](./processor/README.md)

## What This Contains

The `processor/` folder records microphone input, segments it by silence,
turns each captured utterance into compact text input, and sends that input to
Codex or Claude Code with open permissions.

The `docs/` folder contains the generated browser game from
`/home/dldnjs1013/projects/game`. It is arranged as a static site so GitHub
Pages can serve it directly from `/docs`.

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

The generated game keeps a project-facing interpretation record before
implementation changes. Full history is in [docs/ANALYSIS.md](./docs/ANALYSIS.md).

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

This repository is intended to publish GitHub Pages from the `main` branch
`/docs` directory.
