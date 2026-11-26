/* ============================================================
   Lingua Studio — UI controller
   pywebview bridge + state polling + motion system
   ============================================================ */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const LANG_SHORT = {
  en: 'EN', ja: 'JA', ko: 'KO', ru: 'RU', de: 'DE', fr: 'FR', es: 'ES',
  pt: 'PT', it: 'IT', zh: '中', tr: 'TR', ar: 'AR', vi: 'VI', th: 'TH',
  unknown: '??'
};
const LANG_FULL = {
  en: 'English', ja: '日本語', ko: '한국어', ru: 'Русский', de: 'Deutsch',
  fr: 'Français', es: 'Español', pt: 'Português', it: 'Italiano', zh: '中文',
  tr: 'Türkçe', ar: 'العربية', vi: 'Tiếng Việt', th: 'ไทย', unknown: '未知'
};
const ENGINE_LABEL = {
  free: '免费在线', qwen: '通义千问', deepl: 'DeepL', argos: 'Argos 离线', mock: '演示模式'
};
const SOURCE_LABEL = { ocr: '屏幕', asr: '语音', manual: '手动', retry: '重译' };
const ACCENT_COLORS = {
  blue: [10, 132, 255], mint: [48, 209, 88], amber: [255, 159, 10], graphite: [142, 142, 147]
};

const S = {
  ready: false,
  cfg: null,
  state: null,
  subs: [],
  logs: [],
  devices: [],
  models: {},
  constants: { ocr_langs: {}, asr_models: {}, target_langs: {} },
  app: null,
  phone: null,
  page: 'overview',
  filter: 'all',
  subCursor: 0,
  logCursor: 0,
  levels: [],
  levelStatus: null,
  polling: false,
  pendingCfg: {},
  saveTimer: 0,
  regionShot: null,
  selection: null,
  ocrBoxes: [],
  asrLevelBusy: false,
  cmdIndex: 0,
  cmdItems: [],
  previewMode: false,
  booted: false,
  lastSub: null,
  lastLang: 'unknown',
  statValues: {},
  lastStatAt: 0,
  lastPushed: 0,
  theme: 'dark',
  accent: 'blue',
  reduce: false,
  particleCount: 70,
  tiltEl: null,
  magEl: null,
  mouse: { x: innerWidth / 2, y: innerHeight / 2, cx: innerWidth / 2, cy: innerHeight / 2, active: false },
};

/* ============================================================
   Utilities
   ============================================================ */
function esc(s) { return String(s ?? ''); }
function pad(n) { return String(n).padStart(2, '0'); }
function clock(ts) {
  const d = new Date(ts || Date.now());
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function shortClock(ts) {
  const d = new Date(ts || Date.now());
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function toast(msg, type = '', ms = 2600) {
  const wrap = $('#toastWrap');
  const item = document.createElement('div');
  item.className = `toast ${type}`;
  const icon = type === 'ok' ? 'i-check' : (type === 'err' ? 'i-alert' : 'i-spark');
  item.innerHTML = `<svg><use href="#${icon}"/></svg><span></span>`;
  item.querySelector('span').textContent = msg;
  wrap.appendChild(item);
  setTimeout(() => {
    item.classList.add('out');
    setTimeout(() => item.remove(), 320);
  }, ms);
  while (wrap.children.length > 3) wrap.firstElementChild.remove();
}

function apiAvailable() {
  return !!(window.pywebview && window.pywebview.api);
}
async function call(name, ...args) {
  if (!apiAvailable()) throw new Error('原生桥未就绪');
  const res = await window.pywebview.api[name](...args);
  return res || { ok: false, error: '空响应' };
}
async function copyText(text) {
  if (!text) return;
  try {
    const r = await call('copy_text', text);
    if (r && r.ok) { toast('已复制到剪贴板', 'ok', 1600); return; }
  } catch (_) {}
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制到剪贴板', 'ok', 1600);
  } catch (_) {
    toast('复制失败，请手动选择文本', 'err');
  }
}

function currentTargetLabel() {
  const code = S.cfg?.target_lang || 'zh';
  return (S.constants.target_langs || {})[code] || code;
}

/* ============================================================
   Boot
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  initMotion();
  initWindowControls();
  initNav();
  initModals();
  readyBoot();
});

window.addEventListener('pywebviewready', readyBoot);

let bootTimer = setTimeout(() => {
  if (!S.booted && !apiAvailable()) previewBoot();
}, 3200);

async function readyBoot() {
  if (S.booted || !apiAvailable()) return;
  S.booted = true;
  clearTimeout(bootTimer);
  try {
    const res = await call('bootstrap');
    if (!res.ok) throw new Error(res.error || '初始化失败');
    S.cfg = res.config;
    S.state = res.state;
    S.constants = res.constants || S.constants;
    S.devices = (res.devices && res.devices.devices) || [];
    S.models = res.models || {};
    S.app = res.app;
    S.phone = res.phone;
    S.subCursor = res.sub_cursor || 0;
    S.logCursor = res.log_cursor || 0;
    S.subs = (res.subtitles || []).slice().reverse();
    S.logs = (res.logs || []).slice().reverse();
    S.lastSub = S.subs[0] || null;
    if (S.lastSub) S.lastLang = S.lastSub.lang || 'unknown';

    applyAppearance();
    populateAll();
    renderInitial();
    initConfigBindings();
    initActions();
    initCommandPalette();
    updateState();
    startPolling();
    startLevelPolling();
    startDrawLoops();
    requestAnimationFrame(() => navTo((location.hash || '#overview').slice(1), false));
    setTimeout(() => toast('Lingua Studio 已就绪 · 所有处理都在本机', 'ok', 3200), 900);
  } catch (e) {
    console.error(e);
    toast(e.message || '启动失败', 'err', 5000);
    previewBoot();
  }
}

function previewBoot() {
  if (S.booted) return;
  S.booted = true;
  S.previewMode = true;
  S.cfg = {
    target_lang: 'zh', translator: 'free', ocr_source: 'demo', ocr_lang: 'auto',
    ocr_min_score: .62, poll_interval: 1.5, ocr_line_gap: 14,
    overlay: true, overlay_font: 23, subtitle_ttl: 8, overlay_opacity: .88,
    overlay_height: 118, clip_sync: true, clipboard_sync: true,
    show_same_language: false, asr_model: 'base', asr_translate: true,
    theme: 'dark', accent: 'blue', particles: true, particle_density: 70,
    reduce_motion: false, region: [80, 900, 900, 320], pair: '7F3A21',
    asr_device_id: 'preview'
  };
  S.constants = {
    ocr_langs: {
      auto: { label: '自动多语', hint: '中 / 日 / 英 / 欧洲语言', engine: 'PP-OCRv6 multi' },
      ch: { label: '中文 + 英文', hint: '默认高精度' },
      japan: { label: '日语' }, korean: { label: '韩语' }, cyrillic: { label: '俄语 / 西里尔' },
      latin: { label: '欧洲语言' }, arabic: { label: '阿拉伯语' }
    },
    asr_models: { tiny: { size: '约 75 MB' }, base: { size: '约 145 MB' }, small: { size: '约 484 MB' } },
    target_langs: { zh: '简体中文', en: 'English', ja: '日本語', ko: '한국어', ru: 'Русский', de: 'Deutsch', fr: 'Français', es: 'Español', pt: 'Português', ar: 'العربية' }
  };
  S.devices = [
    { id: 'preview', name: '扬声器 (Realtek(R) Audio)', kind: 'loopback', label: '系统声音 · 扬声器 (Realtek(R) Audio)' },
    { id: 'mic', name: '麦克风阵列 (Realtek(R) Audio)', kind: 'microphone', label: '麦克风 · 麦克风阵列 (Realtek(R) Audio)' }
  ];
  S.models = {
    tiny: { downloaded: false, size_mb: 0 }, base: { downloaded: true, size_mb: 141 },
    small: { downloaded: false, size_mb: 0 }
  };
  S.state = {
    running: false, starting: false, status: 'idle', status_text: '界面预览', uptime: 0,
    stats: { ocr_lines: 18, pushed: 6, skipped: 2, asr_segments: 4 }, peers: 1,
    relay_online: false, last_error: '', asr: { status: 'idle', running: false, detail: '预览模式' },
    overlay: true, phone_url: 'http://192.168.1.5:8781/?relay=ws://192.168.1.5:8780&pair=7F3A21',
    relay_url: 'ws://192.168.1.5:8780', pair: '7F3A21', ip: '192.168.1.5'
  };
  S.app = { name: 'Lingua Studio', version: '1.0.0', data_dir: '…\\LinguaStudio\\data', model_dir: '…\\data\\models' };
  S.phone = { url: S.state.phone_url, pair: '7F3A21', ip: '192.168.1.5', qr: '', ports: { relay: 8780, phone: 8781 } };
  S.subs = [
    { id: 3, ts: Date.now(), lang: 'ko', conf: .98, src: '민준: 안녕하세요! 같이 게임 할 사람?', trans: '大家好，有没有人想一起玩？', engine: 'free', source: 'ocr', mode: 'translate' },
    { id: 2, ts: Date.now() - 7000, lang: 'ja', conf: .97, src: 'Yamato: おっす、今日もランク行こうぜ！', trans: '哟，今天也去打排位吧。', engine: 'free', source: 'asr', mode: 'translate' },
    { id: 1, ts: Date.now() - 16000, lang: 'ru', conf: .95, src: 'Ivan: Привет, пойдём в рейд вечером?', trans: '嗨，晚上一起去突袭吗？', engine: 'free', source: 'ocr', mode: 'translate' }
  ];
  S.lastSub = S.subs[0];
  S.lastLang = 'ko';
  applyAppearance();
  populateAll();
  renderInitial();
  initConfigBindings();
  initActions();
  initCommandPalette();
  updateState();
  startDrawLoops();
  requestAnimationFrame(() => navTo((location.hash || '#overview').slice(1), false));
  setTimeout(() => toast('这是界面预览。通过桌面应用启动即可连接真实服务。', '', 4200), 800);
}

/* ============================================================
   Appearance / populate
   ============================================================ */
function applyAppearance() {
  const theme = S.cfg?.theme === 'light' ? 'light' : 'dark';
  const accent = S.cfg?.accent || 'blue';
  S.theme = theme;
  S.accent = accent;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.accent = accent;
  document.documentElement.dataset.motion = S.cfg?.reduce_motion ? 'off' : 'on';
  S.reduce = !!S.cfg?.reduce_motion;
  $$('.theme-choice').forEach(el => el.classList.toggle('is-active', el.dataset.themeOpt === theme));
  $$('.accent-dot').forEach(el => el.classList.toggle('is-active', el.dataset.accent === accent));
  S.particleCount = Number(S.cfg?.particles === false ? 0 : (S.cfg?.particle_density ?? 70));
  particles.setCount(S.particleCount);
  particles.setPalette();
}

function setVal(id, v) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.type === 'checkbox') el.checked = !!v;
  else el.value = v;
}
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}
function setUse(id, icon) {
  const el = document.getElementById(id);
  if (!el) return;
  const use = el.matches && el.matches('svg') ? el : el.querySelector('use');
  if (use) use.setAttribute('href', `#${icon}`);
}

