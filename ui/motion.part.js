/* ============================================================
   Motion: particles, cursor, tilt, magnetic
   ============================================================ */
const particles = {
  canvas: null,
  ctx: null,
  w: 0, h: 0, dpr: 1,
  parts: [],
  target: 0,
  rgb: [10, 132, 255],
  running: false,
  init() {
    this.canvas = $('#particles');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    this.setCount(S.cfg?.particles === false ? 0 : (S.cfg?.particle_density ?? 70));
    this.setPalette();
    if (!this.running) {
      this.running = true;
      requestAnimationFrame((t) => this.tick(t));
    }
  },
  resize() {
    if (!this.canvas) return;
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = window.innerWidth;
    this.h = window.innerHeight;
    this.canvas.width = Math.round(this.w * this.dpr);
    this.canvas.height = Math.round(this.h * this.dpr);
    this.canvas.style.width = `${this.w}px`;
    this.canvas.style.height = `${this.h}px`;
    if (this.ctx) this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  },
  setPalette() {
    const base = ACCENT_COLORS[S.accent] || ACCENT_COLORS.blue;
    this.rgb = S.theme === 'light' ? base.map(v => Math.round(v * .82)) : base;
    this.drawStatic();
  },
  setCount(n) {
    const want = clamp(Math.round(Number(n) || 0), 0, 180);
    this.target = want;
    if (!this.canvas) return;
    const scaled = Math.round(want * (Math.min(1, (window.innerWidth * window.innerHeight) / (1600 * 900)) * .65 + .35));
    const finalN = Math.min(180, Math.max(want ? 1 : 0, scaled));
    while (this.parts.length < finalN) this.parts.push(this.spawn(true));
    if (this.parts.length > finalN) this.parts.length = finalN;
    this.drawStatic();
  },
  spawn(initial = false) {
    return {
      x: Math.random() * this.w,
      y: Math.random() * this.h,
      vx: (Math.random() - .5) * .18,
      vy: (Math.random() - .5) * .18,
      r: Math.random() * 1.5 + .35,
      a: Math.random() * .55 + .12,
      pulse: Math.random() * Math.PI * 2,
      speed: Math.random() * .012 + .004,
    };
  },
  burst(x, y, count = 8) {
    if (!this.parts.length) return;
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2;
      const s = Math.random() * 1.6 + .4;
      this.parts.push({
        x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s,
        r: Math.random() * 1.7 + .6, a: .7, pulse: Math.random() * 6, speed: .02, life: 1
      });
      if (this.parts.length > 210) this.parts.shift();
    }
  },
  tick(t) {
    requestAnimationFrame((tt) => this.tick(tt));
    if (S.reduce) { this.drawStatic(); return; }
    const ctx = this.ctx;
    if (!ctx) return;
    ctx.clearRect(0, 0, this.w, this.h);
    const [r, g, b] = this.rgb;
    const mouse = S.mouse;
    const active = mouse.active;
    const parts = this.parts;

    for (const p of parts) {
      p.x += p.vx;
      p.y += p.vy;
      p.pulse += p.speed;
      if (p.life !== undefined) p.life -= .025;
      if (p.x < -20) p.x = this.w + 20;
      if (p.x > this.w + 20) p.x = -20;
      if (p.y < -20) p.y = this.h + 20;
      if (p.y > this.h + 20) p.y = -20;
      if (active) {
        const dx = p.x - mouse.cx, dy = p.y - mouse.cy;
        const d2 = dx * dx + dy * dy;
        if (d2 < 150 * 150 && d2 > 1) {
          const d = Math.sqrt(d2);
          const f = (150 - d) / 150 * .55;
          p.x += dx / d * f;
          p.y += dy / d * f;
        }
      }
    }
    for (let i = parts.length - 1; i >= 0; i--) if (parts[i].life !== undefined && parts[i].life <= 0) parts.splice(i, 1);
    while (parts.length < Math.min(180, this.target)) parts.push(this.spawn());

    ctx.lineWidth = .6;
    for (let i = 0; i < parts.length; i++) {
      const a = parts[i];
      for (let j = i + 1; j < parts.length; j++) {
        const c = parts[j];
        const dx = a.x - c.x, dy = a.y - c.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 85 * 85) {
          const alpha = (1 - Math.sqrt(d2) / 85) * .16;
          ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(c.x, c.y); ctx.stroke();
        }
      }
      if (active) {
        const dx = a.x - mouse.cx, dy = a.y - mouse.cy;
        const d2 = dx * dx + dy * dy;
        if (d2 < 170 * 170) {
          const alpha = (1 - Math.sqrt(d2) / 170) * .26;
          ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.cx, mouse.cy); ctx.stroke();
        }
      }
    }
    for (const p of parts) {
      const twinkle = .55 + Math.sin(p.pulse) * .45;
      ctx.fillStyle = `rgba(${r},${g},${b},${p.a * twinkle})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      if (p.r > 1.1) {
        ctx.fillStyle = `rgba(255,255,255,${p.a * .35})`;
        ctx.beginPath(); ctx.arc(p.x - p.r * .3, p.y - p.r * .3, p.r * .35, 0, Math.PI * 2); ctx.fill();
      }
    }
    if (active) {
      const grad = ctx.createRadialGradient(mouse.cx, mouse.cy, 0, mouse.cx, mouse.cy, 130);
      grad.addColorStop(0, `rgba(${r},${g},${b},.055)`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(mouse.cx, mouse.cy, 130, 0, Math.PI * 2); ctx.fill();
    }
  },
  drawStatic() {
    const ctx = this.ctx;
    if (!ctx) return;
    ctx.clearRect(0, 0, this.w, this.h);
    const [r, g, b] = this.rgb;
    for (const p of this.parts) {
      ctx.fillStyle = `rgba(${r},${g},${b},${p.a * .6})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
    }
  }
};

