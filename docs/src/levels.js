export const LEVEL_WIDTH = 960;
export const LEVEL_HEIGHT = 540;

export const PLAN_SHARDS = [
  { id: "F", x: 192, y: 352, color: 0xffd166 },
  { id: "J", x: 504, y: 224, color: 0x7bdff2 },
  { id: "D", x: 748, y: 124, color: 0xf694c1 }
];

export const PLATFORMS = [
  { x: 480, y: 518, width: 960, height: 44 },
  { x: 166, y: 410, width: 240, height: 24 },
  { x: 432, y: 324, width: 230, height: 24 },
  { x: 690, y: 234, width: 240, height: 24 },
  { x: 826, y: 410, width: 170, height: 24 },
  { x: 34, y: 270, width: 68, height: 24 }
];

export const HAZARDS = [
  { x: 324, y: 494, width: 76, height: 20 },
  { x: 616, y: 494, width: 76, height: 20 },
  { x: 768, y: 388, width: 64, height: 18 }
];

export const FEED_CELLS = [
  { id: "feed-f", label: "F", x: 96, y: 240, color: 0xfff0a6 },
  { id: "feed-e1", label: "E", x: 358, y: 286, color: 0xfff0a6 },
  { id: "feed-e2", label: "E", x: 632, y: 188, color: 0xfff0a6 },
  { id: "feed-d", label: "D", x: 826, y: 368, color: 0xfff0a6 }
];

export const TRACE_DRONES = [
  { id: "rr", axis: "x", start: 358, end: 502, fixed: 292, size: 24, period: 2.8, offset: 0 },
  { id: "ss", axis: "y", start: 102, end: 202, fixed: 604, size: 24, period: 2.4, offset: 0.8 },
  { id: "tr", axis: "x", start: 706, end: 870, fixed: 458, size: 26, period: 3.2, offset: 1.4 }
];

export const DRIFT_FIELDS = [
  { id: "XX", x: 215, y: 196, width: 118, height: 156, forceX: -330, forceY: 0, color: 0x7bdff2 },
  { id: "WW", x: 494, y: 353, width: 132, height: 126, forceX: 250, forceY: -40, color: 0xc9ff45 },
  { id: "YY", x: 644, y: 78, width: 120, height: 136, forceX: 0, forceY: -360, color: 0xf694c1 },
  { id: "FO", x: 810, y: 265, width: 96, height: 122, forceX: 180, forceY: 90, color: 0xffd166 }
];

export const PLAYER_START = { x: 72, y: 452 };
export const EXIT_ZONE = { x: 888, y: 348, width: 56, height: 128 };
export const TIME_LIMIT_SECONDS = 75;
