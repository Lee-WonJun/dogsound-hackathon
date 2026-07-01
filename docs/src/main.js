import {
  DRIFT_FIELDS,
  EXIT_ZONE,
  FEED_CELLS,
  HAZARDS,
  LEVEL_HEIGHT,
  LEVEL_WIDTH,
  PLAN_SHARDS,
  PLATFORMS,
  PLAYER_START,
  TRACE_DRONES
} from "./levels.js";
import { dronePositionAt } from "./motion.js";
import {
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
} from "./state.js";

const palette = {
  bg: 0x10141f,
  ink: "#eef3ff",
  muted: "#9aa7bd",
  platform: 0x293247,
  platformEdge: 0x51617f,
  player: 0x8cffc1,
  hazard: 0xff5d5d,
  exit: 0xc9ff45
};

class TunkScene extends Phaser.Scene {
  constructor() {
    super("TunkScene");
    this.state = createInitialState();
    this.elapsedAccumulator = 0;
  }

  create() {
    this.state = createInitialState();
    this.elapsedAccumulator = 0;

    this.cameras.main.setBackgroundColor(palette.bg);
    this.addGrid();
    this.createWorld();
    this.createHud();
    this.createInput();
  }

  addGrid() {
    const graphics = this.add.graphics();
    graphics.lineStyle(1, 0x222b3d, 0.65);
    for (let x = 0; x <= LEVEL_WIDTH; x += 48) {
      graphics.lineBetween(x, 0, x, LEVEL_HEIGHT);
    }
    for (let y = 0; y <= LEVEL_HEIGHT; y += 48) {
      graphics.lineBetween(0, y, LEVEL_WIDTH, y);
    }
  }

