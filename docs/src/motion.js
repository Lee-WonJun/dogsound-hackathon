export function pingPongProgress(timeSeconds, periodSeconds, offsetSeconds = 0) {
  if (periodSeconds <= 0) {
    return 0;
  }

  const cycle = ((timeSeconds + offsetSeconds) % periodSeconds) / periodSeconds;
  return cycle <= 0.5 ? cycle * 2 : (1 - cycle) * 2;
}

export function dronePositionAt(drone, timeSeconds) {
  const progress = pingPongProgress(timeSeconds, drone.period, drone.offset);
  const moving = drone.start + (drone.end - drone.start) * progress;

  return drone.axis === "x"
    ? { x: moving, y: drone.fixed }
    : { x: drone.fixed, y: moving };
}
