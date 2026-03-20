const canvas = document.getElementById("game-canvas");
const ctx = canvas.getContext("2d");
const menuPanel = document.getElementById("menu-panel");
const startButton = document.getElementById("start-btn");

const VIEW_W = 960;
const VIEW_H = 540;
const GROUND_Y = 470;
const WORLD_W = 3600;
const FIXED_DT = 1 / 60;

const checkpoints = [80, 900, 1700, 2500, 3150];

const platforms = [
  { x: 280, y: 380, w: 130, h: 12 },
  { x: 640, y: 330, w: 120, h: 12 },
  { x: 1020, y: 390, w: 150, h: 12 },
  { x: 1420, y: 350, w: 120, h: 12 },
  { x: 1840, y: 300, w: 135, h: 12 },
  { x: 2230, y: 370, w: 170, h: 12 },
  { x: 2630, y: 335, w: 120, h: 12 },
  { x: 3020, y: 360, w: 145, h: 12 },
];

const state = {
  mode: "menu",
  score: 0,
  cameraX: 0,
  world: { width: WORLD_W, height: VIEW_H, groundY: GROUND_Y, exitX: WORLD_W - 130 },
  player: null,
  enemies: [],
  bullets: [],
  powerups: [],
  messageTimer: 0,
  jumpHeld: false,
  shootHeld: false,
  pausedBlink: 0,
};

const keys = new Set();

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function aabbOverlap(a, b) {
  return (
    a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y
  );
}

function createPlayer() {
  return {
    x: 84,
    y: GROUND_Y - 58,
    w: 34,
    h: 58,
    vx: 0,
    vy: 0,
    facing: 1,
    onGround: true,
    hp: 5,
    lives: 3,
    invuln: 0,
    shootCooldown: 0,
    checkpoint: 80,
    weaponLevel: 1,
  };
}

function createEnemy(id, x, y) {
  return {
    id,
    x,
    y,
    w: 34,
    h: 48,
    vx: 0,
    hp: id % 3 === 0 ? 2 : 1,
    alive: true,
    patrolMin: x - 90,
    patrolMax: x + 90,
    dir: id % 2 === 0 ? -1 : 1,
    shootCooldown: 1 + (id % 4) * 0.25,
  };
}

function resetMission() {
  state.score = 0;
  state.cameraX = 0;
  state.mode = "playing";
  state.player = createPlayer();
  state.bullets = [];
  state.powerups = [
    { id: "p0", x: 980, y: GROUND_Y - 34, w: 28, h: 34, taken: false },
    { id: "p1", x: 2220, y: GROUND_Y - 34, w: 28, h: 34, taken: false },
  ];
  state.messageTimer = 0;
  state.jumpHeld = false;
  state.shootHeld = false;
  state.pausedBlink = 0;
  state.enemies = [
    createEnemy(0, 540, GROUND_Y - 48),
    createEnemy(1, 850, GROUND_Y - 48),
    createEnemy(2, 1160, GROUND_Y - 48),
    createEnemy(3, 1450, GROUND_Y - 48),
    createEnemy(4, 1770, GROUND_Y - 48),
    createEnemy(5, 2050, GROUND_Y - 48),
    createEnemy(6, 2360, GROUND_Y - 48),
    createEnemy(7, 2700, GROUND_Y - 48),
    createEnemy(8, 3090, GROUND_Y - 48),
    createEnemy(9, 3340, GROUND_Y - 48),
  ];
}

function startMission() {
  resetMission();
  menuPanel.style.display = "none";
}

function showMenu() {
  state.mode = "menu";
  menuPanel.style.display = "grid";
}

function inputDown(code) {
  return keys.has(code);
}

function moveInput() {
  const left = inputDown("ArrowLeft") || inputDown("KeyA");
  const right = inputDown("ArrowRight") || inputDown("KeyD");
  return (right ? 1 : 0) - (left ? 1 : 0);
}

function jumpInput() {
  return inputDown("ArrowUp") || inputDown("KeyW");
}

function shootInput() {
  return inputDown("Space") || inputDown("KeyJ");
}