function initMotion() {
  particles.init();
  const glow = $('#cursorGlow');

  const motionLoop = () => {
    if (glow && !S.reduce) {
      S.mouse.cx += (S.mouse.x - S.mouse.cx) * .18;
      S.mouse.cy += (S.mouse.y - S.mouse.cy) * .18;
      glow.style.transform = `translate(${S.mouse.cx}px, ${S.mouse.cy}px) translate(-50%, -50%)`;
      glow.style.opacity = S.mouse.active ? '1' : '0';
    }
    requestAnimationFrame(motionLoop);
  };
  requestAnimationFrame(motionLoop);

  document.addEventListener('pointermove', (e) => {
    S.mouse.x = e.clientX; S.mouse.y = e.clientY; S.mouse.active = true;
    if (S.reduce) return;

    const card = e.target.closest('.card, .stat-card, .tip-card, .principle-card, .phone-feature');
    if (card) {
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`);
      card.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`);
    }

    const tilt = e.target.closest('.tilt');
    if (tilt !== S.tiltEl) {
      if (S.tiltEl) { S.tiltEl.style.setProperty('--rx', '0deg'); S.tiltEl.style.setProperty('--ry', '0deg'); S.tiltEl.style.setProperty('--lift', '0px'); }
      S.tiltEl = tilt;
    }
    if (tilt) {
      const rect = tilt.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - .5;
      const py = (e.clientY - rect.top) / rect.height - .5;
      tilt.style.setProperty('--rx', `${(-py * 4.5).toFixed(2)}deg`);
      tilt.style.setProperty('--ry', `${(px * 5.5).toFixed(2)}deg`);
    }

    const mag = e.target.closest('.magnetic');
    if (mag !== S.magEl) {
      if (S.magEl) { S.magEl.style.setProperty('--mag-x', '0px'); S.magEl.style.setProperty('--mag-y', '0px'); }
      S.magEl = mag;
    }
    if (mag) {
      const rect = mag.getBoundingClientRect();
      const dx = (e.clientX - (rect.left + rect.width / 2)) / rect.width;
      const dy = (e.clientY - (rect.top + rect.height / 2)) / rect.height;
      mag.style.setProperty('--mag-x', `${clamp(dx * 7, -6, 6).toFixed(2)}px`);
      mag.style.setProperty('--mag-y', `${clamp(dy * 6, -5, 5).toFixed(2)}px`);
    }
  });

  document.addEventListener('pointerleave', () => {
    S.mouse.active = false;
    if (S.tiltEl) { S.tiltEl.style.setProperty('--rx', '0deg'); S.tiltEl.style.setProperty('--ry', '0deg'); }
    if (S.magEl) { S.magEl.style.setProperty('--mag-x', '0px'); S.magEl.style.setProperty('--mag-y', '0px'); }
  });

  document.addEventListener('pointerdown', (e) => {
    if (S.reduce || e.button !== 0) return;
    particles.burst(e.clientX, e.clientY, 5);
  });

  const stage = $('.hero-stage');
  const orbWrap = $('#orbWrap');
  stage?.addEventListener('pointermove', (e) => {
    if (S.reduce || !orbWrap) return;
    const r = stage.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - .5;
    const y = (e.clientY - r.top) / r.height - .5;
    orbWrap.style.transform = `rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 8).toFixed(2)}deg)`;
  });
  stage?.addEventListener('pointerleave', () => { if (orbWrap) orbWrap.style.transform = ''; });
}