function populateAll() {
  const cfg = S.cfg;
  // 主题 / 粒子
  $$('.theme-choice').forEach(el => el.classList.toggle('is-active', el.dataset.themeOpt === cfg.theme));
  $$('.accent-dot').forEach(el => el.classList.toggle('is-active', el.dataset.accent === cfg.accent));

  // 引擎
  $$('.engine-option').forEach(el => el.classList.toggle('is-active', el.dataset.engine === cfg.translator));
  updateEngineUI(cfg.translator);
  setVal('deeplKey', cfg.deepl_key || '');
  setVal('qwenKey', cfg.qwen_key || '');

  // 目标语言
  renderTargetLangs();

  // OCR
  setVal('ocrLang', cfg.ocr_lang || 'auto');
  setVal('ocrScore', Math.round((cfg.ocr_min_score ?? .62) * 100));
  setText('ocrScoreVal', (cfg.ocr_min_score ?? .62).toFixed(2));
  setVal('pollInterval', cfg.poll_interval ?? 1.5);
  setText('pollIntervalVal', `${(cfg.poll_interval ?? 1.5).toFixed(1)}s`);
  setVal('lineGap', cfg.ocr_line_gap ?? 14);
  setText('lineGapVal', `${cfg.ocr_line_gap ?? 14}px`);
  setVal('demoMode', cfg.ocr_source === 'demo');
  setVal('showSame', cfg.show_same_language);
  setText('regionCoords', `${(cfg.region || [0,0,0,0]).slice(0,2).join(', ')} · ${(cfg.region || [0,0,0,0])[2]} × ${(cfg.region || [0,0,0,0])[3]}`);
  setText('regionSource', cfg.ocr_source === 'demo' ? 'DEMO · 内置样例' : 'SCREEN · 屏幕区域');
  updateOcrPill();

  // 字幕条
  setVal('overlayEnabled', cfg.overlay);
  setVal('overlayStart', cfg.overlay);
  setVal('overlayFontRange', cfg.overlay_font ?? 23);
  setText('overlayFontVal', `${cfg.overlay_font ?? 23}`);
  setVal('overlayTtlRange', Math.round(cfg.subtitle_ttl ?? 8));
  setText('overlayTtlVal', `${Math.round(cfg.subtitle_ttl ?? 8)}s`);
  setVal('overlayOpacityRange', Math.round((cfg.overlay_opacity ?? .88) * 100));
  setText('overlayOpacityVal', `${Math.round((cfg.overlay_opacity ?? .88) * 100)}%`);
  setVal('overlayHeightRange', cfg.overlay_height ?? 118);
  setText('overlayHeightVal', `${cfg.overlay_height ?? 118}px`);
  setVal('overlayRadiusRange', cfg.overlay_radius ?? 26);
  setText('overlayRadiusVal', `${cfg.overlay_radius ?? 26}px`);
  setVal('reduceMotion', cfg.reduce_motion);
  setVal('particlesToggle', cfg.particles !== false);
  setVal('particleDensity', cfg.particle_density ?? 70);
  setText('particleDensityVal', `${cfg.particle_density ?? 70}`);
  updateSubtitleStyle();
  updatePreviewFromLast();

  // 手机 / 剪贴板
  setVal('clipSync', cfg.clipboard_sync);
  updatePhoneUI();

  // 语音
  fillDevices();
  setVal('asrModel', cfg.asr_model || 'base');
  setVal('asrLang', cfg.asr_language || '');
  setVal('asrChunk', cfg.asr_chunk ?? 5);
  const chunkEl = $('#asrChunk'); if (chunkEl && chunkEl.nextElementSibling) chunkEl.nextElementSibling.textContent = `${cfg.asr_chunk ?? 5}s`;
  setVal('asrTranslate', cfg.asr_translate !== false);
  updateModelState();

  // 系统
  setText('dataDir', S.app?.data_dir || '—');
  setText('appVersion', S.app?.version || '1.0.0');
  setText('modelDirSize', `${(cfg.asr_model || 'base').toUpperCase()} · ${S.models?.[cfg.asr_model]?.size_mb || '—'} MB`);

  // 二维码
  if (S.phone?.qr) $('#qrImg').src = S.phone.qr;
  setText('phoneUrl', S.phone?.url || S.state?.phone_url || 'http://—');
  setText('pairCode', S.phone?.pair || S.state?.pair || '——');
  setText('relayUrl', S.phone?.url ? (S.phone.url.match(/relay=([^&]+)/)?.[1] || S.state?.relay_url) : (S.state?.relay_url || 'ws://—'));
}

function renderTargetLangs() {
  const wrap = $('#targetLangs');
  if (!wrap) return;
  wrap.innerHTML = '';
  const langs = S.constants.target_langs || {};
  Object.entries(langs).forEach(([code, label]) => {
    const b = document.createElement('button');
    b.className = 'lang-opt' + (S.cfg.target_lang === code ? ' is-active' : '');
    b.dataset.lang = code;
    b.textContent = label;
    b.addEventListener('click', async () => {
      $$('.lang-opt', wrap).forEach(x => x.classList.toggle('is-active', x.dataset.lang === code));
      S.cfg.target_lang = code;
      updatePreviewFromLast();
      queueSave({ target_lang: code });
      updateState();
      if (!S.previewMode) await applyTranslator(true);
    });
    wrap.appendChild(b);
  });
}
function updateOcrPill() {
  const info = (S.constants.ocr_langs || {})[S.cfg?.ocr_lang || 'auto'] || {};
  setText('ocrEnginePill', info.engine || 'PP-OCRv6');
  const hint = info.hint || '首次切换专用模型会自动下载（约 10 MB）。';
  setText('ocrHint', S.cfg?.ocr_lang === 'auto' || S.cfg?.ocr_lang === 'ch' ? '多语模型已随应用内置，无需下载。' : hint + ' 首次切换会自动下载（约 10 MB）。');
}

function shortDeviceName(d) {
  const n = d.name || '';
  if (n.includes('CABLE Input')) return '系统声音 · VB-Cable';
  if (n.includes('Maono')) return '麦克风 · Maono';
  if (n.includes('麦克风阵列')) return '麦克风 · Realtek';
  if (n.includes('HyperX')) return '系统声音 · HyperX';
  if (n.includes('NVIDIA')) return '系统声音 · NVIDIA';
  if (n.includes('Realtek') && d.kind === 'loopback') return '系统声音 · Realtek';
  if (n.includes('Realtek')) return '麦克风 · Realtek';
  return (d.kind === 'loopback' ? '系统声音 · ' : '麦克风 · ') + n;
}

function fillDevices() {
  const sel = $('#asrDevice');
  if (!sel) return;
  sel.innerHTML = '';
  const list = S.devices || [];
  if (!list.length) {
    const o = document.createElement('option');
    o.value = ''; o.textContent = '未发现音频设备';
    sel.appendChild(o);
  } else {
    list.forEach(d => {
      const o = document.createElement('option');
      o.value = d.id;
      o.textContent = shortDeviceName(d);
      o.title = d.label || d.name;
      sel.appendChild(o);
    });
    const cfgId = S.cfg?.asr_device_id;
    const preferred = list.find(d => d.id === cfgId) || list.find(d => d.kind === 'loopback') || list[0];
    sel.value = preferred.id;
    sel.title = preferred.label || preferred.name;
  }
  setText('deviceCount', `${list.length} 个设备`);
}

function updateModelState() {
  const model = (S.cfg?.asr_model || 'base');
  const m = S.models?.[model] || {};
  const size = m.size_mb ? `${m.size_mb} MB` : (S.constants.asr_models?.[model]?.size || '约 145 MB');
  const stateEl = $('#modelState');
  const text = m.downloaded ? `${model.toUpperCase()} 模型 ${size} · 本地` : `${model.toUpperCase()} 模型待下载 · 首次约 ${size}`;
  setText('modelStateText', text);
  if (stateEl) stateEl.classList.toggle('warn', !m.downloaded);
  setText('asrModelPill', `${model.toUpperCase()} · ${m.downloaded ? '已就绪' : '待下载'}`);
  setText('modelDirSize', `${model.toUpperCase()} · ${m.downloaded ? size : '待下载'}`);
}

function updateEngineUI(engine) {
  $$('.engine-option').forEach(el => el.classList.toggle('is-active', el.dataset.engine === engine));
  const keys = $('#engineKeys');
  if (keys) keys.classList.toggle('hidden', !(engine === 'deepl' || engine === 'qwen'));
  const deeplField = $('#deeplKeyField');
  const qwenField = $('#qwenKeyField');
  if (deeplField) deeplField.classList.toggle('hidden', engine !== 'deepl');
  if (qwenField) qwenField.classList.toggle('hidden', engine !== 'qwen');
}

function updateSubtitleStyle() {
  const size = Math.max(12, Math.min(21, Math.round((S.cfg?.overlay_font || 23) * 0.68)));
  const radius = Math.max(8, Math.min(40, Math.round(S.cfg?.overlay_radius ?? 26)));
  [$('#subtitleBar'), $('#subtitleBar2')].forEach(bar => {
    if (!bar) return;
    bar.style.setProperty('--sb-font', `${size}px`);
    bar.style.borderRadius = `${radius}px`;
    bar.style.opacity = String(clamp(S.cfg?.overlay_opacity ?? .88, .3, 1));
  });
}

