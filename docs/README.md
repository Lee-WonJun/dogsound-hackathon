# Plan Z: Tunk

A compact Phaser 3 browser game. Collect the three plan shards in order, grab optional FEED cells for extra time, dodge trace drones, ride or fight the coded drift fields, carry the charged core to Zone Z, then press `Space` to tunk it into the gate before the timer expires.

## Run

```bash
python3 -m http.server 4174
```

Open `http://localhost:4174`.

## Controls

- `A` / `D` or arrow keys: move
- `W` / up arrow: jump
- `Shift`: ZHA brace, a one-use momentum stabilizer that recharges on the ground
- `Space`: tunk at Zone Z
- `R`: restart

## Objective

Collect `F`, `J`, and `D` in order. FEED cells add time but sit near riskier routes. Trace drones patrol fixed lanes and fail the run on contact. Colored fields labeled `XX`, `WW`, `YY`, and `FO` apply directional drift while you pass through them, so the shortest route is not always the safest route. Use the ZHA brace when drift or a landing goes wrong. Zone Z rejects uncharged plans with AZ repulsion; after the plan is charged, the ZA anchor gently pulls you toward the final tunk.

## Install

No install is required to run the game. Phaser is loaded from a CDN.

For local checks with Node:

```bash
npm test
```

## Build

This is a static project. The build check validates that the expected files exist:

```bash
npm run build
```

## Project Notes

The design interpretation is recorded in [ANALYSIS.md](./ANALYSIS.md).