/* ============================================================
   Canvas: orb waveform + voice visualizer
   ============================================================ */
let drawStarted = false;
function startDrawLoops() {
  if (drawStarted) return;
  drawStarted = true;
  requestAnimationFrame(orbLoop);
  requestAnimationFrame(voiceLoop);
}

function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#0a84ff';
}
function hexRGB(hex) {
  const h = (hex || '').replace('#', '');
  if (h.length === 3) return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)];
  if (h.length >= 6) return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  return [10, 132, 255];
}
function sizeCanvas(canvas, cssW, cssH) {
  if (!canvas) return false;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(cssW * dpr));
  const h = Math.max(1, Math.round(cssH * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w; canvas.height = h;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return true;
}

let orbT = 0;
function orbLoop(t) {
  requestAnimationFrame(orbLoop);
  const canvas = $('#orbWave');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2) return;
  if (!sizeCanvas(canvas, rect.width, rect.height)) return;
  const ctx = canvas.getContext('2d');
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);
  orbT += .04;
  const accent = hexRGB(cssColor('--accent'));
  const active = !!(S.state?.running || S.state?.asr?.running || ['listening','transcribing'].includes(S.state?.asr?.status));
  const levels = S.levels || [];
  const gradient = ctx.createLinearGradient(0, 0, w, 0);
  gradient.addColorStop(0, `rgba(${accent[0]},${accent[1]},${accent[2]},.12)`);
  gradient.addColorStop(.35, `rgba(${accent[0]},${accent[1]},${accent[2]},.85)`);
  gradient.addColorStop(.65, `rgba(255,255,255,.8)`);
  gradient.addColorStop(1, `rgba(${accent[0]},${accent[1]},${accent[2]},.12)`);

  ctx.globalCompositeOperation = 'lighter';
  for (let layer = 0; layer < 3; layer++) {
    ctx.beginPath();
    for (let x = 0; x <= w; x += 2) {
      const p = x / w;
      let v = 0;
      if (levels.length) {
        const idx = Math.floor((p * (levels.length - 1)) + layer * 4) % levels.length;
        v = levels[idx] || 0;
      }
      const envelope = Math.sin(p * Math.PI);
      const idle = Math.sin(p * 9 + orbT * 2 + layer * 1.5) * .12 + Math.sin(p * 17 - orbT * 3) * .05;
      const amp = (active ? 15 : 6) * envelope;
      const y = h / 2 + (active ? (v - .5) * amp * 2.2 : idle * amp) + Math.sin(p * 6 + orbT + layer) * 1.4;
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle = layer === 0 ? gradient : `rgba(255,255,255,${.05 - layer * .012})`;
    ctx.lineWidth = layer === 0 ? 1.6 : .8;
    ctx.shadowBlur = layer === 0 ? 14 : 0;
    ctx.shadowColor = `rgba(${accent[0]},${accent[1]},${accent[2]},.55)`;
    ctx.stroke();
  }
  ctx.shadowBlur = 0;
  ctx.globalCompositeOperation = 'source-over';
}