  createWorld() {
    this.platforms = this.physics.add.staticGroup();
    for (const platform of PLATFORMS) {
      const rect = this.add.rectangle(platform.x, platform.y, platform.width, platform.height, palette.platform);
      rect.setStrokeStyle(2, palette.platformEdge);
      this.physics.add.existing(rect, true);
      this.platforms.add(rect);
    }

    this.hazards = this.physics.add.staticGroup();
    for (const hazard of HAZARDS) {
      const spike = this.add.rectangle(hazard.x, hazard.y, hazard.width, hazard.height, palette.hazard);
      spike.setStrokeStyle(2, 0xffb1b1);
      this.physics.add.existing(spike, true);
      this.hazards.add(spike);
    }

    this.driftGraphics = [];
    for (const field of DRIFT_FIELDS) {
      const centerX = field.x + field.width / 2;
      const centerY = field.y + field.height / 2;
      const zone = this.add.rectangle(centerX, centerY, field.width, field.height, field.color, 0.14);
      zone.setStrokeStyle(2, field.color, 0.65);
      this.driftGraphics.push(zone);

      const arrow = field.forceY < -100 ? "UP" : field.forceX < 0 ? "LEFT" : field.forceY > 70 ? "DOWN" : "RIGHT";
      this.add.text(field.x + 8, field.y + 7, `${field.id} ${arrow}`, {
        fontFamily: "Arial, sans-serif",
        fontSize: "13px",
        color: "#eef3ff",
        fontStyle: "700"
      });
    }

    this.exit = this.add.rectangle(
      EXIT_ZONE.x + EXIT_ZONE.width / 2,
      EXIT_ZONE.y + EXIT_ZONE.height / 2,
      EXIT_ZONE.width,
      EXIT_ZONE.height,
      palette.exit,
      0.22
    );
    this.exit.setStrokeStyle(3, palette.exit, 0.95);
    this.add.text(EXIT_ZONE.x - 9, EXIT_ZONE.y - 30, "ZONE Z", {
      fontFamily: "Arial, sans-serif",
      fontSize: "18px",
      color: "#dfff7a",
      fontStyle: "700"
    });

    this.player = this.add.rectangle(PLAYER_START.x, PLAYER_START.y, 30, 38, palette.player);
    this.player.setStrokeStyle(2, 0xe9fff2);
    this.physics.add.existing(this.player);
    this.player.body.setCollideWorldBounds(true);
    this.player.body.setDragX(930);
    this.player.body.setMaxVelocity(245, 520);

    this.physics.add.collider(this.player, this.platforms);
    this.physics.add.overlap(this.player, this.hazards, () => this.fail("Plan burned. Press R."), null, this);

    this.feedCells = this.physics.add.staticGroup();
    for (const cell of FEED_CELLS) {
      const marker = this.add.container(cell.x, cell.y);
      const orb = this.add.circle(0, 0, 14, cell.color, 0.95);
      orb.setStrokeStyle(2, 0x392f0b, 0.55);
      const label = this.add.text(-6, -10, cell.label, {
        fontFamily: "Arial, sans-serif",
        fontSize: "17px",
        color: "#191409",
        fontStyle: "700"
      });
      marker.add([orb, label]);
      marker.cellId = cell.id;
      this.physics.add.existing(marker, true);
      marker.body.setSize(34, 34);
      this.feedCells.add(marker);
    }

    this.physics.add.overlap(this.player, this.feedCells, (_player, marker) => this.takeFeed(marker), null, this);

    this.traceDrones = this.physics.add.group({ allowGravity: false, immovable: true });
    this.droneLabels = [];
    for (const drone of TRACE_DRONES) {
      const position = dronePositionAt(drone, 0);
      const body = this.add.rectangle(position.x, position.y, drone.size, drone.size, 0xffffff, 0.92);
      body.setStrokeStyle(3, 0xff5d5d, 0.95);
      body.droneConfig = drone;
      this.physics.add.existing(body);
      body.body.setAllowGravity(false);
      body.body.setImmovable(true);
      body.body.setSize(drone.size, drone.size);
      this.traceDrones.add(body);

      const label = this.add.text(position.x - 12, position.y - 34, drone.id.toUpperCase(), {
        fontFamily: "Arial, sans-serif",
        fontSize: "12px",
        color: "#ffb1b1",
        fontStyle: "700"
      });
      label.droneTarget = body;
      this.droneLabels.push(label);
    }

    this.physics.add.overlap(this.player, this.traceDrones, () => this.fail("Trace drone caught the feed. Press R."), null, this);

    this.shards = this.physics.add.staticGroup();
    for (const shard of PLAN_SHARDS) {
      const marker = this.add.container(shard.x, shard.y);
      const diamond = this.add.polygon(0, 0, [0, -18, 18, 0, 0, 18, -18, 0], shard.color);
      diamond.setStrokeStyle(2, 0xffffff, 0.8);
      const label = this.add.text(-7, -10, shard.id, {
        fontFamily: "Arial, sans-serif",
        fontSize: "18px",
        color: "#10141f",
        fontStyle: "700"
      });
      marker.add([diamond, label]);
      marker.shardId = shard.id;
      this.physics.add.existing(marker, true);
      marker.body.setSize(42, 42);
      this.shards.add(marker);
    }

    this.physics.add.overlap(this.player, this.shards, (_player, marker) => this.takeShard(marker), null, this);
  }

  createHud() {
    this.hud = this.add.text(18, 16, "", {
      fontFamily: "Arial, sans-serif",
      fontSize: "18px",
      color: palette.ink,
      lineSpacing: 8
    });
    this.status = this.add.text(18, LEVEL_HEIGHT - 70, "", {
      fontFamily: "Arial, sans-serif",
      fontSize: "18px",
      color: palette.muted,
      lineSpacing: 6
    });
    this.result = this.add.text(LEVEL_WIDTH / 2, 78, "", {
      fontFamily: "Arial, sans-serif",
      fontSize: "32px",
      color: "#ffffff",
      fontStyle: "700",
      align: "center"
    });
    this.result.setOrigin(0.5);
    this.refreshHud();
  }

