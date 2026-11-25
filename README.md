# 外服游戏实时翻译（局域网版）

外服游戏里外国人说的话 → PC 端截屏 OCR → 本地语种识别 → 翻译 → **PC 置顶字幕条** + **手机 App / 网页字幕流**，双向剪贴板同步。全部在同一个 WiFi 内跑通，**不需要公网、不需要云服务器、不需要 VPN**。

<p align="center">
  <img src="docs/phone-subtitles.png" width="300" alt="手机端实时字幕">
  <img src="docs/phone-join.png" width="300" alt="手机端连接页">
</p>

---

## 一、下载与安装

### 安卓手机（推荐）

1. 打开本仓库 **Releases**，下载 `GameTranslator-v0.2.0-debug.apk`
2. 手机允许「安装未知来源应用」后安装
3. 打开 App，填入 PC 终端上显示的中继地址和配对码即可

> 没有上架应用商店；APK 为 debug 签名，首次安装时系统会提示风险，确认即可。
> 不想装 App 也可以：手机浏览器打开 PC 给的网址，菜单里选「添加到主屏幕」，效果等同安装（PWA）。

### Windows PC

两种方式任选：

- **绿色版（免安装）**：在 Windows 上运行一次 `build_installer.bat`，产物在 `dist\GameTranslator\`，整个文件夹拷走即可，双击 `GameTranslator.exe` 启动。
- **单文件安装程序**：装好 [Inno Setup 6](https://jrsoftware.org/isdl.php) 后再运行 `build_installer.bat`，会生成 `GameTranslator-Setup-0.2.0.exe`，下一步下一步安装。

> 安装程序 / 绿色版需要在 **Windows 本机**打包（PyInstaller 不支持跨平台编译）。仓库里的源码在 Linux/macOS 上只能跑开发模式。

---

## 二、快速使用（源码模式）

### 1. 装依赖（只需一次）
双击 **`install.bat`**，或手动：
```bat
python -m pip install -r requirements.txt
```

### 2. 圈选游戏聊天区域（只需一次，换游戏再圈）
1. 先把游戏切到窗口化 / 无边框窗口，让聊天框可见
2. 双击 **`select_region.bat`**，屏幕变暗后**拖拽框住聊天框**，回车确认
   - 取消按 `Esc`
   - 没图形界面时，直接改 `config.json` 的 `region: [x, y, 宽, 高]`

### 3. 启动
双击 **`start.bat`**。终端会打印：

```
========================================================
  游戏聊天实时翻译  ·  局域网模式
========================================================
  配对码      : 3F8A2C
  翻译引擎    : mock   目标语言: zh
  OCR 来源    : screen   区域: [80, 480, 620, 200]
  中继地址    : ws://192.168.1.7:8780
  手机端地址  : http://192.168.1.7:8781/
========================================================
  [二维码]
  手机扫码直接打开（需与电脑同一 WiFi）
