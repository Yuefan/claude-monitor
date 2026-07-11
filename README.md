# Claude Usage Monitor

A lightweight, cross-platform (Windows / Linux / macOS) usage monitor for **Claude Code**.
It reads Claude Code's local transcript files and shows you — in real time — how many
tokens you're burning, what it would cost at API prices, and how close you are to your
5-hour rate-limit window.

**Claude-styled GUI** (cream & terracotta), **system tray support**, **bilingual UI
(English / 中文)**, plus a full-featured **CLI**. Zero required third-party dependencies —
the GUI runs on Python's built-in Tkinter.

> 💡 Your data never leaves your machine. The tool only reads local files under
> `~/.claude/projects` — no network calls, no API key needed.

---

## Features

- 📊 **Live dashboard** — auto-refreshes every 30 s, with a countdown to the next refresh
- ⏱️ **5-hour rate-limit window tracking** — elapsed-time bar, burn rate (tokens/min), and a
  **usage / remaining-balance progress bar** (green → yellow → red)
- 💰 **Cost estimation** at official API prices, including cache-write (1.25× / 2×) and
  cache-read (0.1×) rates — per day, per month, per model, per project
- 🔔 **System tray** — closing the window minimizes to tray; hover the icon to see today's cost
- 🌐 **One-click language toggle** — English / 中文, persisted across restarts
- 🖥️ **CLI mode** — `daily`, `monthly`, `models`, `projects`, `blocks`, `live` reports for
  terminals and SSH sessions
- 📦 **Single-file .exe** build for Windows (no Python required on the target machine)

## Requirements

| Component | Requirement |
|---|---|
| OS | Windows 10/11, Linux, or macOS |
| Python | 3.8+ (not needed if you use the packaged `.exe`) |
| Claude Code | Installed and used at least once (so `~/.claude/projects` exists) |
| Optional | `pystray` + `pillow` for the system-tray feature |

---

## Quick Start

### Option A — Windows, no Python (packaged exe)