function damagePlayer(amount) {
  const player = state.player;
  if (!player || player.invuln > 0 || state.mode !== "playing") return;
  player.hp -= amount;
  player.invuln = 1.1;

  if (player.hp > 0) return;
  player.lives -= 1;
  if (player.lives <= 0) {
    state.mode = "gameover";
    state.messageTimer = 0;
    return;
  }

  player.hp = 5;
  player.vx = 0;
  player.vy = 0;
  player.x = player.checkpoint;
  player.y = GROUND_Y - player.h;
  player.invuln = 2.0;
  state.bullets = state.bullets.filter((bullet) => bullet.owner !== "enemy");
}

function spawnPlayerBullet() {
  const player = state.player;
  if (!player) return;
  const originX = player.x + player.w / 2 + player.facing * 15;
  const originY = player.y + player.h * 0.38;
  const level = player.weaponLevel;
  const bullets = [{ dy: 0, vy: 0 }];
  if (level >= 2) bullets.push({ dy: -5, vy: -45 }, { dy: 5, vy: 45 });
  if (level >= 3) bullets.push({ dy: -10, vy: -90 }, { dy: 10, vy: 90 });

  for (const spec of bullets) {
    state.bullets.push({
      owner: "player",
      x: originX,
      y: originY + spec.dy,
      vx: player.facing * 560,
      vy: spec.vy,
      r: 4,
      ttl: 1.0,
    });
  }
}

function spawnEnemyBullet(enemy) {
  const player = state.player;
  if (!player || !enemy.alive) return;
  const facing = player.x >= enemy.x ? 1 : -1;
  state.bullets.push({
    owner: "enemy",
    x: enemy.x + enemy.w / 2,
    y: enemy.y + enemy.h * 0.38,
    vx: facing * 260,
    vy: 0,
    r: 5,
    ttl: 2.2,
  });
}

function updatePlayer(dt) {
  const player = state.player;
  const move = moveInput();
  player.vx = move * 250;
  if (move !== 0) player.facing = move;

  const wantsJump = jumpInput();
  if (wantsJump && player.onGround && !state.jumpHeld) {
    player.vy = -490;
    player.onGround = false;
  }
  state.jumpHeld = wantsJump;

  const wantsShoot = shootInput();
  if (wantsShoot && !state.shootHeld && player.shootCooldown <= 0) {
    spawnPlayerBullet();
    player.shootCooldown = player.weaponLevel >= 2 ? 0.11 : 0.14;
  }
  state.shootHeld = wantsShoot;

  player.shootCooldown = Math.max(0, player.shootCooldown - dt);
  player.invuln = Math.max(0, player.invuln - dt);

  player.vy += 1180 * dt;
  player.x += player.vx * dt;
  player.y += player.vy * dt;

  player.x = clamp(player.x, 0, WORLD_W - player.w);

  player.onGround = false;
  if (player.y + player.h >= GROUND_Y) {
    player.y = GROUND_Y - player.h;
    player.vy = 0;
    player.onGround = true;
  }

  for (const platform of platforms) {
    const playerBottom = player.y + player.h;
    const playerPrevBottom = playerBottom - player.vy * dt;
    const overlapX = player.x + player.w > platform.x && player.x < platform.x + platform.w;
    if (!overlapX) continue;
    if (player.vy >= 0 && playerPrevBottom <= platform.y && playerBottom >= platform.y) {
      player.y = platform.y - player.h;
      player.vy = 0;
      player.onGround = true;
    }
  }

  for (let i = checkpoints.length - 1; i >= 0; i -= 1) {
    if (player.x >= checkpoints[i]) {
      player.checkpoint = checkpoints[i];
      break;
    }
  }

  if (player.x >= state.world.exitX) {
    state.mode = "win";
    state.messageTimer = 0;
  }

  for (const powerup of state.powerups) {
    if (powerup.taken) continue;
    if (aabbOverlap(player, powerup)) {
      powerup.taken = true;
      player.weaponLevel = Math.min(3, player.weaponLevel + 1);
      state.score += 80;
    }
  }
}