========================================================
```

手机连**同一个 WiFi**，扫码（或手动打开那个地址 / 装 APK 填地址），自动填好中继地址和配对码并连接。

---

## 三、配置 `config.json`

首次启动自动生成，改完重启生效。打包后的 exe 配置放在 **exe 同级目录**，不在安装目录里。

| 字段 | 默认 | 说明 |
|---|---|---|
| `pair` | 自动生成 | 配对码；想固定就自己写 6 位字母数字 |
| `translator` | `mock` | **改成 `argos` / `deepl` / `qwen` 才会真的翻译** |
| `deepl_key` | 空 | DeepL API Key（免费版以 `:fx` 结尾自动走 free 域名） |
| `qwen_key` | 空 | 阿里云百炼 API Key（qwen-turbo，OpenAI 兼容协议） |
| `target_lang` | `zh` | 目标语言 |
| `ocr_source` | `screen` | `screen` 真实截图；`demo` 内置样例（验证链路用） |
| `region` | `[80,480,620,200]` | 聊天框圈选区域 `[x, y, w, h]` |
| `poll_interval` | `1.5` | 截图间隔（秒）；越小越实时，越吃 CPU |
| `dedup_window` | `8.0` | 同一句话多少秒内不重复推送（防聊天框重绘刷屏） |
| `overlay` | `true` | PC 字幕条开关；觉得挡画面就设 `false` |
| `overlay_font` | `22` | 字幕字号 |
| `subtitle_ttl` | `8.0` | 字幕停留秒数 |
| `relay_port` / `phone_port` | `8780` / `8781` | 被占用会自动顺延并在终端提示 |

### 选哪个翻译引擎

| 引擎 | 联网 | 花钱 | 质量 | 适合 |
|---|---|---|---|---|
| `argos` | 仅首次下模型 | 免费 | 中等 | 想完全离线、不想给 API 付费 |
| `deepl` | 是 | 按量计费（有免费额度） | 最好 | 追求翻译质量 |
| `qwen` | 是 | 按量计费（很便宜） | 好 | 国内网络稳定、支持小语种上下文 |
| `mock` | 否 | 免费 | 只加前缀不翻译 | 只想验证链路是否通 |

> `argos` 首次使用会后台下载语言包（每个语言对约 100MB，只在第一次），下载期间该语种先显示原文，装好自动生效，不会卡住流水线。

---

## 四、手机端

### 两种形态

- **APK（本仓库 Releases 提供）**：原生壳 + WebView，本地打包网页资源，桌面有图标，全屏启动。
- **PWA 网页**：浏览器打开后「添加到主屏幕」，带图标、启动屏、离线缓存，功能与 APK 一致。

### 功能

- 每行字幕：语种徽章（EN/JA/KO/RU/DE/FR/ES/PT 等）+ 时间
- **复制译文** / **复制原文** / **重译**（重译把原文发回 PC 重新翻译）
- 底部：手动输入一句话点「翻译」（不必等 OCR 抓）
- 「同步剪贴板」：把手机剪贴板内容发到 PC
- 字号切换、清空列表、断开连接；记住上次的地址和配对码
- 背景有低饱和漂浮粒子，跟随系统「减弱动态效果」自动关闭

### 自己编译安卓 APK

`android/` 是完整 Gradle 工程（AGP 7.4.2 / minSdk 24 / 纯 Java，无 Kotlin、无 androidx 依赖）：

```bash
# 需要 Android SDK（platforms;android-33、build-tools;33.0.2）+ JDK 11
cd android
gradle assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

改了 `phone/` 网页后，重新编译前先把 `phone/` 同步到 `android/app/src/main/assets/phone/`（仓库里已随源码保持同步）。

---

## 五、目录结构

```
game-translator/
├── entry.py               PyInstaller 入口
├── GameTranslator.spec    PyInstaller 打包配置
├── installer.iss          Inno Setup 安装程序脚本
├── build_installer.bat    一键打包（绿色版 + 安装程序）
├── start.bat / install.bat / select_region.bat
├── requirements.txt
├── relay/server.py        WebSocket 中继（配对码房间，只转发不落库）
├── lid/                   本地语种识别（lingua）
├── pc/
│   ├── launch.py          一键启动：中继 + 流水线 + 手机服务 + 二维码
│   ├── paths.py           打包后资源 / 可写路径适配
│   ├── config.py          配置 + 局域网 IP 探测
│   ├── ocr.py             截图 + RapidOCR + 行合并
│   ├── translator.py      mock / argos / deepl / qwen
│   ├── pipeline.py        去重 → 识别 → 翻译 → 推送
│   ├── clip.py            剪贴板读写 + 防回环
│   ├── relay_client.py    中继客户端（自动重连）
│   ├── overlay.py         tkinter 置顶字幕条（鼠标穿透）
│   └── select_region.py   拖拽圈选区域
├── phone/                 手机端网页（PWA：HTML / CSS / JS / 图标 / SW）
├── android/               安卓 WebView 壳工程
├── docs/                  截图
└── examples/              语种识别 / 中继自检脚本
```

---

## 六、消息协议

| type | 方向 | 字段 |
|---|---|---|
| `hello` | C→S | `pair`, `role: pc/phone` |
| `paired` | S→C | `pair`, `peers` |
| `subtitle` | PC→手机 | `ts`, `lang`, `conf`, `src`, `trans`, `retry?`, `engine` |
| `clipboard` | 双向 | `text`, `from` |
| `translate_request` | 手机→PC | `src`, `lang`（重译/手动输入） |
| `status_request` / `status` | 手机↔PC | OCR 行数、已推送条数、引擎名 |

---

## 七、实现细节