/* ============================================================
   Config binding / saving
   ============================================================ */
function initConfigBindings() {
  // ranges / selects / inputs with data-cfg
  $$('[data-cfg]').forEach(el => {
    const key = el.dataset.cfg;
    if (key === 'ocr_source' || key === 'overlay') return; // handled specially
    const isRange = el.type === 'range';
    const handler = () => {
      const patch = readCfgControl(el);
      if (!patch) return;
      Object.assign(S.cfg, patch);
      reflectCfgPatch(patch);
      queueSave(patch);
    };
    el.addEventListener(isRange ? 'input' : 'change', () => {
      updateControlLabel(el);
      if (!isRange) handler();
    });
    if (isRange) el.addEventListener('change', handler);
    updateControlLabel(el);
    updateRangeFill(el);
    if (isRange) el.addEventListener('input', () => updateRangeFill(el));
  });

  // 字幕条开关（两处）
  ['overlayEnabled', 'overlayStart'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      S.cfg.overlay = el.checked;
      ['overlayEnabled', 'overlayStart'].forEach(x => { const e = document.getElementById(x); if (e) e.checked = el.checked; });
      queueSave({ overlay: el.checked });
    });
  });

  // OCR 演示模式（反向）
  const demo = $('#demoMode');
  if (demo) demo.addEventListener('change', () => {
    const source = demo.checked ? 'demo' : 'screen';
    S.cfg.ocr_source = source;
    setText('regionSource', source === 'demo' ? 'DEMO · 内置样例' : 'SCREEN · 屏幕区域');
    queueSave({ ocr_source: source });
    updateSetup();
  });

  // 主题 / 强调色
  $$('.theme-choice').forEach(el => el.addEventListener('click', () => {
    S.cfg.theme = el.dataset.themeOpt;
    applyAppearance();
    queueSave({ theme: S.cfg.theme });
  }));
  $$('.accent-dot').forEach(el => el.addEventListener('click', () => {
    S.cfg.accent = el.dataset.accent;
    applyAppearance();
    queueSave({ accent: S.cfg.accent });
  }));

  // 粒子开关 / 密度 / 减弱动效
  const pt = $('#particlesToggle');
  if (pt) pt.addEventListener('change', () => {
    S.cfg.particles = pt.checked;
    particles.setCount(pt.checked ? (S.cfg.particle_density || 70) : 0);
    queueSave({ particles: pt.checked });
  });
  const pd = $('#particleDensity');
  if (pd) pd.addEventListener('input', () => {
    const v = Number(pd.value);
    setText('particleDensityVal', `${v}`);
    S.cfg.particle_density = v;
    particles.setCount(S.cfg.particles === false ? 0 : v);
  });
  if (pd) pd.addEventListener('change', () => queueSave({ particle_density: Number(pd.value) }));
  const rm = $('#reduceMotion');
  if (rm) rm.addEventListener('change', () => {
    S.cfg.reduce_motion = rm.checked;
    document.documentElement.dataset.motion = rm.checked ? 'off' : 'on';
    queueSave({ reduce_motion: rm.checked });
  });

  // 字幕条控件（实时预览 + 持久化）
  const fontRange = $('#overlayFontRange');
  if (fontRange) fontRange.addEventListener('input', () => {
    setText('overlayFontVal', fontRange.value);
    S.cfg.overlay_font = Number(fontRange.value);
    updateSubtitleStyle();
  });
  if (fontRange) fontRange.addEventListener('change', () => queueSave({ overlay_font: Number(fontRange.value) }));
  const ttlRange = $('#overlayTtlRange');
  if (ttlRange) ttlRange.addEventListener('input', () => {
    setText('overlayTtlVal', `${ttlRange.value}s`);
    S.cfg.subtitle_ttl = Number(ttlRange.value);
  });
  if (ttlRange) ttlRange.addEventListener('change', () => queueSave({ subtitle_ttl: Number(ttlRange.value) }));
  const opRange = $('#overlayOpacityRange');
  if (opRange) opRange.addEventListener('input', () => {
    setText('overlayOpacityVal', `${opRange.value}%`);
    S.cfg.overlay_opacity = Number(opRange.value) / 100;
  });
  if (opRange) opRange.addEventListener('change', () => queueSave({ overlay_opacity: Number(opRange.value) / 100 }));
  const hRange = $('#overlayHeightRange');
  if (hRange) hRange.addEventListener('input', () => {
    setText('overlayHeightVal', `${hRange.value}px`);
    S.cfg.overlay_height = Number(hRange.value);
    updateSubtitleStyle();
  });
  if (hRange) hRange.addEventListener('change', () => queueSave({ overlay_height: Number(hRange.value) }));
  const radRange = $('#overlayRadiusRange');
  if (radRange) radRange.addEventListener('input', () => {
    setText('overlayRadiusVal', `${radRange.value}px`);
    S.cfg.overlay_radius = Number(radRange.value);
    updateSubtitleStyle();
    [$('#subtitleBar'), $('#subtitleBar2')].forEach(bar => { if (bar) bar.style.borderRadius = `${radRange.value}px`; });
  });
  if (radRange) radRange.addEventListener('change', () => queueSave({ overlay_radius: Number(radRange.value) }));

  // 语音模型 / 语言 / 分段
  const modelSel = $('#asrModel');
  if (modelSel) modelSel.addEventListener('change', () => {
    S.cfg.asr_model = modelSel.value;
    updateModelState();
    queueSave({ asr_model: modelSel.value });
  });
  const asrLang = $('#asrLang');
  if (asrLang) asrLang.addEventListener('change', () => {
    S.cfg.asr_language = asrLang.value;
    setText('asrLangPill', asrLang.value ? LANG_SHORT[asrLang.value] || asrLang.value.toUpperCase() : 'AUTO');
    queueSave({ asr_language: asrLang.value });
  });
  const asrDevice = $('#asrDevice');
  if (asrDevice) asrDevice.addEventListener('change', () => {
    S.cfg.asr_device_id = asrDevice.value;
    const d = S.devices.find(x => x.id === asrDevice.value);
    if (d) S.cfg.asr_device_name = d.name;
    queueSave({ asr_device_id: asrDevice.value, asr_device_name: d?.name || '' });
  });
  const chunk = $('#asrChunk');
  if (chunk) chunk.addEventListener('input', () => {
    if (chunk.nextElementSibling) chunk.nextElementSibling.textContent = `${chunk.value}s`;
    updateRangeFill(chunk);
  });
  if (chunk) chunk.addEventListener('change', () => queueSave({ asr_chunk: Number(chunk.value) }));
  const ocrLang = $('#ocrLang');
  if (ocrLang) ocrLang.addEventListener('change', () => {
    S.cfg.ocr_lang = ocrLang.value;
    updateOcrPill();
    queueSave({ ocr_lang: ocrLang.value });
  });

  // 引擎 key（change 事件由通用绑定处理，无需重复）
  // 手机 / 剪贴板
  const clip = $('#clipSync');
  if (clip) clip.addEventListener('change', () => queueSave({ clipboard_sync: clip.checked }));
  const asrTrans = $('#asrTranslate');
  if (asrTrans) asrTrans.addEventListener('change', () => queueSave({ asr_translate: asrTrans.checked }));
}

function readCfgControl(el) {
  const key = el.dataset.cfg;
  if (!key || el.type === 'checkbox') {
    if (el.type === 'checkbox') return { [key]: el.checked };
    return null;
  }
  let val;
  if (el.type === 'range') {
    val = Number(el.value);
    if (key === 'ocr_min_score') val = val / 100;
    if (key === 'overlay_opacity') val = val / 100;
    if (key === 'overlay_font' || key === 'ocr_line_gap' || key === 'overlay_height' || key === 'particle_density') val = Math.round(val);
    if (key === 'poll_interval' || key === 'subtitle_ttl') val = Math.round(val * 10) / 10;
  } else {
    val = el.value;
  }
  return { [key]: val };
}

function reflectCfgPatch(patch) {
  const key = Object.keys(patch)[0];
  if (key === 'overlay_font') { setText('overlayFontVal', String(patch[key])); updateSubtitleStyle(); }
  if (key === 'subtitle_ttl') setText('overlayTtlVal', `${patch[key]}s`);
  if (key === 'overlay_opacity') setText('overlayOpacityVal', `${Math.round(patch[key] * 100)}%`);
  if (key === 'ocr_min_score') setText('ocrScoreVal', Number(patch[key]).toFixed(2));
  if (key === 'poll_interval') setText('pollIntervalVal', `${Number(patch[key]).toFixed(1)}s`);
  if (key === 'ocr_line_gap') setText('lineGapVal', `${patch[key]}px`);
  if (key === 'overlay_height') setText('overlayHeightVal', `${patch[key]}px`);
  if (key === 'particle_density') setText('particleDensityVal', String(patch[key]));
  if (key === 'theme' || key === 'accent') applyAppearance();
  if (key === 'clipboard_sync') setVal('clipSync', patch[key]);
}

function updateControlLabel(el) {
  const id = el.id;
  const map = {
    overlayFontRange: ['overlayFontVal', v => `${v}`],
    overlayTtlRange: ['overlayTtlVal', v => `${v}s`],
    overlayOpacityRange: ['overlayOpacityVal', v => `${v}%`],
    ocrScore: ['ocrScoreVal', v => (Number(v) / 100).toFixed(2)],
    pollInterval: ['pollIntervalVal', v => `${Number(v).toFixed(1)}s`],
    lineGap: ['lineGapVal', v => `${v}px`],
    overlayHeightRange: ['overlayHeightVal', v => `${v}px`],
    overlayRadiusRange: ['overlayRadiusVal', v => `${v}px`],
    particleDensity: ['particleDensityVal', v => `${v}`],
    asrChunk: ['asrChunkVal', v => `${v}s`]
  };
  if (map[id]) {
    const target = document.getElementById(map[id][0]);
    if (target) target.textContent = map[id][1](el.value);
  }
  updateRangeFill(el);
}