function updateEnemies(dt) {
  const player = state.player;
  for (const enemy of state.enemies) {
    if (!enemy.alive) continue;

    enemy.vx = enemy.dir * 65;
    enemy.x += enemy.vx * dt;

    if (enemy.x <= enemy.patrolMin) enemy.dir = 1;
    if (enemy.x >= enemy.patrolMax) enemy.dir = -1;
    enemy.x = clamp(enemy.x, 0, WORLD_W - enemy.w);

    enemy.shootCooldown -= dt;
    const seesPlayer = Math.abs(player.x - enemy.x) < 300 && Math.abs(player.y - enemy.y) < 80;
    if (enemy.shootCooldown <= 0 && seesPlayer) {
      spawnEnemyBullet(enemy);
      enemy.shootCooldown = 1.1 + (enemy.id % 3) * 0.35;
    }

    if (aabbOverlap(player, enemy)) {
      damagePlayer(1);
    }
  }
}

function updateBullets(dt) {
  const player = state.player;
  for (const bullet of state.bullets) {
    bullet.ttl -= dt;
    bullet.x += bullet.vx * dt;
    bullet.y += bullet.vy * dt;

    if (bullet.owner === "player") {
      for (const enemy of state.enemies) {
        if (!enemy.alive) continue;
        if (
          bullet.x + bullet.r > enemy.x &&
          bullet.x - bullet.r < enemy.x + enemy.w &&
          bullet.y + bullet.r > enemy.y &&
          bullet.y - bullet.r < enemy.y + enemy.h
        ) {
          bullet.ttl = 0;
          enemy.hp -= 1;
          if (enemy.hp <= 0) {
            enemy.alive = false;
            state.score += 120;
          }
          break;
        }
      }
    } else if (bullet.owner === "enemy") {
      const hitPlayer =
        bullet.x + bullet.r > player.x &&
        bullet.x - bullet.r < player.x + player.w &&
        bullet.y + bullet.r > player.y &&
        bullet.y - bullet.r < player.y + player.h;
      if (hitPlayer) {
        bullet.ttl = 0;
        damagePlayer(1);
      }
    }
  }

  state.bullets = state.bullets.filter((bullet) => {
    if (bullet.ttl <= 0) return false;
    if (bullet.x < -80 || bullet.x > WORLD_W + 80) return false;
    return true;
  });
}

function updateWorld(dt) {
  if (state.mode !== "playing") {
    state.messageTimer += dt;
    return;
  }

  updatePlayer(dt);
  updateEnemies(dt);
  updateBullets(dt);

  state.cameraX = clamp(state.player.x - VIEW_W * 0.35, 0, WORLD_W - VIEW_W);
  state.pausedBlink += dt;
}

function drawBackground() {
  const gradient = ctx.createLinearGradient(0, 0, 0, VIEW_H);
  gradient.addColorStop(0, "#76b5ff");
  gradient.addColorStop(0.6, "#4d90d9");
  gradient.addColorStop(1, "#285d96");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, VIEW_W, VIEW_H);

  const offsetFar = state.cameraX * 0.15;
  const offsetNear = state.cameraX * 0.35;

  ctx.fillStyle = "rgba(30, 74, 118, 0.65)";
  for (let i = 0; i < 8; i += 1) {
    const x = ((i * 240 - offsetFar) % (VIEW_W + 300)) - 120;
    ctx.beginPath();
    ctx.moveTo(x, 370);
    ctx.lineTo(x + 90, 240);
    ctx.lineTo(x + 240, 370);
    ctx.closePath();
    ctx.fill();
  }

  ctx.fillStyle = "rgba(38, 110, 146, 0.6)";
  for (let i = 0; i < 9; i += 1) {
    const x = ((i * 190 - offsetNear) % (VIEW_W + 260)) - 80;
    ctx.beginPath();
    ctx.moveTo(x, 400);
    ctx.lineTo(x + 60, 315);
    ctx.lineTo(x + 170, 400);
    ctx.closePath();
    ctx.fill();
  }
}

function drawGround() {
  const cameraX = state.cameraX;
  ctx.fillStyle = "#6f4e2f";
  ctx.fillRect(0, GROUND_Y, VIEW_W, VIEW_H - GROUND_Y);
  ctx.fillStyle = "#5fa24f";
  ctx.fillRect(0, GROUND_Y - 18, VIEW_W, 18);

  ctx.fillStyle = "#8e6d4a";
  for (let i = 0; i < 35; i += 1) {
    const x = (i * 120 - (cameraX % 120)) - 10;
    ctx.fillRect(x, GROUND_Y + 25, 70, 6);
  }
}