  createInput() {
    this.keys = this.input.keyboard.addKeys({
      left: Phaser.Input.Keyboard.KeyCodes.LEFT,
      right: Phaser.Input.Keyboard.KeyCodes.RIGHT,
      up: Phaser.Input.Keyboard.KeyCodes.UP,
      a: Phaser.Input.Keyboard.KeyCodes.A,
      d: Phaser.Input.Keyboard.KeyCodes.D,
      w: Phaser.Input.Keyboard.KeyCodes.W,
      shift: Phaser.Input.Keyboard.KeyCodes.SHIFT,
      space: Phaser.Input.Keyboard.KeyCodes.SPACE,
      r: Phaser.Input.Keyboard.KeyCodes.R
    });
  }

  update(_time, delta) {
    if (Phaser.Input.Keyboard.JustDown(this.keys.r)) {
      this.scene.restart();
      return;
    }

    if (this.state.won || this.state.failed) {
      this.player.body.setVelocityX(0);
      return;
    }

    this.elapsedAccumulator += delta / 1000;
    if (this.elapsedAccumulator >= 0.25) {
      this.state = tickTimer(this.state, this.elapsedAccumulator);
      this.elapsedAccumulator = 0;
      if (this.state.failed) {
        this.fail("Plan expired. Press R.");
      }
      this.refreshHud();
    }

    const moveLeft = this.keys.left.isDown || this.keys.a.isDown;
    const moveRight = this.keys.right.isDown || this.keys.d.isDown;
    const jump = Phaser.Input.Keyboard.JustDown(this.keys.up) || Phaser.Input.Keyboard.JustDown(this.keys.w);

    if (moveLeft) {
      this.player.body.setAccelerationX(-900);
    } else if (moveRight) {
      this.player.body.setAccelerationX(900);
    } else {
      this.player.body.setAccelerationX(0);
    }

    if (jump && this.player.body.blocked.down) {
      this.player.body.setVelocityY(-385);
    }

    if (this.player.body.blocked.down) {
      const recharged = rechargeZhaBrace(this.state);
      if (recharged.zhaReady !== this.state.zhaReady) {
        this.state = recharged;
        this.refreshHud();
      }
    }

    if (Phaser.Input.Keyboard.JustDown(this.keys.shift)) {
      this.tryZhaBrace();
    }

    this.applyDrift(delta / 1000);
    this.applyAntiZone(delta / 1000);
    this.applyZoneAnchor(delta / 1000);

    if (Phaser.Input.Keyboard.JustDown(this.keys.space)) {
      this.tryTunk();
    }

    this.updateTraceDrones(this.time.now / 1000);
  }

  takeShard(marker) {
    const previous = this.state;
    this.state = collectShard(this.state, marker.shardId);

    if (this.state.failed && !previous.failed) {
      this.fail(`Wrong shard. Needed ${expectedShardId(previous)}. Press R.`);
      return;
    }

    marker.destroy();
    this.cameras.main.flash(110, 255, 246, 190);
    this.refreshHud();
  }

  takeFeed(marker) {
    const previousTime = this.state.timeLeft;
    this.state = collectFeedCell(this.state, marker.cellId);
    marker.destroy();

    if (this.state.timeLeft > previousTime) {
      this.cameras.main.flash(70, 255, 240, 166);
      this.status.setText("Feed cell absorbed. Timer extended.");
      this.refreshHud();
    }
  }

  tryTunk() {
    const bounds = this.playerBounds();
    const nextState = tunk(this.state, bounds, EXIT_ZONE);
    if (nextState.won) {
      this.state = nextState;
      this.exit.setFillStyle(0xffffff, 0.8);
      this.cameras.main.shake(160, 0.006);
      this.result.setText("PLAN Z TUNKED");
      this.status.setText("The gate accepts the completed plan. Press R to run it again.");
      this.refreshHud();
      return;
    }

    this.status.setText(this.state.charged ? "Stand inside Zone Z, then press Space." : "Collect F, J, D before the tunk.");
  }

  fail(message) {
    if (!this.state.won) {
      this.state = { ...this.state, failed: true };
      this.player.setFillStyle(0xff8787);
      this.result.setText("PLAN FAILED");
      this.status.setText(message);
    }
  }

