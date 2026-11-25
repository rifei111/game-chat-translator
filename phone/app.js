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
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制");
  } catch {
    // 回退：临时 textarea
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("已复制"); }
    catch { toast("复制失败，请长按选择"); }
    ta.remove();
  }
}

/* ---------- 渲染 ---------- */
function renderSubtitle(msg) {
  $("empty").classList.add("hidden");
  const list = $("subtitle-list");

  const row = document.createElement("div");
  row.className = "row" + (msg.retry ? " retry" : "");

  // 顶部：语种 + 时间
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

  // 原文
  const src = document.createElement("div");
  src.className = "src";
  src.textContent = msg.src || "";

  // 译文
  const trans = document.createElement("div");
  trans.className = "trans";
  trans.textContent = msg.trans || "";

  // 操作
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
        $("join").classList.add("hidden");
        $("chat").classList.remove("hidden");
        localStorage.setItem("gt_relay", $("relay-url").value.trim());
        localStorage.setItem("gt_pair", code);
        toast("已连接电脑");
        break;
      case "subtitle":
        renderSubtitle(msg);
        break;
      case "clipboard":
        // PC 复制的文字 → 手机剪贴板 + 提示
        navigator.clipboard?.writeText(msg.text || "").catch(() => {});
        toast("收到电脑剪贴板：" + (msg.text || "").slice(0, 24));
        break;
      case "peer_left":
        setConn(false);
        toast("电脑端已断开");
        break;
      case "status":
        toast(`引擎 ${msg.engine || "-"} · 已推 ${msg.pushed || 0} 条`);
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

$("btn-clear").onclick = () => {
  $("subtitle-list").innerHTML = "";
  $("empty").classList.remove("hidden");
  toast("已清空");
};

$("btn-disconnect").onclick = () => {
  ws?.close();
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

/* ---------- 初始化（URL 参数自动填充） ---------- */
(function init() {
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

  // 扫码进来（带 relay 参数）自动连接
  if (p.get("relay") && code) {
    setTimeout(connect, 300);
  } else if (relay && code) {
    $("join-status").textContent = "已记住上次设置，点「连接」继续";
  }
})();