1. Download `ClaudeUsageMonitor.exe` from the [Releases](../../releases) page
   (or build it yourself — see [Building the exe](#building-the-exe)).
2. Double-click it. That's it.
3. If Windows SmartScreen warns you (normal for unsigned executables), click
   **More info → Run anyway**.

### Option B — Run from source (all platforms)

```bash
# 1. Clone the repository
git clone https://github.com/Yuefan/claude-monitor.git
cd claude-monitor

# 2. (Optional) enable the system-tray feature
pip install pystray pillow

# 3. Launch the GUI
python claude_monitor_gui.py
```

On Linux, if Tkinter is missing: `sudo apt install python3-tk` (Debian/Ubuntu) or
`sudo dnf install python3-tkinter` (Fedora).

### Option C — CLI only (great over SSH)

```bash
python claude_monitor.py            # summary: current 5h window + today + last 7 days
python claude_monitor.py live      # live terminal dashboard (Ctrl+C to quit)
```

---

## GUI Tour

```
┌──────────────────────────────────────────┬────────────────────────┐
│ Current 5-hour Window                    │ Today  2026-07-11      │
│ 18:00 - 23:00   elapsed 42m, 258m left   │                        │
│ [██████░░░░░░░░░░░░░░░]  (time)          │   $42.73               │
│ tokens 1.9M   cost $9.46   msgs 51       │ tokens 19.3M  msgs 198 │
│ in 11  out 11.8K  cacheW ...  burn ...   │ in ... out ...         │
│ Window usage / limit (auto $24.69)       │ Models: fable-5        │
│ [████████░░░░░░░░░░░░]  (usage)          │                        │
│ used $9.46 (38%)    remaining $15.23     │                        │
├──────────────────────────────────────────┴────────────────────────┤
│ [ Daily ] [ Models ] [ Projects ] [ 5h Blocks ] [ Monthly ]       │
│  ... sortable tables with a TOTAL row ...                         │
├───────────────────────────────────────────────────────────────────┤
│ Last refresh 18:42:10 · Next refresh 18:42:40 (in 23s)  [中文][Refresh] │
└───────────────────────────────────────────────────────────────────┘
```

- **Time bar** — how far into the current 5-hour rate-limit window you are.
- **Usage bar** — estimated cost used vs. your window limit; the label shows the
  **remaining balance**. Colors: green < 60 %, yellow < 85 %, red ≥ 85 %.
- **Tabs** — daily / per-model / per-project / 5-hour-block / monthly breakdowns.
- **Status bar** — last & next refresh time (live countdown), language toggle, manual refresh.
- **Close button** minimizes to the system tray (if `pystray` is installed); right-click the
  tray icon to quit. On Windows 11 new tray icons start in the `^` overflow area — drag the
  orange starburst onto the taskbar to pin it.

## Configuration

> **Do I need an API key?** No. The tool reads Claude Code's local transcript files —
> there is nothing to authenticate and no data ever leaves your machine.

Click the **Settings** button in the status bar to configure everything from the GUI:

- **Claude data directory** — leave empty for auto-detect (`~/.claude/projects`,
  `$CLAUDE_CONFIG_DIR/projects`, or `~/.config/claude/projects`). Set it only if
  Claude Code stores data in a non-standard location.
- **5-hour window limit (USD)** — the budget used by the remaining-balance bar.
  Leave empty to auto-estimate from your highest historical window.

Settings are stored in a `config.json` next to the script (or next to the `.exe`).
You can also edit it by hand — all fields optional:

```json
{
  "lang": "en",
  "block_limit_usd": 35,
  "data_dir": "D:/somewhere/.claude"
}
```

| Key | Default | Meaning |
|---|---|---|
| `lang` | `"en"` | UI language: `"en"` or `"zh"`. Also set by the in-app toggle button. |
| `block_limit_usd` | auto | Your 5-hour window budget in USD. Anthropic doesn't publish exact subscription limits, so by default the tool estimates it from your **highest historical window usage**. Set it manually if you know your plan's practical ceiling. |
| `data_dir` | auto | Custom Claude data directory (either the `.claude` folder or its `projects` subfolder). |

## CLI Reference

```bash
python claude_monitor.py [command] [options]
```

| Command | Description | Options |
|---|---|---|
| *(none)* / `summary` | Current window + today + last 7 days | |
| `daily` | Per-day table | `--days N` (default 14) |
| `monthly` | Per-month table | |
| `models` | Per-model breakdown | |
| `projects` | Per-project breakdown | |
| `blocks` | 5-hour rate-limit windows | `--limit N` (default 10) |
| `live` | Auto-refreshing terminal dashboard | `--interval N` seconds (default 10) |

## How It Works

1. **Data source** — Claude Code writes a JSONL transcript for every session under
   `~/.claude/projects/<project>/<session>.jsonl`. Each assistant message carries a
   `usage` object (input / output / cache-write / cache-read tokens and the model ID).
   The tool also checks `$CLAUDE_CONFIG_DIR/projects` and `~/.config/claude/projects`.
2. **Deduplication** — retried/streamed messages are deduplicated on
   `message.id + requestId`, so nothing is double-counted.
3. **Cost model** — official API prices per model (input/output per MTok), with cache
   writes at 1.25× (5-min TTL) or 2× (1-h TTL) input price and cache reads at 0.1×.
   Sonnet 5 automatically uses its introductory pricing before 2026-09-01.
4. **5-hour blocks** — Claude subscriptions rate-limit in rolling 5-hour windows. A block
   starts at the first message (floored to the hour) and spans 5 h; a gap > 5 h starts a
   new block. This mirrors how the official limits behave.

> **Note on "cost":** if you're on a Pro/Max subscription you don't pay per token.
> The dollar figures are the *API-equivalent value* of your usage — useful for gauging
> intensity and distance to the rate limit, not an invoice.

## Building the exe

```bash
pip install pyinstaller pystray pillow
python -m PyInstaller --onefile --noconsole --name ClaudeUsageMonitor --icon icon.ico claude_monitor_gui.py
# → dist/ClaudeUsageMonitor.exe  (~29 MB, fully self-contained)
```

## FAQ

**The window flashes and closes / nothing happens.**
Run `python claude_monitor_gui.py` from a terminal to see the error. The most common cause
is a missing Tkinter on Linux (`sudo apt install python3-tk`).

**"Claude Code data directory not found".**
Use Claude Code at least once on this machine first — the tool reads
`~/.claude/projects`, which is created by Claude Code itself.

**Where is the tray icon?**
On Windows 11 it starts hidden in the taskbar's `^` overflow. Drag the orange starburst
out to pin it.

**SmartScreen / antivirus flags the exe.**
PyInstaller-packaged executables are unsigned; this is a well-known false-positive pattern.
Build from source with the one-liner above if you prefer.

**Are the numbers exact?**
Token counts are exactly what Claude Code recorded. Costs are computed from the public
price list; the 5-hour *limit* is an estimate (see `block_limit_usd`) because Anthropic
doesn't publish per-plan quotas.

---

## 中文说明

跨平台的 Claude Code 用量监控工具：实时显示 token 消耗、等价 API 成本、5 小时限额窗口的
用量与**余额**进度条。Claude 官方风格界面，支持系统托盘和中英文一键切换。

**快速开始：**

- Windows 免 Python：下载 `ClaudeUsageMonitor.exe` 双击运行（SmartScreen 警告点"更多信息 → 仍要运行"）
- 源码运行：`pip install pystray pillow`（托盘，可选）→ `python claude_monitor_gui.py`
- 命令行：`python claude_monitor.py live`

**配置**：点击状态栏的 **设置** 按钮即可配置数据目录和 5 小时限额（也可手动编辑脚本/exe
同目录的 `config.json`：`lang` 界面语言、`block_limit_usd` 窗口限额、`data_dir` 自定义
数据目录）。**本工具不需要 API Key**——数据来自本机 Claude Code 的记录文件。

**说明：** 数据全部来自本机 `~/.claude/projects`，不联网、不需要 API key。订阅用户不按
token 付费，显示的美元是"等价 API 价值"，用于衡量用量强度和离限额的距离。

## License

MIT — see [LICENSE](LICENSE).
