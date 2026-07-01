import { PLAN_SHARDS, TIME_LIMIT_SECONDS } from "./levels.js";

export const FEED_BONUS_SECONDS = 6;
export const MAX_FEED_BONUS_SECONDS = 24;

export function createInitialState() {
  return {
    nextShardIndex: 0,
    collected: [],
    feedCollected: [],
    charged: false,
    zhaReady: true,
    won: false,
    failed: false,
    timeLeft: TIME_LIMIT_SECONDS
  };
}

export function expectedShardId(state) {
  return PLAN_SHARDS[state.nextShardIndex]?.id ?? null;
}

export function collectShard(state, shardId) {
  if (state.won || state.failed || state.charged) {
    return { ...state };
  }

  if (shardId !== expectedShardId(state)) {
    return { ...state, failed: true };
  }

  const collected = [...state.collected, shardId];
  return {
    ...state,
    collected,
    nextShardIndex: state.nextShardIndex + 1,
    charged: collected.length === PLAN_SHARDS.length
  };
}

export function tickTimer(state, deltaSeconds) {
  if (state.won || state.failed) {
    return { ...state };
  }

  const timeLeft = Math.max(0, state.timeLeft - deltaSeconds);
  return {
    ...state,
    timeLeft,
    failed: timeLeft <= 0
  };
}

export function collectFeedCell(state, cellId) {
  if (state.won || state.failed || state.feedCollected.includes(cellId)) {
    return { ...state };
  }

  return {
    ...state,
    feedCollected: [...state.feedCollected, cellId],
    timeLeft: Math.min(TIME_LIMIT_SECONDS + MAX_FEED_BONUS_SECONDS, state.timeLeft + FEED_BONUS_SECONDS)
  };
}

export function canTunk(state, playerBounds, exitZone) {
  if (!state.charged || state.won || state.failed) {
    return false;
  }

  return !(
    playerBounds.right < exitZone.x ||
    playerBounds.left > exitZone.x + exitZone.width ||
    playerBounds.bottom < exitZone.y ||
    playerBounds.top > exitZone.y + exitZone.height
  );
}

export function tunk(state, playerBounds, exitZone) {
  if (!canTunk(state, playerBounds, exitZone)) {
    return { ...state };
  }

  return { ...state, won: true };
}

export function boundsOverlap(a, b) {
  return !(
    a.right < b.x ||
    a.left > b.x + b.width ||
    a.bottom < b.y ||
    a.top > b.y + b.height
  );
}

export function resolveDriftForce(playerBounds, driftFields) {
  return driftFields.reduce(
    (force, field) => {
      if (!boundsOverlap(playerBounds, field)) {
        return force;
      }

      return {
        x: force.x + field.forceX,
        y: force.y + field.forceY,
        active: [...force.active, field.id]
      };
    },
    { x: 0, y: 0, active: [] }
  );
}

export function resolveZoneAnchorForce(state, playerBounds, exitZone) {
  if (!state.charged || state.won || state.failed) {
    return { x: 0, y: 0, active: false };
  }

  const anchorZone = {
    x: exitZone.x - 54,
    y: exitZone.y - 36,
    width: exitZone.width + 108,
    height: exitZone.height + 72
  };

  if (!boundsOverlap(playerBounds, anchorZone)) {
    return { x: 0, y: 0, active: false };
  }

  const playerCenter = {
    x: (playerBounds.left + playerBounds.right) / 2,
    y: (playerBounds.top + playerBounds.bottom) / 2
  };
  const exitCenter = {
    x: exitZone.x + exitZone.width / 2,
    y: exitZone.y + exitZone.height / 2
  };

  return {
    x: Math.sign(exitCenter.x - playerCenter.x) * 110,
    y: Math.sign(exitCenter.y - playerCenter.y) * 70,
    active: true
  };
}

export function resolveAntiZoneForce(state, playerBounds, exitZone) {
  if (state.charged || state.won || state.failed) {
    return { x: 0, y: 0, active: false };
  }

  const antiZone = {
    x: exitZone.x - 46,
    y: exitZone.y - 28,
    width: exitZone.width + 92,
    height: exitZone.height + 56
  };

  if (!boundsOverlap(playerBounds, antiZone)) {
    return { x: 0, y: 0, active: false };
  }

  const playerCenter = {
    x: (playerBounds.left + playerBounds.right) / 2,
    y: (playerBounds.top + playerBounds.bottom) / 2
  };
  const exitCenter = {
    x: exitZone.x + exitZone.width / 2,
    y: exitZone.y + exitZone.height / 2
  };

  return {
    x: Math.sign(playerCenter.x - exitCenter.x || -1) * 150,
    y: Math.sign(playerCenter.y - exitCenter.y || -1) * 85,
    active: true
  };
}

export function consumeZhaBrace(state) {
  if (!state.zhaReady || state.won || state.failed) {
    return { ...state };
  }

  return { ...state, zhaReady: false };
}

export function rechargeZhaBrace(state) {
  if (state.zhaReady || state.won || state.failed) {
    return { ...state };
  }

  return { ...state, zhaReady: true };
}