function drawPlatforms() {
  for (const platform of platforms) {
    const sx = platform.x - state.cameraX;
    if (sx + platform.w < -20 || sx > VIEW_W + 20) continue;
    ctx.fillStyle = "#4d3a28";
    ctx.fillRect(sx, platform.y, platform.w, platform.h);
    ctx.fillStyle = "#7fcf63";
    ctx.fillRect(sx, platform.y - 5, platform.w, 5);
  }
}

function drawExitBeacon() {
  const x = state.world.exitX - state.cameraX;
  if (x < -100 || x > VIEW_W + 100) return;
  ctx.fillStyle = "#2f2f2f";
  ctx.fillRect(x - 14, GROUND_Y - 128, 28, 128);
  ctx.fillStyle = "#ffd34b";
  ctx.beginPath();
  ctx.arc(x, GROUND_Y - 138, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 211, 75, 0.25)";
  ctx.beginPath();
  ctx.arc(x, GROUND_Y - 138, 34, 0, Math.PI * 2);
  ctx.fill();
}

function drawPlayer() {
  const p = state.player;
  const sx = p.x - state.cameraX;
  const flashing = p.invuln > 0 && Math.floor(p.invuln * 12) % 2 === 0;
  if (flashing) {
    ctx.save();
    ctx.globalAlpha = 0.35;
  }

  ctx.fillStyle = "#102032";
  ctx.fillRect(sx + 6, p.y + 10, p.w - 12, p.h - 10);
  ctx.fillStyle = "#ffcc89";
  ctx.fillRect(sx + 8, p.y + 2, p.w - 16, 14);
  ctx.fillStyle = "#54c6ff";
  ctx.fillRect(sx + (p.facing > 0 ? 20 : 4), p.y + 25, 14, 8);
  ctx.fillStyle = "#203046";
  ctx.fillRect(sx + 7, p.y + 42, 8, 14);
  ctx.fillRect(sx + p.w - 15, p.y + 42, 8, 14);
  if (flashing) ctx.restore();
}

function drawEnemies() {
  for (const enemy of state.enemies) {
    if (!enemy.alive) continue;
    const sx = enemy.x - state.cameraX;
    if (sx + enemy.w < -30 || sx > VIEW_W + 30) continue;
    ctx.fillStyle = "#5d2222";
    ctx.fillRect(sx + 4, enemy.y + 8, enemy.w - 8, enemy.h - 8);
    ctx.fillStyle = "#ffd8a5";
    ctx.fillRect(sx + 9, enemy.y + 2, enemy.w - 18, 12);
    ctx.fillStyle = "#ff5d5d";
    ctx.fillRect(sx + 10, enemy.y + 23, enemy.w - 20, 5);
  }
}