function updateRangeFill(el) {
  if (!el || el.type !== 'range') return;
  const min = Number(el.min || 0), max = Number(el.max || 100), v = Number(el.value);
  el.style.setProperty('--fill', `${((v - min) / (max - min)) * 100}%`);
}

function queueSave(patch) {
  if (S.previewMode) return;
  S.pendingCfg = { ...S.pendingCfg, ...patch };
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(async () => {
    const p = S.pendingCfg;
    S.pendingCfg = {};
    try {
      const r = await call('save_config', p);
      if (r.ok) {
        S.cfg = r.config;
        if (r.phone) { S.phone = r.phone; updatePhoneUI(); }
        updateSetup();
      } else toast(r.error || '保存失败', 'err');
    } catch (e) { if (!S.previewMode) toast('保存失败：' + e.message, 'err'); }
  }, 180);
}

async function flushSave() {
  if (S.previewMode) return true;
  clearTimeout(S.saveTimer);
  const p = S.pendingCfg;
  S.pendingCfg = {};
  if (!p || !Object.keys(p).length) return true;
  try {
    const r = await call('save_config', p);
    if (r.ok) { S.cfg = r.config; if (r.phone) { S.phone = r.phone; updatePhoneUI(); } }
    else toast(r.error || '保存失败', 'err');
    return !!r.ok;
  } catch (e) { if (!S.previewMode) toast('保存失败：' + e.message, 'err'); return false; }
}

/* ============================================================
   State polling
   ============================================================ */
async function startPolling() {
  if (S.previewMode) return;
  pollState();
}
async function pollState() {
  if (S.polling) return;
  S.polling = true;
  try {
    const r = await call('get_state', S.subCursor, S.logCursor);
    if (r.ok) applyDelta(r);
  } catch (e) {
    // keep UI alive; no repeated toast
  } finally {
    S.polling = false;
    const delay = (S.state?.starting || S.state?.asr?.status === 'preparing') ? 350 : 650;
    setTimeout(pollState, delay);
  }
}
function applyDelta(delta) {
  if (delta.state) S.state = delta.state;
  const newSubs = delta.subtitles || [];
  newSubs.forEach(addSubtitle);
  if (delta.sub_cursor) S.subCursor = delta.sub_cursor;
  const newLogs = delta.logs || [];
  newLogs.forEach(addLog);
  if (delta.log_cursor) S.logCursor = delta.log_cursor;
  updateState();
}

function updateState() {
  const st = S.state;
  if (!st) return;
  const running = !!st.running;
  const starting = !!st.starting;
  const asr = st.asr || {};
  const asrOn = !!(asr.running || ['listening', 'transcribing', 'preparing'].includes(asr.status));
  const error = st.status === 'error';

  // titlebar / hero
  setText('tbStatus', running ? '实时翻译运行中' : starting ? '正在启动…' : error ? '启动失败' : '等待开始');
  setText('tbStatusText', running ? 'RUNNING' : starting ? 'STARTING' : error ? 'ERROR' : 'IDLE');
  const pillDot = $('#tbStatusPill .s-dot');
  if (pillDot) pillDot.className = `s-dot ${running ? 'on' : starting ? 'busy' : error ? 'err' : ''}`;
  setText('heroToggleText', running ? '停止翻译' : starting ? '启动中…' : '开始翻译');
  setUse('heroToggleIcon', running ? 'i-stop' : 'i-play');
  setText('heroStatus', st.status_text || '等待开始');
  const hd = $('#heroDot'); if (hd) hd.className = `s-dot ${running ? 'on' : starting ? 'busy' : error ? 'err' : ''}`;
  setText('heroEngine', ENGINE_LABEL[S.cfg?.translator] || '免费在线');
  setText('orbState', asrOn ? (asr.status === 'transcribing' ? 'TRANSCRIBING' : 'LISTENING') : running ? 'LIVE' : starting ? 'BOOTING' : 'IDLE');
  setText('orbLang', S.lastSub ? (LANG_SHORT[S.lastSub.lang] || '??') : '—');
  setText('orbSub', S.lastSub ? `${LANG_FULL[S.lastSub.lang] || '未知'} → ${currentTargetLabel()}` : '等待声音或字幕');
  $('#orb')?.classList.toggle('running', running || asrOn);

  // stats
  setStat('ocr_lines', st.stats?.ocr_lines || 0);
  setStat('pushed', st.stats?.pushed || 0);
  setStat('asr_segments', st.stats?.asr_segments || 0);
  setStat('peers', st.peers || 0);
  updateRate();
  setText('statAsrState', asrOn ? (asr.status === 'transcribing' ? '转写中' : '聆听中') : '离线');
  $('#statAsrState')?.classList.toggle('on', asrOn);
  setText('statQr', st.peers > 0 ? '已连接' : running ? '等待扫码' : '扫码连接');

  // relay
  const relayDot = $('#relayDot');
  if (relayDot) relayDot.className = `live-dot ${(running && st.relay_online) ? 'on' : ''}`;
  setText('relayLabel', running ? (st.relay_online ? '中继在线' : '中继连接中') : starting ? '正在启动' : error ? '启动失败' : '中继未启动');
  setText('relayPair', `配对码 ${st.pair || '—'}`);
  setText('relayPeers', `手机 ${st.peers || 0}`);
  const line = $('#relayLine');
  if (line) line.style.width = running && st.relay_online ? '100%' : starting ? '55%' : '0%';

  // nav dots
  $('#navPhoneDot')?.classList.toggle('on', (st.peers || 0) > 0);
  $('#navVoiceDot')?.classList.toggle('on', asrOn);
  setText('navLiveCount', String(Math.min(999, st.stats?.pushed || 0)));

  // ASR
  const status = asr.status || 'idle';
  const statusMap = {
    idle: '语音识别未启动', ready: '语音模型已就绪', preparing: '正在准备语音模型',
    listening: '正在聆听', transcribing: '正在转写…', stopping: '正在停止…', error: '语音识别出错'
  };
  setText('asrStateText', statusMap[status] || status);
  setText('asrDetailText', asr.detail || (asrOn ? '音频只在本机处理' : '选择输入设备后开始聆听'));
  $('#voiceMicRing')?.classList.toggle('on', asrOn);
  setText('asrToggleText', asrOn ? '停止聆听' : '开始聆听');
  setUse('asrToggleIcon', asrOn ? 'i-stop' : 'i-mic');
  setText('asrLangPill', asr.language ? (LANG_SHORT[asr.language] || asr.language.toUpperCase()) : (S.cfg?.asr_language ? (LANG_SHORT[S.cfg.asr_language] || S.cfg.asr_language.toUpperCase()) : 'AUTO'));
  $('#asrModelPill')?.classList.toggle('on', !!S.models?.[S.cfg?.asr_model]?.downloaded);
  updateModelState();
  if (!asrOn) S.levels = [];

  // setup
  updateSetup();

  // phone / overlay / preview
  updatePhoneUI();
  updatePreviewFromLast();
  setText('mobileStatusPill', running ? `服务在线 · 手机 ${st.peers || 0}` : starting ? '正在启动' : '等待启动');
  $('#mobileStatusPill')?.classList.toggle('on', running);

  // server urls
  if (st.phone_url) setText('phoneUrl', st.phone_url);
  if (st.pair) setText('pairCode', st.pair);
  if (st.relay_url) setText('relayUrl', st.relay_url);
  if (st.phone_url && (!S.phone?.url || S.phone.url !== st.phone_url) && running) refreshPhone();
}

let phoneRefreshAt = 0;
async function refreshPhone() {
  if (S.previewMode || performance.now() - phoneRefreshAt < 2500) return;
  phoneRefreshAt = performance.now();
  try {
    const r = await call('phone_qr');
    if (r.ok) {
      S.phone = r;
      updatePhoneUI();
    }
  } catch (_) {}
}