function resizeVoiceCanvas() {
  const canvas = $('#voiceCanvas');
  if (!canvas) return;
  const parent = canvas.parentElement;
  const rect = parent.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;
  if (!sizeCanvas(canvas, rect.width, rect.height)) return;
}

let voiceT = 0;
function voiceLoop(t) {
  requestAnimationFrame(voiceLoop);
  if (S.page !== 'voice') return;
  const canvas = $('#voiceCanvas');
  if (!canvas) return;
  resizeVoiceCanvas();
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 10) return;
  const ctx = canvas.getContext('2d');
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);
  voiceT += .016;
  const accent = hexRGB(cssColor('--accent'));
  const active = !!(S.state?.asr?.running || ['listening','transcribing','preparing'].includes(S.state?.asr?.status));
  const levels = S.levels || [];
  const cx = w / 2 + (S.mouse.active ? clamp((S.mouse.cx - w / 2) / w, -.5, .5) * 10 : 0);
  const cy = h / 2 + (S.mouse.active ? clamp((S.mouse.cy - h / 2) / h, -.5, .5) * 8 : 0);
  const maxR = Math.min(w, h) * .42;
  const baseR = maxR * .45;

  const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 1.5);
  bg.addColorStop(0, `rgba(${accent[0]},${accent[1]},${accent[2]},${active ? .16 : .07})`);
  bg.addColorStop(.6, `rgba(${accent[0]},${accent[1]},${accent[2]},.03)`);
  bg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = bg;
  ctx.beginPath(); ctx.arc(cx, cy, maxR * 1.5, 0, Math.PI * 2); ctx.fill();

  for (let ring = 0; ring < 3; ring++) {
    const rr = baseR + ring * 24 + (active ? Math.sin(voiceT * 1.4 + ring) * 3 : 0);
    ctx.strokeStyle = `rgba(${accent[0]},${accent[1]},${accent[2]},${.13 - ring * .028})`;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
  }

  const n = Math.max(32, levels.length || 48);
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const v = levels.length ? (levels[i % levels.length] || 0) : (active ? .2 + Math.abs(Math.sin(i * .5 + voiceT * 3)) * .35 : .08 + Math.sin(i * .3 + voiceT) * .04);
    const len = 10 + v * (maxR - baseR - 26) * 1.55;
    const inner = baseR + 8;
    const outer = inner + len;
    const x1 = cx + Math.cos(angle) * inner;
    const y1 = cy + Math.sin(angle) * inner;
    const x2 = cx + Math.cos(angle) * outer;
    const y2 = cy + Math.sin(angle) * outer;
    const alpha = .18 + v * .7;
    ctx.strokeStyle = `rgba(${accent[0]},${accent[1]},${accent[2]},${alpha})`;
    ctx.lineWidth = i % 4 === 0 ? 1.6 : .8;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    if (v > .3) {
      ctx.fillStyle = `rgba(255,255,255,${v * .28})`;
      ctx.beginPath(); ctx.arc(x2, y2, i % 3 === 0 ? 1.5 : .8, 0, Math.PI * 2); ctx.fill();
    }
  }

  const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * .8);
  core.addColorStop(0, `rgba(255,255,255,${active ? .14 : .05})`);
  core.addColorStop(1, `rgba(${accent[0]},${accent[1]},${accent[2]},0)`);
  ctx.fillStyle = core;
  ctx.beginPath(); ctx.arc(cx, cy, baseR * .8, 0, Math.PI * 2); ctx.fill();
}