function drawBullets() {
  for (const bullet of state.bullets) {
    const sx = bullet.x - state.cameraX;
    if (sx < -40 || sx > VIEW_W + 40) continue;
    ctx.fillStyle = bullet.owner === "player" ? "#ffd34b" : "#ff7a5f";
    ctx.beginPath();
    ctx.arc(sx, bullet.y, bullet.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawPowerups() {
  for (const powerup of state.powerups) {
    if (powerup.taken) continue;
    const sx = powerup.x - state.cameraX;
    if (sx + powerup.w < -20 || sx > VIEW_W + 20) continue;
    ctx.fillStyle = "#2a2435";
    ctx.fillRect(sx, powerup.y, powerup.w, powerup.h);
    ctx.fillStyle = "#ffdf61";
    ctx.fillRect(sx + 6, powerup.y + 6, powerup.w - 12, powerup.h - 12);
    ctx.fillStyle = "#20252f";
    ctx.fillRect(sx + 11, powerup.y + 14, powerup.w - 22, powerup.h - 20);
  }
}

function drawHud() {
  const p = state.player;
  ctx.fillStyle = "rgba(5, 15, 28, 0.55)";
  ctx.fillRect(12, 10, 300, 74);
  ctx.fillStyle = "#f4fbff";
  ctx.font = "18px Trebuchet MS, sans-serif";
  ctx.fillText(`HP ${p.hp}   LIVES ${p.lives}   SCORE ${state.score}`, 24, 36);
  ctx.fillStyle = "#d6e8f6";
  ctx.font = "14px Trebuchet MS, sans-serif";
  ctx.fillText(`ENEMIES ${state.enemies.filter((enemy) => enemy.alive).length}`, 24, 59);
  ctx.fillText(`X ${(p.x + p.w / 2).toFixed(0)} / ${WORLD_W}   WPN ${p.weaponLevel}`, 24, 77);
}

function drawModeOverlay() {
  if (state.mode === "paused") {
    if (Math.floor(state.pausedBlink * 3) % 2 === 0) return;
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(0, 0, VIEW_W, VIEW_H);
    ctx.fillStyle = "#f4fcff";
    ctx.font = "bold 44px Trebuchet MS, sans-serif";
    ctx.fillText("PAUSED", VIEW_W / 2 - 95, VIEW_H / 2 - 20);
    ctx.font = "20px Trebuchet MS, sans-serif";
    ctx.fillText("按 P/B 继续", VIEW_W / 2 - 72, VIEW_H / 2 + 16);
    return;
  }

  if (state.mode === "gameover" || state.mode === "win") {
    ctx.fillStyle = "rgba(0,0,0,0.58)";
    ctx.fillRect(0, 0, VIEW_W, VIEW_H);
    ctx.fillStyle = state.mode === "win" ? "#ffe06c" : "#ff8f8f";
    ctx.font = "bold 48px Trebuchet MS, sans-serif";
    ctx.fillText(state.mode === "win" ? "MISSION CLEAR" : "MISSION FAILED", VIEW_W / 2 - 190, VIEW_H / 2 - 10);
    ctx.fillStyle = "#f2f8ff";
    ctx.font = "22px Trebuchet MS, sans-serif";
    ctx.fillText("按 R 重新开始", VIEW_W / 2 - 82, VIEW_H / 2 + 34);
  }
}

function drawMenuBackground() {
  drawBackground();
  drawGround();
  drawPlatforms();
  drawExitBeacon();
  ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
  ctx.fillRect(0, 0, VIEW_W, VIEW_H);
}

function drawMenuOverlay() {
  ctx.fillStyle = "rgba(5, 18, 34, 0.68)";
  ctx.fillRect(180, 80, 600, 320);
  ctx.strokeStyle = "rgba(120, 212, 255, 0.8)";
  ctx.lineWidth = 2;
  ctx.strokeRect(180, 80, 600, 320);

  ctx.fillStyle = "#f0f8ff";
  ctx.font = "bold 56px Trebuchet MS, sans-serif";
  ctx.fillText("STEEL FALCON", 255, 154);
  ctx.fillStyle = "#9be4ff";
  ctx.font = "22px Trebuchet MS, sans-serif";
  ctx.fillText("横版突击射击", 402, 188);

  ctx.fillStyle = "#d9f4ff";
  ctx.font = "19px Trebuchet MS, sans-serif";
  ctx.fillText("MOVE: LEFT/RIGHT or A/D", 260, 242);
  ctx.fillText("JUMP: UP or W", 260, 274);
  ctx.fillText("SHOOT: SPACE or J", 260, 306);
  ctx.fillText("PAUSE: P or B    FULLSCREEN: F", 260, 338);
  ctx.fillText("Press ENTER or click start button", 260, 370);
}

function render() {
  if (state.mode === "menu") {
    drawMenuBackground();
    drawMenuOverlay();
    return;
  }
  drawBackground();
  drawGround();
  drawPlatforms();
  drawExitBeacon();
  drawEnemies();
  drawPowerups();
  drawBullets();
  drawPlayer();
  drawHud();
  drawModeOverlay();
}

function togglePause() {
  if (state.mode === "playing") {
    state.mode = "paused";
    if (state.player) state.player.vx = 0;
  } else if (state.mode === "paused") {
    state.mode = "playing";
  }
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
  } catch (err) {
    console.error("fullscreen failed", err);
  }
}

function updateCanvasScale() {
  const margin = 24;
  const maxW = window.innerWidth - margin;
  const maxH = window.innerHeight - margin;
  const scale = Math.min(maxW / VIEW_W, maxH / VIEW_H);
  const width = Math.floor(VIEW_W * scale);
  const height = Math.floor(VIEW_H * scale);
  canvas.style.width = `${Math.max(320, width)}px`;
  canvas.style.height = `${Math.max(180, height)}px`;
}

function renderGameToText() {
  const p = state.player ?? createPlayer();
  const visibleEnemies = state.enemies
    .filter((enemy) => enemy.alive)
    .map((enemy) => ({
      id: enemy.id,
      x: Number(enemy.x.toFixed(1)),
      y: Number(enemy.y.toFixed(1)),
      hp: enemy.hp,
      vx: Number(enemy.vx.toFixed(1)),
    }));
  const bullets = state.bullets.map((bullet) => ({
    owner: bullet.owner,
    x: Number(bullet.x.toFixed(1)),
    y: Number(bullet.y.toFixed(1)),
    vx: Number(bullet.vx.toFixed(1)),
    ttl: Number(bullet.ttl.toFixed(2)),
  }));
  const activePowerups = state.powerups
    .filter((powerup) => !powerup.taken)
    .map((powerup) => ({
      id: powerup.id,
      x: Number(powerup.x.toFixed(1)),
      y: Number(powerup.y.toFixed(1)),
    }));

  return JSON.stringify({
    coordinateSystem: "origin=(0,0) at top-left; +x right; +y down",
    mode: state.mode,
    world: {
      width: state.world.width,
      height: state.world.height,
      groundY: state.world.groundY,
      exitX: state.world.exitX,
      cameraX: Number(state.cameraX.toFixed(1)),
    },
    player: {
      x: Number(p.x.toFixed(1)),
      y: Number(p.y.toFixed(1)),
      vx: Number(p.vx.toFixed(1)),
      vy: Number(p.vy.toFixed(1)),
      width: p.w,
      height: p.h,
      facing: p.facing,
      hp: p.hp,
      lives: p.lives,
      onGround: p.onGround,
      shootCooldown: Number(p.shootCooldown.toFixed(2)),
      invuln: Number(p.invuln.toFixed(2)),
      checkpoint: p.checkpoint,
      weaponLevel: p.weaponLevel,
    },
    score: state.score,
    enemiesAlive: visibleEnemies.length,
    enemies: visibleEnemies,
    powerups: activePowerups,
    bullets,
    fullscreen: Boolean(document.fullscreenElement),
    controls: {
      move: ["ArrowLeft", "ArrowRight", "KeyA", "KeyD"],
      jump: ["ArrowUp", "KeyW"],
      shoot: ["Space", "KeyJ"],
      pause: "KeyP",
      pauseAlt: "KeyB",
      restart: "KeyR or Enter(on win/gameover)",
      fullscreen: "KeyF",
    },
  });
}

window.render_game_to_text = renderGameToText;
window.advanceTime = (ms) => {
  const steps = Math.max(1, Math.round(ms / (1000 / 60)));
  for (let i = 0; i < steps; i += 1) {
    updateWorld(FIXED_DT);
  }
  render();
};

let last = performance.now();
let accumulator = 0;

function animationFrame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;

  if (typeof window.__vt_pending === "undefined") {
    accumulator += dt;
    while (accumulator >= FIXED_DT) {
      updateWorld(FIXED_DT);
      accumulator -= FIXED_DT;
    }
  }

  render();
  requestAnimationFrame(animationFrame);
}

startButton.addEventListener("click", startMission);

window.addEventListener("keydown", (event) => {
  keys.add(event.code);

  if (event.code === "Enter" && state.mode === "menu") {
    startMission();
  } else if ((event.code === "KeyP" || event.code === "KeyB") && !event.repeat && state.mode !== "menu" && state.mode !== "gameover" && state.mode !== "win") {
    togglePause();
  } else if ((event.code === "KeyR" || event.code === "Enter") && !event.repeat && (state.mode === "gameover" || state.mode === "win")) {
    resetMission();
  } else if (event.code === "KeyF" && !event.repeat) {
    toggleFullscreen();
  }
});

window.addEventListener("keyup", (event) => {
  keys.delete(event.code);
});

window.addEventListener("resize", updateCanvasScale);
document.addEventListener("fullscreenchange", updateCanvasScale);

showMenu();
updateCanvasScale();
requestAnimationFrame(animationFrame);