function setStat(key, value) {
  $$(`[data-stat="${key}"]`).forEach(el => {
    const from = Number(el.dataset.value || 0);
    const to = Number(value || 0);
    if (from === to) return;
    el.dataset.value = String(to);
    animateNumber(el, from, to, 550);
  });
}
function animateNumber(el, from, to, dur) {
  const t0 = performance.now();
  const step = (t) => {
    const p = clamp((t - t0) / dur, 0, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = String(Math.round(from + (to - from) * eased));
    if (p < 1) requestAnimationFrame(step);
    else el.textContent = String(to);
  };
  requestAnimationFrame(step);
}
function updateRate() {
  const pushed = S.state?.stats?.pushed || 0;
  const now = performance.now();
  if (!S.lastStatAt) { S.lastStatAt = now; S.lastPushed = pushed; }
  if (now - S.lastStatAt > 2000) {
    const delta = Math.max(0, pushed - S.lastPushed);
    const sec = (now - S.lastStatAt) / 1000;
    setText('statRate', `${Math.round(delta / sec * 60)}/min`);
    S.lastStatAt = now;
    S.lastPushed = pushed;
  }
}

function updateSetup() {
  const st = S.state, cfg = S.cfg;
  const checks = {
    vision: cfg?.ocr_source === 'screen',
    engine: cfg?.translator && cfg.translator !== 'mock',
    mobile: !!(st && st.running)
  };
  let n = 0;
  Object.entries(checks).forEach(([k, v]) => {
    const el = $(`.setup-check[data-check="${k}"]`);
    if (el) el.classList.toggle('done', !!v);
    if (v) n++;
  });
  setText('setupProgress', `${n}/3`);
  const region = cfg?.region || [0, 0, 0, 0];
  setText('setupRegionText', cfg?.ocr_source === 'screen' ? `已框选 ${region[2]} × ${region[3]} · ${ENGINE_LABEL[cfg.translator] || ''}` : '当前为演示模式 · 点此圈选');
  setText('setupEngineText', `${ENGINE_LABEL[cfg?.translator] || '免费在线'} · ${cfg?.translator === 'free' ? '无需 Key' : cfg?.translator === 'mock' ? '仅演示' : '已配置'}`);
  setText('setupMobileText', st?.peers > 0 ? `${st.peers} 台手机在线` : st?.running ? '服务已就绪 · 等待扫码' : '手机与电脑同一 WiFi');
}

function updatePhoneUI() {
  if (!S.phone) return;
  setText('phoneUrl', S.phone.url || S.state?.phone_url || 'http://—');
  setText('pairCode', S.phone.pair || S.state?.pair || '——');
  const url = S.phone.url || '';
  const relay = url.match(/relay=([^&]+)/);
  setText('relayUrl', relay ? decodeURIComponent(relay[1]) : (S.state?.relay_url || 'ws://—'));
  const img = $('#qrImg');
  if (img) {
    if (S.phone.qr) { img.src = S.phone.qr; img.style.opacity = '1'; }
    else img.style.opacity = '0';
  }
}

function updatePreviewFromLast() {
  const sub = S.lastSub;
  const meta = sub ? `${LANG_SHORT[sub.lang] || '??'} → ${currentTargetLabel()}${sub.source === 'asr' ? ' · 语音' : ' · 实时翻译'}` : `JA → ${currentTargetLabel()} · 实时翻译`;
  const text = sub ? (sub.trans || sub.src) : '今天也去打排位吧。';
  setText('previewMeta', meta); setText('previewMeta2', meta);
  setText('previewTrans', text); setText('previewTrans2', text);
}

/* ============================================================
   Feeds and logs
   ============================================================ */
function addSubtitle(msg) {
  if (!msg) return;
  // 手动翻译会同时走 bootstrap/delta 与接口返回值，按内容去重，避免同一句出现两次
  if (S.subs.some(s => (
    (s.id != null && msg.id != null && s.id === msg.id) ||
    (s.ts === msg.ts && s.source === msg.source && s.src === msg.src && s.trans === msg.trans)
  ))) return;
  S.lastSub = msg;
  S.lastLang = msg.lang || 'unknown';
  S.subs.unshift(msg);
  if (S.subs.length > 140) S.subs.pop();
  appendFeedItem(msg, false);
  appendOverviewItem(msg);
  appendAsrItem(msg);
  updatePreviewFromLast();
  setText('orbLang', LANG_SHORT[msg.lang] || '??');
  setText('orbSub', `${LANG_FULL[msg.lang] || '未知'} → ${currentTargetLabel()}`);
}

function langBadge(lang) {
  const known = ['en','ja','ko','ru','de','fr','es','pt','it','zh','tr','ar','vi','th','unknown'];
  const cls = known.includes(lang) ? lang : 'unknown';
  return `<span class="lang-badge ${cls}">${LANG_SHORT[lang] || '??'}</span>`;
}

function feedItemEl(msg, compact = false) {
  const item = document.createElement('div');
  item.className = `feed-item${compact ? ' compact' : ''}`;
  const conf = Math.round((msg.conf || 0) * 100);
  const source = SOURCE_LABEL[msg.source] || 'OCR';
  const badges = [];
  if (msg.degraded) badges.push('<span class="fi-degraded">原文</span>');
  if (msg.same_lang || msg.mode === 'transcribe') badges.push('<span class="fi-mode">仅转写</span>');
  item.innerHTML = `
    <div class="fi-top">
      ${langBadge(msg.lang)}
      <span class="fi-time">${clock(msg.ts)}</span>
      <span class="fi-source">${source}</span>
      <span class="conf-track"><i style="width:${clamp(conf, 0, 100)}%"></i></span>
      ${badges.join('')}
    </div>
    <div class="fi-src"></div>
    <div class="fi-trans"></div>
    <div class="fi-actions">
      <button class="fi-act" data-act="copy-trans" title="复制译文"><svg><use href="#i-copy"/></svg></button>
      <button class="fi-act" data-act="copy-src" title="复制原文"><svg><use href="#i-clipboard"/></svg></button>
      <button class="fi-act" data-act="retry" title="重译"><svg><use href="#i-refresh"/></svg></button>
      <button class="fi-act" data-act="overlay" title="投到字幕条"><svg><use href="#i-eye"/></svg></button>
    </div>`;
  item.querySelector('.fi-src').textContent = msg.src || '';
  item.querySelector('.fi-trans').textContent = msg.trans || msg.src || '';
  item.querySelectorAll('.fi-act').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const act = btn.dataset.act;
      if (act === 'copy-trans') copyText(msg.trans);
      if (act === 'copy-src') copyText(msg.src);
      if (act === 'retry') retrySubtitle(msg);
      if (act === 'overlay') testOverlay(msg.trans || msg.src);
    });
  });
  return item;
}

function appendFeedItem(msg, compact = false, force = false) {
  if (!force && S.filter !== 'all' && msg.source !== S.filter) return;
  const feed = $('#liveFeed');
  if (!feed) return;
  $('#liveEmpty')?.classList.add('hidden');
  feed.prepend(feedItemEl(msg, compact));
  while (feed.querySelectorAll('.feed-item').length > 80) {
    const items = feed.querySelectorAll('.feed-item');
    items[items.length - 1].remove();
  }
}

function appendOverviewItem(msg) {
  const feed = $('#overviewFeed');
  if (!feed) return;
  $('#overviewEmpty')?.classList.add('hidden');
  feed.prepend(feedItemEl(msg, true));
  while (feed.querySelectorAll('.feed-item').length > 5) {
    const items = feed.querySelectorAll('.feed-item');
    items[items.length - 1].remove();
  }
}

function appendAsrItem(msg) {
  if (msg.source !== 'asr') return;
  const feed = $('#asrFeed');
  if (!feed) return;
  const empty = feed.querySelector('.feed-empty');
  if (empty) empty.remove();
  const line = document.createElement('div');
  line.className = 'asr-line';
  line.innerHTML = `<div class="al-top">${langBadge(msg.lang)}<span class="al-time">${clock(msg.ts)}</span></div><strong></strong><small></small>`;
  line.querySelector('strong').textContent = msg.src || '';
  line.querySelector('small').textContent = msg.trans && msg.mode !== 'transcribe' ? msg.trans : '仅转写';
  feed.prepend(line);
  while (feed.querySelectorAll('.asr-line').length > 40) {
    const lines = feed.querySelectorAll('.asr-line');
    lines[lines.length - 1].remove();
  }
}

function ensureAsrEmpty() {
  const feed = $('#asrFeed');
  if (!feed) return;
  if (feed.querySelector('.asr-line') || feed.querySelector('.feed-empty')) return;
  feed.innerHTML = `<div class="feed-empty small">
    <div class="empty-orb"><svg><use href="#i-mic"/></svg></div>
    <strong>等待语音</strong>
    <span>系统声音 · 麦克风 · 自动语种</span>
  </div>`;
}

function renderInitial() {
  const live = $('#liveFeed');
  if (live) {
    live.querySelectorAll('.feed-item').forEach(x => x.remove());
    S.subs.slice(0, 60).forEach(s => appendFeedItem(s, false, true));
    if (!S.subs.length) $('#liveEmpty')?.classList.remove('hidden');
    else $('#liveEmpty')?.classList.add('hidden');
  }
  const ov = $('#overviewFeed');
  if (ov) {
    ov.querySelectorAll('.feed-item').forEach(x => x.remove());
    S.subs.slice(0, 5).forEach(s => appendOverviewItem(s));
    if (!S.subs.length) $('#overviewEmpty')?.classList.remove('hidden');
    else $('#overviewEmpty')?.classList.add('hidden');
  }
  const asr = $('#asrFeed');
  if (asr) {
    asr.querySelectorAll('.asr-line').forEach(x => x.remove());
    S.subs.filter(s => s.source === 'asr').slice(0, 20).forEach(s => appendAsrItem(s));
    ensureAsrEmpty();
  }
  // logs
  const logList = $('#logList');
  if (logList) {
    logList.innerHTML = '';
    S.logs.slice(0, 50).forEach(l => appendLog(l, true));
  }
  renderClipEvents();
  renderOcrEmpty();
  updatePreviewFromLast();
}

function applyFeedFilter() {
  const feed = $('#liveFeed');
  if (!feed) return;
  feed.querySelectorAll('.feed-item').forEach(x => x.remove());
  const list = S.filter === 'all' ? S.subs : S.subs.filter(s => s.source === S.filter);
  list.slice(0, 60).forEach(s => appendFeedItem(s, false, true));
  $('#liveEmpty')?.classList.toggle('hidden', list.length > 0);
}

function addLog(item, silent = false) {
  if (!item) return;
  S.logs.unshift(item);
  if (S.logs.length > 300) S.logs.pop();
  if (!silent) appendLog(item);
}

function appendLog(item, bottom = false) {
  const list = $('#logList');
  if (!list) return;
  const row = document.createElement('div');
  row.className = `log-item ${item.level || ''}`;
  row.innerHTML = `<time>${clock(item.ts)}</time><i class="lg-dot"></i><span></span>`;
  row.querySelector('span').textContent = item.msg || '';
  if (bottom) list.appendChild(row);
  else list.prepend(row);
  while (list.children.length > 60) {
    if (bottom) list.removeChild(list.firstElementChild);
    else list.removeChild(list.lastElementChild);
  }
  if (item.level === 'clip') renderClipEvents();
}

function renderClipEvents() {
  const wrap = $('#clipEvents');
  if (!wrap) return;
  const clips = S.logs.filter(l => l.level === 'clip').slice(0, 6);
  wrap.innerHTML = '';
  if (!clips.length) {
    wrap.innerHTML = '<div class="muted-line">剪贴板事件会出现在操作记录中。</div>';
    return;
  }
  clips.forEach(l => {
    const row = document.createElement('div');
    row.className = 'log-item clip';
    row.innerHTML = `<time>${clock(l.ts)}</time><i class="lg-dot"></i><span></span>`;
    row.querySelector('span').textContent = l.msg;
    wrap.appendChild(row);
  });
}

function renderOcrEmpty() {
  const lines = $('#ocrLines');
  if (lines && !lines.children.length) lines.innerHTML = '<div class="muted-line">测试识别后，这里会显示每一行的置信度与文本。</div>';
}

async function retrySubtitle(msg) {
  if (S.previewMode) return toast('预览模式不可重译', '');
  try {
    const r = await call('manual_translate', msg.src || '');
    if (!r.ok) return toast(r.error || '重译失败', 'err');
    toast(r.queued ? '已提交重译' : '已重新翻译', 'ok');
    if (r.message) addSubtitle(r.message);
  } catch (e) { toast(e.message, 'err'); }
}