  tryZhaBrace() {
    if (!this.state.zhaReady) {
      this.status.setText("ZHA brace is recharging. Touch ground.");
      return;
    }

    this.state = consumeZhaBrace(this.state);
    this.player.body.setVelocity(this.player.body.velocity.x * 0.18, Math.min(this.player.body.velocity.y * 0.12, 40));
    this.cameras.main.flash(90, 201, 255, 69);
    this.status.setText("ZHA brace spent. Momentum stabilized.");
    this.refreshHud();
  }

  playerBounds() {
    const halfW = this.player.width / 2;
    const halfH = this.player.height / 2;
    return {
      left: this.player.x - halfW,
      right: this.player.x + halfW,
      top: this.player.y - halfH,
      bottom: this.player.y + halfH
    };
  }

  applyDrift(deltaSeconds) {
    const drift = resolveDriftForce(this.playerBounds(), DRIFT_FIELDS);
    if (drift.active.length === 0) {
      return;
    }

    this.player.body.setVelocity(
      Phaser.Math.Clamp(this.player.body.velocity.x + drift.x * deltaSeconds, -285, 285),
      Phaser.Math.Clamp(this.player.body.velocity.y + drift.y * deltaSeconds, -520, 520)
    );
    this.status.setText(`Drift ${drift.active.join("+")} is pushing the route.`);
  }

  applyZoneAnchor(deltaSeconds) {
    const anchor = resolveZoneAnchorForce(this.state, this.playerBounds(), EXIT_ZONE);
    if (!anchor.active) {
      return;
    }

    this.player.body.setVelocity(
      Phaser.Math.Clamp(this.player.body.velocity.x + anchor.x * deltaSeconds, -285, 285),
      Phaser.Math.Clamp(this.player.body.velocity.y + anchor.y * deltaSeconds, -520, 520)
    );
    this.status.setText("ZA anchor is drawing the charged plan into Zone Z.");
  }

  applyAntiZone(deltaSeconds) {
    const antiZone = resolveAntiZoneForce(this.state, this.playerBounds(), EXIT_ZONE);
    if (!antiZone.active) {
      return;
    }

    this.player.body.setVelocity(
      Phaser.Math.Clamp(this.player.body.velocity.x + antiZone.x * deltaSeconds, -285, 285),
      Phaser.Math.Clamp(this.player.body.velocity.y + antiZone.y * deltaSeconds, -520, 520)
    );
    this.status.setText("AZ repulsion rejects an uncharged plan.");
  }

  updateTraceDrones(timeSeconds) {
    for (const drone of this.traceDrones.getChildren()) {
      const position = dronePositionAt(drone.droneConfig, timeSeconds);
      drone.setPosition(position.x, position.y);
      drone.body.updateFromGameObject();
    }

    for (const label of this.droneLabels) {
      label.setPosition(label.droneTarget.x - 12, label.droneTarget.y - 34);
    }
  }

  refreshHud() {
    const next = expectedShardId(this.state);
    const time = Math.ceil(this.state.timeLeft).toString().padStart(2, "0");
    const plan = PLAN_SHARDS.map((shard) => (this.state.collected.includes(shard.id) ? shard.id : "_")).join(" ");
    this.hud.setText(
      `Plan: ${plan}\nNext: ${next ?? "Zone Z"}\nTime: ${time}\nFeed: ${this.state.feedCollected.length}/${FEED_CELLS.length}\nZHA: ${
        this.state.zhaReady ? "Ready" : "Spent"
      }`
    );

    if (!this.state.won && !this.state.failed) {
      this.status.setText(
        this.state.charged
          ? "Core charged. Reach Zone Z and press Space."
          : "Collect the plan shards in order: F, J, D."
      );
    }
  }
}

const config = {
  type: Phaser.AUTO,
  parent: "game",
  width: LEVEL_WIDTH,
  height: LEVEL_HEIGHT,
  backgroundColor: "#10141f",
  physics: {
    default: "arcade",
    arcade: {
      gravity: { y: 880 },
      debug: false
    }
  },
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH
  },
  scene: TunkScene
};

new Phaser.Game(config);
