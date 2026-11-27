/* 游戏字幕翻译 · 手机端 */
const $ = (id) => document.getElementById(id);

const LANG_LABEL = {
  en:"EN", ja:"JA", ko:"KO", ru:"RU", de:"DE", fr:"FR", es:"ES",
  pt:"PT", tr:"TR", ar:"AR", vi:"VI", th:"TH", zh:"中", unknown:"??"
};

let ws = null;
let pair = "";
let autoScroll = true;
let fontSize = 17;
let deferredInstall = null;
let displayMode = "both";
let lastSub = null;

/* ---------- 工具 ---------- */
function toast(msg, ms = 1800) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), ms);
}

function hhmm(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}

async function copyText(text) {
  if (!text) return;
  // 安卓 WebView 壳：优先走原生剪贴板桥接
  if (window.GTBridge && typeof GTBridge.copyText === "function") {
    GTBridge.copyText(text);
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制");
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand("copy"); toast("已复制"); }
    catch { toast("复制失败，请长按选择"); }
    ta.remove();
  }
}

/* ---------- 扫码配对 ---------- */
function applyPairPayload(raw) {
  const text = (raw || "").trim();
  let relay = "";
  let code = "";
  try {
    const u = new URL(text, location.href);
    relay = u.searchParams.get("relay") || "";
    code = u.searchParams.get("pair") || "";
  } catch (_) {}
  if (!relay || !code) {
    const m = text.match(/relay=([^&\s]+).*?pair=([^&\s]+)/i);
    if (m) {
      relay = decodeURIComponent(m[1]);
      code = decodeURIComponent(m[2]);
    }
  }
  if (!relay || !code) {
    toast("二维码里没有配对信息");
    return false;
  }
  $("relay-url").value = relay;
  $("pair-code").value = code.toUpperCase();
  history.replaceState(null, "", location.pathname +
    "?relay=" + encodeURIComponent(relay) + "&pair=" + encodeURIComponent(code));
  $("join-status").textContent = "已识别二维码，正在连接…";
  setTimeout(connect, 180);
  return true;
}

async function decodeQrImage(file) {
  const bitmap = await createImageBitmap(file);
  const maxSide = 1600;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();

  if (window.jsQR) {
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const hit = jsQR(data.data, data.width, data.height, {
      inversionAttempts: "attemptBoth",
    });
    if (hit?.data) return hit.data;
  }
  // 部分浏览器自带条码识别；失败时回退到 jsQR 的库解码。
  if ("BarcodeDetector" in window) {
    try {
      const detector = new BarcodeDetector({ formats: ["qr_code"] });
      const codes = await detector.detect(canvas);
      if (codes.length && codes[0].rawValue) return codes[0].rawValue;
    } catch (_) {}
  }
  return "";
}

async function scanQrFile(file) {
  if (!file) return;
  try {
    $("join-status").textContent = "正在识别二维码…";
    const text = await decodeQrImage(file);
    if (!text) {
      $("join-status").textContent = "没识别到二维码，请靠近一点重拍";
      return;
    }
    applyPairPayload(text);
  } catch (e) {
    $("join-status").textContent = "读取图片失败：" + (e.message || "未知错误");
  }
}

/* ---------- 字幕模式 ---------- */
function setDisplayMode(mode) {
  displayMode = mode === "phone" ? "phone" : "both";
  $("chat")?.classList.toggle("phone-mode", displayMode === "phone");
  $("modeBanner")?.classList.toggle("hidden", displayMode !== "phone");
  if (displayMode !== "phone") {
    $("live")?.classList.add("hidden");
  } else if (lastSub) {
    updateLive(lastSub);
  }
}

function updateLive(msg) {
  const live = $("live");
  if (!live || displayMode !== "phone") return;
  const badge = $("liveBadge");
  const lang = msg.lang || "unknown";
  badge.textContent = "LIVE";
  badge.className = "badge live";
  $("liveTime").textContent = (LANG_LABEL[lang] || lang.toUpperCase()) + " · " + hhmm(msg.ts);
  $("liveTrans").textContent = msg.trans || msg.src || "";
  $("liveSrc").textContent = msg.src || "";
  live.classList.remove("hidden");
}

