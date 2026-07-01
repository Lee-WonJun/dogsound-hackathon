import test from "node:test";
import assert from "node:assert/strict";

import { DRIFT_FIELDS, EXIT_ZONE, FEED_CELLS, PLAN_SHARDS, TIME_LIMIT_SECONDS, TRACE_DRONES } from "../src/levels.js";
import { dronePositionAt, pingPongProgress } from "../src/motion.js";
import {
  boundsOverlap,
  collectFeedCell,
  collectShard,
  consumeZhaBrace,
  createInitialState,
  expectedShardId,
  rechargeZhaBrace,
  resolveAntiZoneForce,
  resolveDriftForce,
  resolveZoneAnchorForce,
  tickTimer,
  tunk
} from "../src/state.js";

test("plan shards must be collected in deterministic order", () => {
  let state = createInitialState();
  assert.equal(expectedShardId(state), "F");

  state = collectShard(state, PLAN_SHARDS[0].id);
  assert.deepEqual(state.collected, ["F"]);
  assert.equal(expectedShardId(state), "J");

  state = collectShard(state, PLAN_SHARDS[1].id);
  state = collectShard(state, PLAN_SHARDS[2].id);
  assert.equal(state.charged, true);
  assert.equal(expectedShardId(state), null);
});

test("wrong shard fails the run", () => {
  const state = collectShard(createInitialState(), "J");
  assert.equal(state.failed, true);
  assert.deepEqual(state.collected, []);
});

test("timer fails when it reaches zero", () => {
  const state = tickTimer(createInitialState(), TIME_LIMIT_SECONDS);
  assert.equal(state.timeLeft, 0);
  assert.equal(state.failed, true);
});

test("tunk only wins when charged and inside Zone Z", () => {
  const inside = {
    left: EXIT_ZONE.x + 8,
    right: EXIT_ZONE.x + 30,
    top: EXIT_ZONE.y + 8,
    bottom: EXIT_ZONE.y + 30
  };
  const outside = {
    left: 10,
    right: 32,
    top: 10,
    bottom: 32
  };

  let state = createInitialState();
  for (const shard of PLAN_SHARDS) {
    state = collectShard(state, shard.id);
  }

  assert.equal(tunk(state, outside, EXIT_ZONE).won, false);
  assert.equal(tunk(state, inside, EXIT_ZONE).won, true);
});

test("drift fields resolve deterministic combined force", () => {
  const firstField = DRIFT_FIELDS[0];
  const secondField = DRIFT_FIELDS[1];
  const playerBounds = {
    left: firstField.x + 18,
    right: firstField.x + 26,
    top: firstField.y + 18,
    bottom: firstField.y + 26
  };

  assert.equal(boundsOverlap(playerBounds, firstField), true);
  assert.equal(boundsOverlap(playerBounds, secondField), false);

  const drift = resolveDriftForce(playerBounds, DRIFT_FIELDS);
  assert.deepEqual(drift, {
    x: firstField.forceX,
    y: firstField.forceY,
    active: [firstField.id]
  });
});

test("ZHA brace can be consumed once and recharged", () => {
  let state = createInitialState();
  assert.equal(state.zhaReady, true);

  state = consumeZhaBrace(state);
  assert.equal(state.zhaReady, false);

  state = consumeZhaBrace(state);
  assert.equal(state.zhaReady, false);

  state = rechargeZhaBrace(state);
  assert.equal(state.zhaReady, true);
});

test("ZA anchor only activates for a charged plan near Zone Z", () => {
  const nearZone = {
    left: EXIT_ZONE.x - 16,
    right: EXIT_ZONE.x + 8,
    top: EXIT_ZONE.y + 20,
    bottom: EXIT_ZONE.y + 44
  };

  let state = createInitialState();
  assert.deepEqual(resolveZoneAnchorForce(state, nearZone, EXIT_ZONE), { x: 0, y: 0, active: false });

  for (const shard of PLAN_SHARDS) {
    state = collectShard(state, shard.id);
  }

  const anchor = resolveZoneAnchorForce(state, nearZone, EXIT_ZONE);
  assert.equal(anchor.active, true);
  assert.equal(anchor.x, 110);
});

test("AZ repulsion only activates for an uncharged plan near Zone Z", () => {
  const nearZone = {
    left: EXIT_ZONE.x - 16,
    right: EXIT_ZONE.x + 8,
    top: EXIT_ZONE.y + 20,
    bottom: EXIT_ZONE.y + 44
  };

  let state = createInitialState();
  const repulsion = resolveAntiZoneForce(state, nearZone, EXIT_ZONE);
  assert.equal(repulsion.active, true);
  assert.equal(repulsion.x, -150);

  for (const shard of PLAN_SHARDS) {
    state = collectShard(state, shard.id);
  }

  assert.deepEqual(resolveAntiZoneForce(state, nearZone, EXIT_ZONE), { x: 0, y: 0, active: false });
});

test("FEED cells are one-time timer bonuses with a cap", () => {
  let state = createInitialState();
  const startTime = state.timeLeft;

  state = tickTimer(state, 20);
  state = collectFeedCell(state, FEED_CELLS[0].id);
  assert.equal(state.feedCollected.length, 1);
  assert.equal(state.timeLeft, startTime - 14);

  state = collectFeedCell(state, FEED_CELLS[0].id);
  assert.equal(state.feedCollected.length, 1);

  for (const cell of FEED_CELLS.slice(1)) {
    state = collectFeedCell(state, cell.id);
  }
  assert.equal(state.feedCollected.length, FEED_CELLS.length);
  assert.equal(state.timeLeft <= TIME_LIMIT_SECONDS + 24, true);
});

test("trace drone motion is deterministic ping-pong", () => {
  const drone = TRACE_DRONES[0];
  assert.equal(pingPongProgress(0, 4), 0);
  assert.equal(pingPongProgress(1, 4), 0.5);
  assert.equal(pingPongProgress(2, 4), 1);
  assert.equal(pingPongProgress(3, 4), 0.5);

  assert.deepEqual(dronePositionAt(drone, 0), { x: drone.start, y: drone.fixed });
  assert.deepEqual(dronePositionAt(drone, drone.period / 2), { x: drone.end, y: drone.fixed });
});
