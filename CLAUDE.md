> **檔案**: CLAUDE.md
> **版本**: v1.0
> **創建日期**: 2026-05-23

# Context for Claude Code sessions — ytscribe (engine library)

每個 CC session 進入這個 repo 自動載入本檔。內容是 Eric 個人偏好、專案結構、現階段狀態、跨 session 紀律——讓 session 不用每次重新交付 context。

## Repo 身分

這是 **engine library repo**（`hysteric-lab/ytscribe`，公開、open-core 模式），ytscribe 雙 repo 架構的「引擎」端：純 Python library 封裝 yt-dlp + Groq ASR + bundle 邏輯，由 sibling service repo 透過 `git+https://...@vTAG` pin 安裝。**不是** PyPI 上的同名套件（那是無關專案）。

CLI entrypoint：`ytscribe.cli:main`（service 透過 subprocess 呼叫，不 import）。
公開 helper：`ytscribe.logging_setup.setup_logging()`、`ytscribe.config.Config.from_env()`。

## 雙 repo + 傘子結構

```
~/vs/projects/ytscribe/            ← 傘子目錄，本身不是 git repo
├── ytscribe/                      ← 你正在的這個 repo（engine，公開）
├── ytscribe-service/              ← consuming service（hysteric-lab/ytscribe-service，私有）
│                                    透過 git+https://github.com/hysteric-lab/ytscribe@v0.2.0 安裝本 repo
└── .remember/                     ← 跨 repo project memory（gitignored）
    ├── now.md                     ← 跨 session anchor
    ├── recent.md
    └── today-YYYY-MM-DD.md
```

從本 repo 看，service 在 `../ytscribe-service/`、umbrella `.remember/` 在 `../.remember/`。跨 session 接手只信 `../.remember/now.md` + git log + 真實 artefact——不信記憶。

## 當前階段狀態

- **Phase 0 完整收官**：master = `409070a`、tag `v0.1.0` + `v0.2.0` 已推送、PR #1 merged、CI 綠勾。
- **Phase 1 backlog 3 項**（在 `docs/superpowers/specs/2026-05-22-phase-0-library-design.md §9`）：
  1. `python-json-logger` import path——`logging_setup.py` 用 `from pythonjsonlogger import jsonlogger`，3.x 後子模組搬到 `pythonjsonlogger.json`。`>=2.0,<4` pin 讓它只 warning 不 crash；`lint.yml` 上線後改 import。
  2. `test.yml` hardening——加 `permissions: contents: read`、`branches: [master]` PR trigger 過濾、step `name:`。
  3. 套件 `__version__` 與 tag sync——`src/ytscribe/__init__.py` 與 `pyproject.toml [project] version` 仍卡 `0.1.0`，但 git tag 已 `v0.2.0`，`importlib.metadata.version("ytscribe")` 回 `"0.1.0"`、consuming service `uv.lock` 也記 `0.1.0`。下次 release 一併 bump、未來 `release.yml` 接管。

- **Phase 0 真實抓出的硬 bug**（避免再犯）：
  - `engine.py` 用 subprocess 呼自己的 CLI、不 import library——所以 `Config.from_env()` fail-fast 不在 worker startup trip。consuming service 用 eager call 解（service worker.py main() 開頭呼一次）。
  - `setup_logging()` 必須 idempotent（重複呼叫不疊 handler）、必須 `logger.propagate = False`（避免 host root logger 雙 emit）、只動 `logging.getLogger("ytscribe")` namespace、絕不碰 root。

## 回應規範（Eric 偏好）

- **繁體中文**回應。程式碼註解與檔名保持英文。
- **直言不諱、不迴避批評**。指出問題後必須附可執行處方。
- **拒絕「理所當然」**。第一性原理拆解、蘇格拉底式詰問過濾偽命題。
- **默認實現更改而非僅建議**。意圖不清時推斷最有用的操作並執行。
- **清晰流動散文**為主、列表只在真正離散項目時用、避免過度粗體/斜體。
- **檔案標頭格式**：`> **檔案**: name.md` / `> **版本**: v1.0` / `> **創建日期**: YYYY-MM-DD`。

## 任務結束前必做（通用收尾規範）

1. 寫 `../.remember/now.md` 一行：時間戳 + 本 session 做了什麼 + 下一個 session 該從哪繼續。
2. 列出本 session 任務「出口驗收」每一條 ✅ 或 ❌。
3. 任一 ❌：明寫卡在哪、具體錯誤訊息（exit code、stderr 末三行、最後一條 log line）、下個 session 該帶什麼錯誤訊息問。
4. 任何 secret 絕不貼回 chat、只回報 metadata。

## 跨 session 紀律

- session 開頭固定動作：`cat ../.remember/now.md`、`git status`、`git log --oneline -3`、`uv run pytest -q` 確認綠勾。
- 卡 30 分鐘沒進展就停、寫 now.md、開新 session 帶具體錯誤訊息問。
- engine 修改流程：feature/fix branch → PR → review → merge → **tag 新版本** → consuming service 端 bump pin（Dockerfile + pyproject `[tool.uv.sources]`）。**不要跳過 tag、直接讓 service 拉 master**——uv.lock 會與 Dockerfile 不一致。

## engine ↔ service 介面契約（不要破壞）

- `Config.from_env()` 必須 fail-fast 在無效設定（missing `YTSCRIBE_COOKIES_FILE`、`>=1` 不滿足等）。consuming service 依賴這個語意——service worker.py main() 開頭 eager 呼這個。
- `setup_logging()` 由 consuming app 顯式呼叫（不 auto-run on import）。讀 `YTSCRIBE_LOG_FORMAT=json` env 切換 JSON / human format。
- 所有 yt-dlp 呼叫透過 `_ytdlp.run_ytdlp()` 單一 wrapper、emit 標準 extra fields（`duration_ms` / `exit_code` / `cookies_used` / `proxy_used` / `event`）。**新增 yt-dlp 呼叫點不要繞過 wrapper**——破壞 log schema 一致性。
- 公開 surface：`ytscribe.config`、`ytscribe.logging_setup`、`ytscribe.cli`。其他模組（`engine.py`、`_ytdlp.py`、`sources.py` 等）視為 internal、不對外承諾穩定 API。

## 工具用慣例

- **Python 版本**：3.11 + 3.12 matrix（CI test.yml）。本機 dev 用 `uv` 管理 venv 與 lock。
- **測試**：`uv run pytest` 為 Phase 0 baseline。整合測試標 `@pytest.mark.integration`、預設 deselect。
- **Lint / type-check**：Phase 1 backlog 加 `lint.yml`（ruff + mypy strict）。Phase 0 沒有。
- **Release**：手動 `git tag -a vX.Y.Z -m "..."` + `git push origin vX.Y.Z`。Phase 1 加 `release.yml` 自動化。
