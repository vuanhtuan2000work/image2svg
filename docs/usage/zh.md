# 使用指南（中文）

**image2svg** 是一个本地（可离线）图片转 SVG 工具，提供批量 CLI 和简易 Web UI。

完整依赖列表见：[../libraries.md](../libraries.md)。

Agent Skill（Cursor / Claude / Codex / Gemini）：[../agent-skill.md](../agent-skill.md)。

## 相关库一览

| 作用 | 库 |
|------|----|
| 位图矢量化 → SVG | **vtracer** |
| 图像读写与预处理 | **Pillow**、**pillow-heif** |
| 读取 recipe 配置 | **PyYAML** |
| SVG 优化 | **SVGO**（`npx`）或 **scour** |
| Web UI / API | **FastAPI**、**Uvicorn**、**python-multipart**、**Pydantic** |
| SVG 帧条分析 | **svg.path**、**NumPy**、**PuLP** |
| 抠图（可选） | BiRefNet HTTP / **BEN2**+**PyTorch** / **rembg** |
| Cloudflare 部署（可选） | **fflate**、**upng-js**、**Wrangler** |

## 环境要求

- Python **3.10+**
- （推荐）Node.js，用于 **SVGO**
- Windows / macOS / Linux

## 安装

```bash
git clone https://github.com/vuanhtuan2000work/image2svg.git
cd image2svg
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e .
```

开发依赖：

```bash
pip install -e ".[dev]"
```

检查 SVGO：

```bash
npx svgo --version
```

## 准备素材

```text
assets/raw/<部件类型>/*.png   →   assets/out/<部件类型>/*.svg
```

示例：`assets/raw/eye/eye_purple_01.png`

各部件的 vtracer 参数在 `configs/recipes.yaml`。

## CLI 用法

```bash
# 转换 assets/raw/ 下全部目录
image2svg convert

# 仅某一部件
image2svg convert --part eye

# 质量相关参数
image2svg convert --part eye --smoothing high --color-precision 8 --sharpness 80 --remove-bg --trim --overwrite
```

| 参数 | 含义 |
|------|------|
| `--smoothing` | `none` / `low` / `medium` / `high`（trace 前 Lanczos 放大） |
| `--color-precision` | 1–8（越高保留颜色越多） |
| `--sharpness` | 0–250（锐化） |
| `--remove-bg` | 去背景 → 透明 |
| `--trim` | 裁切到内容边界 |
| `--overwrite` | 覆盖已有 SVG |

## Web UI

```bash
image2svg serve
# 或
image2svg-server
```

- 转换页：[http://127.0.0.1:8765](http://127.0.0.1:8765)
- 分析页：[http://127.0.0.1:8765/analyze](http://127.0.0.1:8765/analyze)

拖拽图片、调整参数、预览并导出 SVG。

## Python API

```python
from pathlib import Path
from image2svg.convert import convert_image_bytes

data = Path("assets/raw/eye/eye_purple_01.png").read_bytes()
svg, params, optimizer, elapsed = convert_image_bytes(
    data,
    part="eye",
    smoothing="high",
    remove_bg=True,
    trim=True,
)

Path("out.svg").write_text(svg, encoding="utf-8")
print(optimizer, elapsed, params)
```

## Analyze / 游戏 manifest 导出

```bash
python scripts/export_game_manifest.py path/to/sheet.svg --dry-run
```

说明见：[../animation-stack.md](../animation-stack.md)。

## 常用环境变量

| 变量 | 用途 |
|------|------|
| `HOST` / `PORT` | Web UI 监听地址 |
| `IMAGE2SVG_RECIPES` | 自定义 recipes 路径 |
| `IMAGE2SVG_ASSETS_ROOT` | 自定义 assets 根目录 |
| `IMAGE2SVG_BIREFNET_URL` | 远程 BiRefNet 抠图接口 |
| `IMAGE2SVG_ML_LANDMARKS` / `IMAGE2SVG_MMPOSE` | 启用分析阶段 ML |

## Cloudflare（可选）

```bash
npm install
npm run deploy
```

Worker 仅提供轻量转换 UI，**不会**运行完整 Python 分析器。

## Agent Skill（AI 编程助手）

安装 **open-source-repo** skill，让各 Agent 按同一套流程把仓库整理成开源标准：

```bash
python skills/installer/install.py install --global
# 或（有 Node）：npx --yes ./skills/installer install --global
```

在对话中输入：`/open-source-repo`，或说 “open-source this repository”。

详见：[../agent-skill.md](../agent-skill.md)。