/* ---------- 粒子背景 ---------- */
function startParticles() {
  const canvas = $("particles");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W, H, parts = [];

  function resize() {
    W = canvas.width = innerWidth * devicePixelRatio;
    H = canvas.height = innerHeight * devicePixelRatio;
    canvas.style.width = innerWidth + "px";
    canvas.style.height = innerHeight + "px";
  }
  resize();
  addEventListener("resize", resize);

  const N = reduced ? 0 : Math.min(28, Math.floor(innerWidth / 18));
  function spawn(init) {
    return {
      x: Math.random() * W,
      y: init ? Math.random() * H : H + 10,
      r: (Math.random() * 2.2 + 1.1) * devicePixelRatio,
      vy: (Math.random() * 0.35 + 0.15) * devicePixelRatio,
      vx: (Math.random() - 0.5) * 0.15 * devicePixelRatio,
      a: Math.random() * 0.35 + 0.12,
      hue: Math.random() > 0.5 ? "0,113,227" : "255,255,255",
      sway: Math.random() * Math.PI * 2,
    };
  }
  for (let i = 0; i < N; i++) parts.push(spawn(true));

  let raf = 0;
  function tick() {
    ctx.clearRect(0, 0, W, H);
    for (const p of parts) {
      p.sway += 0.01;
      p.y -= p.vy;
      p.x += p.vx + Math.sin(p.sway) * 0.2 * devicePixelRatio;
      if (p.y < -10) Object.assign(p, spawn(false));
      if (p.x < -10) p.x = W + 10;
      if (p.x > W + 10) p.x = -10;
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 3);
      grad.addColorStop(0, `rgba(${p.hue},${p.a})`);
      grad.addColorStop(1, `rgba(${p.hue},0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2);
      ctx.fill();
    }
    raf = requestAnimationFrame(tick);
  }
  if (!reduced) tick();

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else if (!reduced) tick();
  });
}

/* ---------- 渲染 ---------- */
function renderSubtitle(msg) {
  lastSub = msg;
  updateLive(msg);
  $("empty").classList.add("hidden");
  const list = $("subtitle-list");

  const row = document.createElement("div");
  row.className = "row" + (msg.retry ? " retry" : "");

  const meta = document.createElement("div");
  meta.className = "meta";
  const badge = document.createElement("span");
  const lg = msg.lang || "unknown";
  badge.className = "badge" + (LANG_LABEL[lg] ? "" : " unknown");
  badge.textContent = LANG_LABEL[lg] || lg.toUpperCase();
  const time = document.createElement("span");
  time.className = "time";
  time.textContent = hhmm(msg.ts) + (msg.retry ? " · 重译" : "");
  meta.append(badge, time);

  const src = document.createElement("div");
  src.className = "src";
  src.textContent = msg.src || "";

  const trans = document.createElement("div");
  trans.className = "trans";
  trans.textContent = msg.trans || "";

  const acts = document.createElement("div");
  acts.className = "acts";
  const bCopy = document.createElement("button");
  bCopy.textContent = "复制译文";
  bCopy.onclick = () => copyText(msg.trans);
  const bCopySrc = document.createElement("button");
  bCopySrc.textContent = "复制原文";
  bCopySrc.onclick = () => copyText(msg.src);
  const bRetry = document.createElement("button");
  bRetry.textContent = "重译";
  bRetry.onclick = () => {
    if (!ws || ws.readyState !== 1) return toast("未连接");
    ws.send(JSON.stringify({ type:"translate_request", src: msg.src, lang: msg.lang }));
    toast("已请求重译");
  };
  acts.append(bCopy, bCopySrc, bRetry);

  row.append(meta, src, trans, acts);
  list.appendChild(row);

  while (list.children.length > 200) list.firstChild.remove();
  if (autoScroll) list.scrollTop = list.scrollHeight;
}

/* ---------- 连接 ---------- */
function setConn(on) {
  const dot = $("conn-dot");
  dot.className = "dot " + (on ? "on" : "off");
}

function connect() {
  const url = $("relay-url").value.trim();
  const code = $("pair-code").value.trim().toUpperCase();
  if (!url) return ($("join-status").textContent = "请填写中继地址");
  if (!code) return ($("join-status").textContent = "请填写配对码");

  $("join-status").textContent = "连接中…";
  try { ws = new WebSocket(url); }
  catch { $("join-status").textContent = "地址格式错误"; return; }

  ws.onopen = () => {
    ws.send(JSON.stringify({ type:"hello", pair: code, role:"phone" }));
    $("join-status").textContent = "";
  };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    switch (msg.type) {
      case "paired":
        pair = msg.pair;
        $("pair-tag").textContent = "配对 " + pair;
        setConn(true);
        setDisplayMode(msg.display_mode || displayMode);
        $("join").classList.add("hidden");
        $("chat").classList.remove("hidden");
        localStorage.setItem("gt_relay", $("relay-url").value.trim());
        localStorage.setItem("gt_pair", code);
        toast("已连接电脑");
        // 拉一次完整状态，确保在独占全屏中重连时立刻切到手机字幕。
        setTimeout(() => {
          if (ws?.readyState === 1) ws.send(JSON.stringify({ type: "status_request" }));
        }, 120);
        break;
      case "subtitle":
        renderSubtitle(msg);
        break;
      case "display_mode":
        setDisplayMode(msg.mode);
        if (msg.mode === "phone") toast("已切换到手机字幕模式");
        break;
      case "clipboard":
        navigator.clipboard?.writeText(msg.text || "").catch(() => {});
        toast("收到电脑剪贴板：" + (msg.text || "").slice(0, 24));
        break;
      case "peer_left":
        setConn(false);
        setDisplayMode("both");
        toast("电脑端已断开");
        break;
      case "status":
        if (msg.display_mode) setDisplayMode(msg.display_mode);
        // 状态每 2 秒一次，静默更新，不弹 toast，避免打断手机字幕。
        break;
      case "error":
        $("join-status").textContent = msg.msg || "错误";
        break;
    }
  };
  ws.onerror = () => { $("join-status").textContent = "连接失败，检查地址与配对码"; };
  ws.onclose = () => { setConn(false); };
}

/* ---------- 交互 ---------- */
$("btn-join").onclick = connect;

$("btn-scan").onclick = () => {
  // 局域网页面是 HTTP，浏览器通常不给 live camera；用系统相机拍照后本地解码，
  // 不需要把图片上传到任何服务器。
  if (window.GTBridge && typeof GTBridge.scanQRCode === "function") {
    try {
      GTBridge.scanQRCode();
      return;
    } catch (_) {}
  }
  $("qr-file").click();
};

/* 安卓原生壳：相机拍完把照片以 data URL 回传，仍在本机用 jsQR 解码。 */
window.onNativeScanImage = async (dataUrl) => {
  try {
    $("join-status").textContent = "正在识别二维码…";
    const blob = await (await fetch(dataUrl)).blob();
    const file = new File([blob], "scan.jpg", { type: blob.type || "image/jpeg" });
    await scanQrFile(file);
  } catch (e) {
    $("join-status").textContent = "读取照片失败：" + (e.message || "未知错误");
  }
};

window.onNativeScanCancel = () => {
  $("join-status").textContent = "已取消扫码";
};

window.onNativeScanError = (msg) => {
  $("join-status").textContent = msg || "扫码失败，请重试";
};

$("qr-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  await scanQrFile(file);
});

$("btn-clear").onclick = () => {
  $("subtitle-list").innerHTML = "";
  $("empty").classList.remove("hidden");
  toast("已清空");
};

$("btn-disconnect").onclick = () => {
  ws?.close();
  setDisplayMode("both");
  $("chat").classList.add("hidden");
  $("join").classList.remove("hidden");
};

$("btn-font").onclick = () => {
  fontSize = fontSize >= 24 ? 15 : fontSize + 3;
  document.documentElement.style.setProperty("--fs", fontSize + "px");
  localStorage.setItem("gt_fs", fontSize);
  toast("字号 " + fontSize);
};

$("btn-sync-clip").onclick = async () => {
  if (!ws || ws.readyState !== 1) return toast("未连接");
  try {
    const text = await navigator.clipboard.readText();
    if (!text) return toast("手机剪贴板为空");
    ws.send(JSON.stringify({ type:"clipboard", text, from:"phone" }));
    toast("已同步到电脑剪贴板");
  } catch {
    toast("系统限制了读剪贴板，请长按输入框粘贴后点「翻译」");
  }
};

$("btn-send-manual").onclick = () => {
  const text = $("manual-input").value.trim();
  if (!text) return toast("请输入内容");
  if (!ws || ws.readyState !== 1) return toast("未连接");
  ws.send(JSON.stringify({ type:"translate_request", src: text, lang:"unknown" }));
  $("manual-input").value = "";
  toast("已发送翻译请求");
};

$("manual-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("btn-send-manual").click();
});

$("subtitle-list").addEventListener("scroll", () => {
  const el = $("subtitle-list");
  autoScroll = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
});

/* ---------- PWA：安装到主屏幕 ---------- */
function setupInstall() {
  const btn = $("btn-install");
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e;
    btn.classList.remove("hidden");
  });
  btn.onclick = async () => {
    if (!deferredInstall) {
      toast("用浏览器菜单选择「添加到主屏幕」");
      return;
    }
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall = null;
    btn.classList.add("hidden");
  };
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
}

/* ---------- 初始化（URL 参数自动填充） ---------- */
(function init() {
  startParticles();
  setupInstall();

  const fs = localStorage.getItem("gt_fs");
  if (fs) {
    fontSize = +fs;
    document.documentElement.style.setProperty("--fs", fontSize + "px");
  }

  const p = new URLSearchParams(location.search);
  const relay = p.get("relay") || localStorage.getItem("gt_relay") || "";
  const code = p.get("pair") || localStorage.getItem("gt_pair") || "";

  if (relay) $("relay-url").value = relay;
  if (code) $("pair-code").value = code;

  if (p.get("relay") && code) {
    setTimeout(connect, 300);
  } else if (relay && code) {
    $("join-status").textContent = "已记住上次设置，点「连接」继续";
  }
})();