async function testOverlay(text) {
  if (S.previewMode) return toast('预览模式：字幕条将在桌面显示', '');
  try {
    const r = await call('overlay_test', text || '字幕条预览 · Lingua Studio');
    if (!r.ok) toast(r.error || '字幕条未启动', 'err');
    else toast('字幕条已显示在桌面上', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

/* ============================================================
   Actions
   ============================================================ */
function initActions() {
  $('#heroToggle')?.addEventListener('click', toggleService);
  $('#clearFeed')?.addEventListener('click', async () => {
    if (S.previewMode) return;
    const r = await call('clear_feed');
    if (r.ok) {
      S.subs = []; S.lastSub = null;
      $('#liveFeed').querySelectorAll('.feed-item').forEach(x => x.remove());
      $('#overviewFeed').querySelectorAll('.feed-item').forEach(x => x.remove());
      $('#asrFeed').querySelectorAll('.asr-line').forEach(x => x.remove());
      ensureAsrEmpty();
      $('#liveEmpty')?.classList.remove('hidden');
      $('#overviewEmpty')?.classList.remove('hidden');
      toast('字幕流已清空', 'ok');
    }
  });

  // 手动翻译
  const sendManual = async () => {
    const input = $('#manualInput');
    const text = input.value.trim();
    if (!text) return toast('先输入一句话', '');
    if (S.previewMode) return toast('预览模式：请从桌面应用启动', '');
    try {
      const r = await call('manual_translate', text);
      if (!r.ok) return toast(r.error || '翻译失败', 'err');
      input.value = '';
      toast(r.queued ? '已加入流水线' : '翻译完成', 'ok');
      if (r.message) addSubtitle(r.message);
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#manualSend')?.addEventListener('click', sendManual);
  $('#manualInput')?.addEventListener('keydown', e => { if (e.key === 'Enter') sendManual(); });

  // 过滤
  $$('#feedFilter .seg').forEach(btn => btn.addEventListener('click', () => {
    $$('#feedFilter .seg').forEach(x => x.classList.toggle('is-active', x === btn));
    S.filter = btn.dataset.filter;
    applyFeedFilter();
  }));

  // 字幕条
  $('#overlayTest')?.addEventListener('click', () => testOverlay(S.lastSub?.trans));
  $('#overlayTest2')?.addEventListener('click', () => testOverlay(S.lastSub?.trans));

  // 日志导出
  $('#exportLogs')?.addEventListener('click', exportLogs);
  $('#exportLogs2')?.addEventListener('click', exportLogs);

  // 语音
  $('#asrToggle')?.addEventListener('click', toggleAsr);
  $('#refreshDevices')?.addEventListener('click', refreshDevices);
  $('#prepareModel')?.addEventListener('click', prepareModel);

  // 屏幕
  $('#captureScreen')?.addEventListener('click', openRegionModal);
  $('#previewRegion')?.addEventListener('click', previewCurrentRegion);
  $('#applyVision')?.addEventListener('click', applyVision);
  $('#regionImage')?.addEventListener('load', positionOcrBoxes);

  // 手机
  $('#openPhone')?.addEventListener('click', async () => {
    if (S.previewMode) return toast('预览模式：服务未启动', '');
    const r = await call('open_phone_page');
    if (r.ok) toast('已在浏览器打开手机端页面', 'ok');
  });
  $('#sendClip')?.addEventListener('click', async () => {
    const text = $('#clipText').value.trim();
    if (!text) return toast('剪贴板内容为空', '');
    if (S.previewMode) return toast('预览模式：服务未启动', '');
    const r = await call('send_clipboard', text);
    if (r.ok) { $('#clipText').value = ''; toast('已发送到手机剪贴板', 'ok'); }
    else toast(r.error || '发送失败', 'err');
  });
  $$('[data-copy]').forEach(btn => btn.addEventListener('click', () => {
    const target = document.getElementById(btn.dataset.copy);
    if (target) copyText(target.textContent);
  }));

  // 引擎
  $$('.engine-option').forEach(el => el.addEventListener('click', async () => {
    S.cfg.translator = el.dataset.engine;
    updateEngineUI(el.dataset.engine);
    setText('heroEngine', ENGINE_LABEL[el.dataset.engine] || '');
    queueSave({ translator: el.dataset.engine });
    toast(`引擎：${ENGINE_LABEL[el.dataset.engine]}${el.dataset.engine === 'free' ? ' · 点击「应用引擎」生效' : ''}`, '', 1800);
  }));
  $('#applyTranslator')?.addEventListener('click', () => applyTranslator(false));
  $('#runTest')?.addEventListener('click', runTest);
  $('#testInput')?.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runTest(); });

  // 系统
  $('#openFolder')?.addEventListener('click', async () => {
    if (S.previewMode) return;
    const r = await call('open_data_folder');
    if (r.ok) toast('已打开数据目录', 'ok');
  });

  // OCR 语言提示
  $('#ocrLang')?.addEventListener('change', () => {
    const lang = $('#ocrLang').value;
    setText('ocrEnginePill', (S.constants.ocr_langs?.[lang]?.engine) || 'PP-OCRv6');
  });
}

async function toggleService() {
  if (S.previewMode) {
    S.state.running = !S.state.running;
    S.state.starting = false;
    S.state.status = S.state.running ? 'running' : 'idle';
    S.state.status_text = S.state.running ? '预览运行中' : '已暂停';
    if (S.state.running && !S.subs.length) {
      const demo = {
        id: 4, ts: Date.now(), lang: 'ja', conf: .98, src: 'Yamato: おっす、今日もランク行こうぜ！',
        trans: '哟，今天也去打排位吧。', engine: 'free', source: 'ocr', mode: 'translate'
      };
      addSubtitle(demo);
    }
    updateState();
    return;
  }
  try {
    await flushSave();
    const r = await call('toggle_all');
    if (!r.ok) toast(r.error || '操作失败', 'err');
    else {
      await sleep(160);
      const st = await call('get_state', S.subCursor, S.logCursor);
      if (st.ok) applyDelta(st);
    }
  } catch (e) { toast(e.message, 'err'); }
}

async function applyTranslator(silent = false) {
  if (S.previewMode) { if (!silent) toast('预览模式：引擎设置仅演示', ''); return; }
  await flushSave();
  try {
    const r = await call('apply_translator');
    if (r.ok) { if (!silent) toast('翻译引擎已应用', 'ok'); }
    else if (!silent) toast(r.error || '应用失败', 'err');
  } catch (e) { if (!silent) toast(e.message, 'err'); }
}

async function runTest() {
  const input = $('#testInput');
  const text = input.value.trim();
  if (!text) return toast('先输入一句要翻译的话', '');
  if (S.previewMode) {
    setText('testOutput', '推进中路，我们需要一个辅助。');
    setText('testMeta', 'FREE · EN → 中文');
    setText('testMs', '186 ms');
    return;
  }
  const btn = $('#runTest');
  btn.disabled = true;
  btn.textContent = '翻译中…';
  try {
    const r = await call('test_translate', text);
    if (!r.ok) throw new Error(r.error || '翻译失败');
    setText('testOutput', r.trans || r.src);
    setText('testMeta', `${(r.engine || '').toUpperCase()} · ${(r.lang || '??').toUpperCase()} → ${currentTargetLabel()}${r.degraded ? ' · 原文' : ''}`);
    setText('testMs', `${r.elapsed_ms || 0} ms`);
  } catch (e) { toast(e.message, 'err'); }
  finally {
    btn.disabled = false;
    btn.innerHTML = '运行 <svg><use href="#i-chevron"/></svg>';
  }
}

async function exportLogs() {
  if (S.previewMode) return toast('预览模式：日志未落盘', '');
  try {
    const r = await call('export_logs');
    if (r.ok) toast(`日志已导出：${r.path}`, 'ok', 4200);
    else toast(r.error || '导出失败', 'err');
  } catch (e) { toast(e.message, 'err'); }
}

/* ============================================================
   Voice / ASR
   ============================================================ */
async function refreshDevices() {
  if (S.previewMode) return toast('预览模式：设备为示例', '');
  try {
    const r = await call('asr_devices');
    if (!r.ok) return toast(r.error || '读取设备失败', 'err');
    S.devices = r.devices || [];
    fillDevices();
    toast(`发现 ${S.devices.length} 个音频设备`, 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

async function refreshModels() {
  try {
    const r = await call('asr_models');
    if (r.ok && r.models) {
      S.models = r.models;
      updateModelState();
    }
  } catch (_) {}
}

async function prepareModel() {
  if (S.previewMode) return toast('预览模式：模型已就绪', 'ok');
  try {
    const r = await call('asr_prepare', $('#asrModel').value);
    if (r.ok) toast(r.preparing ? '正在检查 / 下载模型，首次约 145 MB' : '模型已就绪', 'ok', 3800);
    else toast(r.error || '准备失败', 'err');
    refreshModels();
  } catch (e) { toast(e.message, 'err'); }
}

async function toggleAsr() {
  if (S.previewMode) {
    const asr = S.state.asr;
    asr.running = !asr.running;
    asr.status = asr.running ? 'listening' : 'idle';
    asr.detail = asr.running ? '预览聆听中' : '预览停止';
    updateState();
    return;
  }
  const running = S.state?.asr?.running || ['listening','transcribing','preparing'].includes(S.state?.asr?.status);
  if (running) {
    const r = await call('asr_stop');
    if (!r.ok) toast(r.error || '停止失败', 'err');
    if (r.ok && S.state?.voice_only) {
      await call('stop_all');
      toast('语音模式已停止', '');
    }
    return;
  }
  await flushSave();
  if (!S.state?.running) {
    toast('正在启动语音模式…', '');
    await call('start_voice');
    const ok = await waitForRunning(30000);
    if (!ok) return toast('语音服务启动失败', 'err');
  }
  const device = $('#asrDevice').value;
  if (!device) return toast('没有可用音频设备，请刷新设备或检查驱动', 'err');
  const r = await call('asr_start', device, $('#asrModel').value, $('#asrLang').value, Number($('#asrChunk').value));
  if (!r.ok) return toast(r.error || '启动失败', 'err');
  toast('语音识别已启动 · 音频只在本机处理', 'ok');
  refreshModels();
}

async function waitForRunning(timeout = 20000) {
  const t0 = performance.now();
  while (performance.now() - t0 < timeout) {
    try {
      const r = await call('get_state', S.subCursor, S.logCursor);
      if (r.ok) { applyDelta(r); if (S.state?.running) return true; }
    } catch (_) {}
    await sleep(400);
  }
  return false;
}

let levelTimer = null;
function startLevelPolling() {
  if (S.previewMode) { startPreviewLevels(); return; }
  clearInterval(levelTimer);
  levelTimer = setInterval(async () => {
    if (S.asrLevelBusy) return;
    const asr = S.state?.asr;
    if (!asr || (!asr.running && !['listening','transcribing','preparing'].includes(asr.status))) return;
    S.asrLevelBusy = true;
    try {
      const r = await call('get_levels');
      if (r.ok) {
        S.levels = r.levels || [];
        S.levelStatus = r;
        if (S.state?.asr) {
          S.state.asr.status = r.status || S.state.asr.status;
          S.state.asr.detail = r.detail || S.state.asr.detail;
          S.state.asr.error = r.error || '';
          S.state.asr.running = r.status !== 'idle' && r.status !== 'error';
        }
        updateAsrLive();
      }
    } catch (_) {} finally { S.asrLevelBusy = false; }
  }, 240);
}

function startPreviewLevels() {
  let t = 0;
  setInterval(() => {
    t += .08;
    const base = S.state?.asr?.running ? .35 : .08;
    S.levels = Array.from({ length: 48 }, (_, i) =>
      clamp(base + Math.abs(Math.sin(i * .28 + t)) * (S.state?.asr?.running ? .55 : .12) * (1 + Math.sin(i * .9 + t * 1.3) * .3), 0, 1));
  }, 100);
}

function updateAsrLive() {
  const st = S.levelStatus;
  if (!st) return;
  const statusMap = {
    idle: '语音识别未启动', ready: '语音模型已就绪', preparing: '正在准备语音模型',
    listening: '正在聆听', transcribing: '正在转写…', stopping: '正在停止…', error: '语音识别出错'
  };
  setText('asrStateText', statusMap[st.status] || st.status);
  setText('asrDetailText', st.detail || st.error || '音频只在本机处理');
  $('#voiceMicRing')?.classList.toggle('on', ['listening','transcribing','preparing'].includes(st.status));
  const asrOn = ['listening','transcribing','preparing'].includes(st.status);
  setText('orbState', st.status === 'transcribing' ? 'TRANSCRIBING' : asrOn ? 'LISTENING' : (S.state?.running ? 'LIVE' : 'IDLE'));
  $('#orb')?.classList.toggle('running', asrOn || !!S.state?.running);
}

/* ============================================================
   Vision / region
   ============================================================ */
async function openRegionModal() {
  if (S.previewMode) {
    toast('预览模式：无法截取桌面', '');
    return;
  }
  try {
    toast('正在截取桌面…', '', 1200);
    const r = await call('screen_capture', true);
    if (!r.ok) throw new Error(r.error || '截图失败');
    S.regionShot = r;
    S.selection = null;
    $('#regionPickImg').src = r.image;
    $('#pickRect').hidden = true;
    $('#confirmRegion').disabled = true;
    $('#pickSize').textContent = '0 × 0';
    $('#pickCoords').textContent = '—';
    $('#pickHint').textContent = '按住鼠标拖拽，框住聊天文字所在的矩形';
    $('#regionModal').hidden = false;
    requestAnimationFrame(() => {
      const img = $('#regionPickImg');
      img.style.opacity = 1;
    });
  } catch (e) { toast(e.message, 'err'); }
}

function closeRegionModal() {
  $('#regionModal').hidden = true;
  S.selection = null;
}
function initRegionDrag() {
  const pick = $('#regionPick');
  const img = $('#regionPickImg');
  let dragging = false, start = null;

  const imgRect = () => img.getBoundingClientRect();
  const containerRect = () => pick.getBoundingClientRect();

  function point(e) {
    const r = imgRect();
    return {
      x: clamp(e.clientX - r.left, 0, r.width),
      y: clamp(e.clientY - r.top, 0, r.height),
      rw: r.width, rh: r.height
    };
  }
  function draw(a, b) {
    const rect = imgRect(), crect = containerRect();
    const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    const w = Math.abs(a.x - b.x), h = Math.abs(a.y - b.y);
    const el = $('#pickRect');
    el.hidden = false;
    el.style.left = `${rect.left - crect.left + x}px`;
    el.style.top = `${rect.top - crect.top + y}px`;
    el.style.width = `${w}px`;
    el.style.height = `${h}px`;
    $('#pickSize').textContent = `${Math.round(w / rect.width * S.regionShot.width)} × ${Math.round(h / rect.height * S.regionShot.height)}`;
    const absX = Math.round(S.regionShot.left + x / rect.width * S.regionShot.width);
    const absY = Math.round(S.regionShot.top + y / rect.height * S.regionShot.height);
    const absW = Math.round(w / rect.width * S.regionShot.width);
    const absH = Math.round(h / rect.height * S.regionShot.height);
    S.selection = { x: absX, y: absY, w: absW, h: absH };
    $('#pickCoords').textContent = `x ${absX}  y ${absY}  ·  ${absW} × ${absH}`;
    $('#confirmRegion').disabled = w < 20 || h < 20;
  }
  pick.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const r = imgRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) return;
    e.preventDefault();
    dragging = true;
    start = point(e);
    draw(start, start);
    $('#pickHint').textContent = '松开鼠标完成框选';
    pick.setPointerCapture?.(e.pointerId);
  });
  pick.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    draw(start, point(e));
  });
  pick.addEventListener('pointerup', (e) => {
    if (!dragging) return;
    dragging = false;
    draw(start, point(e));
    $('#pickHint').textContent = '回车确认 · Esc 取消';
  });
  $('#confirmRegion').addEventListener('click', confirmRegion);
  $('#cancelRegion').addEventListener('click', closeRegionModal);
  $('#closeRegionModal').addEventListener('click', closeRegionModal);
}

async function confirmRegion() {
  if (!S.selection) return;
  const sel = S.selection;
  closeRegionModal();
  try {
    const r = await call('apply_region', sel.x, sel.y, sel.w, sel.h);
    if (!r.ok) return toast(r.error || '应用区域失败', 'err');
    S.cfg = r.config;
    if (r.phone) { S.phone = r.phone; updatePhoneUI(); }
    setText('regionCoords', `${sel.x}, ${sel.y} · ${sel.w} × ${sel.h}`);
    setText('regionSource', 'SCREEN · 屏幕区域');
    setVal('demoMode', false);
    S.cfg.ocr_source = 'screen';
    toast('聊天区域已应用 · 正在加载 OCR', 'ok');
    updateSetup();
    setTimeout(previewCurrentRegion, 600);
  } catch (e) { toast(e.message, 'err'); }
}

async function previewCurrentRegion() {
  if (S.previewMode) {
    toast('预览模式：识别结果仅演示', '');
    return;
  }
  try {
    const r = await call('preview_region');
    if (!r.ok) throw new Error(r.error || '预览失败');
    const img = $('#regionImage');
    S.ocrBoxes = (r.lines || []).map(l => ({ box: l.box, score: l.score }));
    img.onload = () => requestAnimationFrame(positionOcrBoxes);
    img.src = r.image;
    img.hidden = false;
    $('#regionEmpty')?.classList.add('hidden');
    $('#regionElapsed').textContent = `${r.elapsed_ms} ms`;
    renderOcrResult(r.lines || [], r.elapsed_ms);
    requestAnimationFrame(positionOcrBoxes);
    setText('regionCoords', `${r.region[0]}, ${r.region[1]} · ${r.region[2]} × ${r.region[3]}`);
    toast(`识别到 ${r.lines.length} 行文字 · ${r.elapsed_ms} ms`, 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

function renderOcrResult(lines, ms) {
  const wrap = $('#ocrLines');
  if (!wrap) return;
  wrap.innerHTML = '';
  setText('ocrCount', `${lines.length} 行`);
  if (!lines.length) {
    wrap.innerHTML = '<div class="muted-line">这个区域没有识别到文字。试着把框拉大一点，或降低置信度阈值。</div>';
    return;
  }
  lines.forEach(l => {
    const row = document.createElement('div');
    row.className = 'ocr-line';
    row.innerHTML = `<span class="ol-score">${(l.score * 100).toFixed(0)}</span><span></span>`;
    row.lastElementChild.textContent = l.text;
    wrap.appendChild(row);
  });
}

function positionOcrBoxes() {
  const img = $('#regionImage');
  const boxes = $('#ocrBoxes');
  const frame = $('#regionFrame');
  if (!img || !boxes || !frame || img.hidden) return;
  const ir = img.getBoundingClientRect();
  const fr = frame.getBoundingClientRect();
  boxes.style.left = `${ir.left - fr.left}px`;
  boxes.style.top = `${ir.top - fr.top}px`;
  boxes.style.width = `${ir.width}px`;
  boxes.style.height = `${ir.height}px`;
  boxes.innerHTML = '';
  const natW = img.naturalWidth || ir.width, natH = img.naturalHeight || ir.height;
  S.ocrBoxes.forEach(o => {
    const b = o.box || [0,0,0,0];
    const el = document.createElement('div');
    el.className = 'ocr-box';
    el.dataset.score = `${Math.round((o.score || 0) * 100)}%`;
    el.style.left = `${b[0] / natW * 100}%`;
    el.style.top = `${b[1] / natH * 100}%`;
    el.style.width = `${b[2] / natW * 100}%`;
    el.style.height = `${b[3] / natH * 100}%`;
    boxes.appendChild(el);
  });
}

async function applyVision() {
  if (S.previewMode) return toast('预览模式：设置仅演示', '');
  const lang = $('#ocrLang').value;
  await flushSave();
  try {
    toast('应用识别设置…', '', 1600);
    if (!lang || lang === 'auto' || lang === 'ch') {
      // 内置模型
    } else {
      const warm = await call('ocr_warmup', lang);
      if (!warm.ok) throw new Error(warm.error || '模型加载失败');
    }
    const r = await call('apply_vision');
    if (!r.ok) throw new Error(r.error || '应用失败');
    S.cfg.ocr_lang = lang;
    updateOcrPill();
    toast(r.deferred ? '设置已保存，启动后生效' : '识别设置已生效', 'ok');
    if (S.state?.running) setTimeout(previewCurrentRegion, 500);
  } catch (e) { toast(e.message, 'err', 3800); }
}

/* ============================================================
   Navigation
   ============================================================ */
function debounce(fn, ms = 200) {
  let t = 0;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
const VALID_PAGES = ['overview', 'live', 'voice', 'vision', 'mobile', 'engine', 'appearance', 'about'];

function initNav() {
  $$('.nav-item').forEach(item => item.addEventListener('click', () => navTo(item.dataset.page)));
  document.addEventListener('click', (e) => {
    const nav = e.target.closest('[data-nav]');
    if (nav) {
      const page = nav.dataset.nav;
      if (page) { e.preventDefault(); navTo(page); }
    }
  });
  window.addEventListener('resize', debounce(() => {
    updateNavPill();
    positionOcrBoxes();
    particles.resize();
  }, 120));
  window.addEventListener('hashchange', () => {
    const page = (location.hash || '#overview').slice(1);
    if (VALID_PAGES.includes(page) && page !== S.page) navTo(page, false);
  });
  requestAnimationFrame(updateNavPill);
}

function navTo(page, scroll = true) {
  if (!VALID_PAGES.includes(page)) page = 'overview';
  S.page = page;
  $$('.page').forEach(el => el.classList.toggle('is-active', el.id === `page-${page}`));
  $$('.nav-item').forEach(el => {
    const active = el.dataset.page === page;
    el.classList.toggle('is-active', active);
    el.setAttribute('aria-current', active ? 'page' : 'false');
  });
  updateNavPill();
  if (scroll) $('#viewport')?.scrollTo({ top: 0, behavior: 'smooth' });
  if (page === 'voice') requestAnimationFrame(resizeVoiceCanvas);
  if (page === 'vision') requestAnimationFrame(positionOcrBoxes);
  try { history.replaceState(null, '', `#${page}`); } catch (_) {}
}

function updateNavPill() {
  const pill = $('#navPill');
  if (!pill) return;
  const active = $('.nav-item.is-active');
  if (!active) return;
  const nav = $('#nav');
  const nr = nav.getBoundingClientRect();
  const ar = active.getBoundingClientRect();
  pill.style.top = `${ar.top - nr.top}px`;
  pill.style.height = `${ar.height}px`;
  pill.style.opacity = '1';
}

/* ============================================================
   Window chrome
   ============================================================ */
function initWindowControls() {
  $$('[data-win]').forEach(btn => btn.addEventListener('click', async () => {
    const act = btn.dataset.win;
    if (!apiAvailable()) return toast('窗口控制仅在桌面应用中可用', '');
    try {
      if (act === 'close') await call('window_close');
      if (act === 'min') await call('window_minimize');
      if (act === 'max') await call('window_toggle_max');
    } catch (e) { toast(e.message, 'err'); }
  }));

  $('.drag-fill')?.addEventListener('dblclick', async () => {
    if (!apiAvailable()) return;
    try { await call('window_toggle_max'); } catch (_) {}
  });

  const grip = $('#resizeGrip');
  if (grip) {
    let manual = false, sx = 0, sy = 0, sw = 0, sh = 0, lastW = 0, lastH = 0, pending = false;
    grip.addEventListener('pointerdown', async (e) => {
      e.preventDefault();
      if (!apiAvailable()) return;
      grip.setPointerCapture?.(e.pointerId);
      try {
        const r = await call('window_start_resize');
        if (!r.ok) throw new Error(r.error || 'native resize unavailable');
      } catch (_) {
        manual = true; sx = e.screenX; sy = e.screenY; sw = innerWidth; sh = innerHeight;
        lastW = sw; lastH = sh;
      }
    });
    grip.addEventListener('pointermove', (e) => {
      if (!manual || pending) return;
      const w = Math.max(1080, Math.round(sw + (e.screenX - sx)));
      const h = Math.max(700, Math.round(sh + (e.screenY - sy)));
      if (w === lastW && h === lastH) return;
      lastW = w; lastH = h; pending = true;
      call('window_resize', w, h).finally(() => { pending = false; });
    });
    grip.addEventListener('pointerup', () => { manual = false; });
  }
}

/* ============================================================
   Modals / command palette
   ============================================================ */
function initModals() {
  initRegionDrag();
  $('#regionModal')?.addEventListener('pointerdown', (e) => {
    if (e.target === $('#regionModal')) closeRegionModal();
  });
  $('#cmdModal')?.addEventListener('pointerdown', (e) => {
    if (e.target === $('#cmdModal')) closeCmd();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (!$('#cmdModal').hidden) closeCmd();
      else if (!$('#regionModal').hidden) closeRegionModal();
    }
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if ($('#cmdModal').hidden) openCmd(); else closeCmd();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && S.page === 'overview') {
      e.preventDefault();
      toggleService();
    }
  });
  $('#regionPickImg')?.addEventListener('load', () => {
    $('#regionPickImg').style.opacity = 1;
  });
}

const COMMANDS = [];
function initCommandPalette() {
  COMMANDS.length = 0;
  const pageCmds = [
    ['overview', 'i-grid', '打开概览', '总览与实时状态'],
    ['live', 'i-captions', '打开实时字幕', '查看完整字幕流'],
    ['voice', 'i-mic', '打开语音识别', '语音转文字'],
    ['vision', 'i-scan', '打开屏幕识别', 'OCR 与区域圈选'],
    ['mobile', 'i-phone', '打开手机接力', '二维码与剪贴板'],
    ['engine', 'i-globe', '打开翻译引擎', '引擎与目标语言'],
    ['appearance', 'i-sliders', '打开外观与字幕', '主题、粒子、字幕条'],
    ['about', 'i-info', '打开关于', '隐私与版本'],
  ];
  pageCmds.forEach(([page, icon, label, hint]) => COMMANDS.push({ icon, label, hint, run: () => navTo(page) }));
  COMMANDS.push(
    { icon: 'i-play', label: '开始 / 停止翻译', hint: '切换主服务', run: toggleService },
    { icon: 'i-mic', label: '开始 / 停止语音识别', hint: 'Whisper 本地转写', run: toggleAsr },
    { icon: 'i-scan', label: '截取屏幕并圈选', hint: '框住游戏聊天区域', run: openRegionModal },
    { icon: 'i-eye', label: '测试屏幕识别', hint: '立即识别当前区域', run: previewCurrentRegion },
    { icon: 'i-eye', label: '预览字幕条', hint: '在桌面上显示一条字幕', run: () => testOverlay(S.lastSub?.trans) },
    { icon: 'i-down', label: '导出日志', hint: '保存到数据目录', run: exportLogs },
    { icon: 'i-trash', label: '清空字幕流', hint: '仅清空本次会话', run: async () => { const r = await call('clear_feed'); if (r.ok) { S.subs = []; renderInitial(); toast('已清空', 'ok'); } } },
    { icon: 'i-spark', label: '切换主题', hint: '午夜 / 晨光', run: () => {
      S.cfg.theme = S.cfg.theme === 'dark' ? 'light' : 'dark';
      applyAppearance();
      queueSave({ theme: S.cfg.theme });
      toast(`主题：${S.cfg.theme === 'dark' ? '午夜' : '晨光'}`, '', 1600);
    } },
  );
  $('#cmdBtn')?.addEventListener('click', openCmd);
  $('#tbCmd')?.addEventListener('click', openCmd);
  $('#cmdInput')?.addEventListener('input', () => renderCmd($('#cmdInput').value));
  $('#cmdInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); moveCmd(1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); moveCmd(-1); }
    if (e.key === 'Enter') { e.preventDefault(); runCmd(S.cmdItems[S.cmdIndex]); }
  });
}

function openCmd() {
  const modal = $('#cmdModal');
  if (!modal) return;
  modal.hidden = false;
  const input = $('#cmdInput');
  input.value = '';
  renderCmd('');
  setTimeout(() => input.focus(), 60);
}
function closeCmd() { const m = $('#cmdModal'); if (m) m.hidden = true; }

function renderCmd(query) {
  const list = $('#cmdList');
  if (!list) return;
  const q = (query || '').trim().toLowerCase();
  S.cmdItems = COMMANDS.filter(c => !q || `${c.label} ${c.hint}`.toLowerCase().includes(q));
  S.cmdIndex = 0;
  list.innerHTML = '';
  if (!S.cmdItems.length) {
    list.innerHTML = '<div class="muted-line" style="padding:18px">没有匹配的命令</div>';
    return;
  }
  S.cmdItems.forEach((cmd, i) => {
    const btn = document.createElement('button');
    btn.className = `cmd-item${i === 0 ? ' is-active' : ''}`;
    btn.innerHTML = `<svg><use href="#${cmd.icon}"/></svg><span></span><kbd>↵</kbd>`;
    btn.querySelector('span').textContent = `${cmd.label} · ${cmd.hint}`;
    btn.addEventListener('mouseenter', () => { S.cmdIndex = i; markCmd(); });
    btn.addEventListener('click', () => runCmd(cmd));
    list.appendChild(btn);
  });
}
function markCmd() {
  $$('#cmdList .cmd-item').forEach((el, i) => el.classList.toggle('is-active', i === S.cmdIndex));
}
function moveCmd(dir) {
  if (!S.cmdItems.length) return;
  S.cmdIndex = (S.cmdIndex + dir + S.cmdItems.length) % S.cmdItems.length;
  markCmd();
  $$('#cmdList .cmd-item')[S.cmdIndex]?.scrollIntoView({ block: 'nearest' });
}
async function runCmd(cmd) {
  if (!cmd) return;
  closeCmd();
  try { await cmd.run(); } catch (e) { toast(e.message || '命令执行失败', 'err'); }
}
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