1. **只截屏，不读内存**：OCR 只对屏幕像素做识别，不注入游戏进程、不改游戏文件，主流反作弊（VAC/EAC/ACE）不会因此封号。
2. **视觉行合并**：OCR 输出的是一块块文本框，按 y 坐标容差 14px 聚成"一行"，行内按 x 排序拼接，避免同一行被拆成两段推送。
3. **去重靠归一化文本**：去掉标点/空格/大小写后做哈希，8 秒窗口内相同内容不重复推，解决聊天框滚动重绘导致的重复。
4. **语种判定兜底**：置信度 < 0.55（短文本 < 0.70）判 `unknown`；纯拉丁字母且 ≥3 字符按英文处理；`ok`/`gg` 这类 ≤3 字符的判不出语种直接丢弃，不刷字幕。
5. **argos 不阻塞**：模型下载放后台线程，`translate()` 只读已安装的包，缺包时返回空串，上层保留原文，下一条自动生效。
6. **字幕条鼠标穿透**：Windows 下给窗口加 `WS_EX_LAYERED | WS_EX_TRANSPARENT`，点击直接落到下面的游戏。
7. **剪贴板防回环**：记住刚写入的远端内容，轮询遇到它就跳过，不会 PC→手机→PC 无限循环。
8. **端口占用自动顺延**：8780/8781 被占了自动换下一个，二维码和打印的地址用最终端口，不会给你印一个打不开的地址。

---

## 八、已验证 / 未验证

**已实测通过**
- 语种识别：15 条多语种聊天样例判定正确（ja/ko/ru/de/fr/es/pt/tr/ar/zh/en），短词兜底与噪声过滤生效
- OCR：RapidOCR 对合成聊天截图识别准确（置信度 0.98~0.99），三行文本按 y 合并正确
- 中继：PC↔手机双向字幕与剪贴板路由通过
- PC 流水线：demo 源 → 识别 → 翻译 → 推送，连续输出多语种字幕无异常
- 手机端：真实浏览器连上中继后实时收到字幕，徽章/复制/重译/底部栏渲染正常
- 安卓 APK：Gradle 编译通过，`com.rifei.gt` / 入口 Activity / 本地网页资源 / 权限清单已校验，MainActivity 与剪贴板桥接类已进 dex

**未在本机验证（需真机）**
- APK 真机安装后 WebView 加载 `file://` 资源、`ws://` 局域网连接、剪贴板桥接的实际表现（无安卓模拟器/设备）
- 屏幕截图 OCR 的真实游戏画面效果（本机无显示器，`mss` 截图不可用；逻辑已用合成图验证）
- PC 字幕条的窗口置顶与鼠标穿透（tkinter 需要可见桌面）
- DeepL / 千问真实调用（本机网络到这两个域名被拦，代码为官方标准协议，填 key 即可）
- Windows 单文件安装程序（PyInstaller / Inno Setup 需在 Windows 上执行；脚本与配置已就绪）

---

## 九、常见问题

**手机 / APK 连不上**
1. 确认手机和电脑同一个 WiFi（不要一个连 5G 一个连 2.4G 不同网段，也不要电脑插网线到别的路由）
2. 电脑 IP 变了？重新看终端打印的地址
3. Windows 防火墙入站放行 8780/8781（仅限专用网络）
4. 公司/学校 WiFi 开了"AP 隔离"，设备互访被拦，换手机热点试

**识别不到文字**
1. 游戏必须窗口化 / 无边框，全屏独占模式下截图可能黑屏
2. 重新 `select_region.bat` 圈一次，框要完全覆盖聊天文字
3. 文字太小/太糊：游戏内把聊天字号调大，或把 `ocr_min_score` 降到 0.5

**字幕刷得太快 / 重复**
- 调大 `dedup_window`（如 15 秒）
- 调大 `poll_interval`（如 2.5 秒）

**字幕条挡视线**
- `overlay: false` 关掉，只看手机
- 或调小 `overlay_height` / `overlay_font`

---

## 十、合规提醒

- 仅做屏幕截图识别，**不读游戏内存、不注入进程、不改游戏文件**。
- 部分游戏用户协议禁止第三方覆盖层，字幕条可随时用 `overlay: false` 关闭。
- 在线翻译会把聊天文本发到对应服务商，敏感场景请用 `argos` 本地翻译。
- 仅限个人使用，不要用于商业化分发或批量采集他人聊天内容。
