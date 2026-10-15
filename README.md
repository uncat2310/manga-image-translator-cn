<div align="center">

# 🎨 Manga Image Translator CN (漫画翻译中文优化版)

**针对中文（简体/繁体）场景深度优化的全自动漫画翻译、自适应嵌字与图集分发引擎**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GHCR%20Automated-success.svg)](https://github.com/uncat2310/manga-image-translator-cn/actions)

*基于 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) 深度定制与中文重构。*

</div>

---

## 📖 项目简介

**Manga Image Translator CN** 是一个针对中文漫画翻译、去字嵌字场景深度定制的开源工具。

原版在处理中文繁简体时存在断句不准确、字号溢出、生硬机翻等问题。本项目重构了中文渲染引擎，接入了 **DeepSeek 原生大模型翻译接口**，实现了自适应字号折行与白边描边，并支持一键发布至 Telegraph / Catbox 图床链。

---

## ✨ 核心优化对比

| 特性 | 原版 (Upstream) | 本项目 (CN 优化版) |
| :--- | :--- | :--- |
| 🔤 **中文排版嵌字** | Freetype 逐字渲染，英文连字符断词，中文经常溢出/截断 | **PIL + 思源黑体**，CJK 智能断句折行，自适应字号与动态描边 |
| 🧠 **翻译大模型** | OpenAI / Sugoi 离线机翻 | **DeepSeek 原生大模型接口**，对白地道流畅，拟声词自然本地化 |
| 🚀 **极速发布分发** | 仅生成本地零散文件 | **一键生成 Telegraph 聚合图集** 与 Telegram 频道推送 |
| ⚙️ **配置中枢** | 繁琐且分散的 CLI 参数 | `config.json` 集中化配置，支持一键热重载 |
| 🐳 **容器与部署** | 单一 Dockerfile | 原生支持 Docker 一键拉取与 systemd 生产守护进程 |

---

## 🚀 快速开始

### 🖥️ 网页工作台（Windows 推荐，无需命令行）

按下方「方式二」装好依赖后，双击项目根目录的 **`启动翻译工作台.bat`**：

- 自动检测显卡（NVIDIA / Intel Arc / CPU），启动服务并在浏览器打开 `http://127.0.0.1:8000/studio`
- 拖入图片或整个文件夹，或**直接粘贴漫画网页链接**（由 [gallery-dl](https://github.com/mikf/gallery-dl) 下载，支持 nhentai、pixiv 等数百个站点），下载完自动开始翻译
- 实时显示每页进度，点击任意一页可拖动滑块对比原图与译图
- 结果自动保存到 `output/<作品名称>/`，可一键打开文件夹或打包下载
- 右上角「设置」里填写 DeepSeek API Key 和模型，无需手动编辑 `.env`

使用期间保持启动窗口打开，关闭窗口即退出。

### 方式一：Docker 一键拉取运行

```bash
docker run -d \
  --name manga-translator \
  --restart unless-stopped \
  -p 5003:5003 \
  --env-file .env \
  -v $(pwd)/models:/app/models \
  --entrypoint python \
  ghcr.io/uncat2310/manga-image-translator-cn:latest \
  server/main.py --start-instance --host=0.0.0.0 --port=5003
```

---

### 方式二：源码本地运行

需要 **Python 3.12+**。Windows 用户请先安装 [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)（勾选“使用 C++ 的桌面开发”），`pydensecrf` 需要编译。

#### 1. 克隆仓库并安装依赖

```bash
git clone https://github.com/uncat2310/manga-image-translator-cn.git
cd manga-image-translator-cn

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 按硬件选一个：
pip install -r requirements-cuda.txt  # NVIDIA 显卡（RTX 20–50 系列，驱动需 580 以上）
pip install -r requirements.txt       # 只用 CPU
pip install -r requirements-xpu.txt   # Intel Arc 独显/核显（XPU）
pip install -r requirements-rocm.txt  # AMD GPU (ROCm)
```

#### 2. 配置 API Key

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxx
# 可选
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash        # 或 deepseek-v4-pro
```

再复制配置模板：`cp config-example.json config.json`（Windows: `copy config-example.json config.json`）。

#### 3. 单张/批量漫画翻译

```bash
# 翻译 input/ 目录下的图片，结果写入 output/（有 GPU 时加 --use-gpu，支持 CUDA / Intel XPU / Apple MPS）
python -m manga_translator -v local --config-file config.json -i input/ -o output/

# 指定中文字体（可选，默认使用 fonts/msyh.ttc）
python -m manga_translator --font-path fonts/msyh.ttc local --config-file config.json -i input/ -o output/

# 生成 Telegraph 图集
python publish.py --mode telegraph --title "漫画第1话" output/
```

---

## ⚙️ 配置文件

### `config.json`（翻译流程）

完整模板见 [`config-example.json`](config-example.json)，字段说明可运行 `python -m manga_translator config-help`。关键部分：

```json
{
  "translator": {
    "translator": "deepseek",
    "target_lang": "CHS"
  },
  "detector": { "detector": "default", "detection_size": 2048 },
  "ocr": { "ocr": "48px" },
  "inpainter": { "inpainter": "lama_large", "inpainting_size": 2048 }
}
```

> API Key 只从 `.env` / 环境变量读取，不要写进 `config.json`；字体通过命令行 `--font-path` 指定。

### `publish_config.json`（发布）

复制 [`publish_config.example.json`](publish_config.example.json) 为 `publish_config.json`。Telegraph 模式首次运行会自动注册并写入 `access_token`。

---

## 📄 开源许可证

本项目基于 [AGPL-3.0 License](LICENSE) 开源协议。
