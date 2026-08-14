<div align="center">

# 🎨 Manga Image Translator CN (漫画翻译中文优化版)

**针对中文（简体/繁体）场景深度优化的全自动漫画翻译、自适应嵌字与图集分发引擎**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
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

### 方式一：Docker 一键拉取运行（推荐）

```bash
docker run -d \
  --name manga-translator \
  --restart unless-stopped \
  -p 5003:5003 \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/config.json:/app/config.json \
  ghcr.io/uncat2310/manga-image-translator-cn:latest
```

---

### 方式二：源码本地运行

#### 1. 克隆仓库并安装依赖
```bash
git clone https://github.com/uncat2310/manga-image-translator-cn.git
cd manga-image-translator-cn

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. 单张/批量漫画翻译
```bash
# 本地翻译并保存为图片
python -m manga_translator -v --config-file config.json -i input.jpg -o output.jpg

# 自动生成 Telegraph 图集
python publish.py --mode telegraph --title "漫画第1话" /path/to/translated_images/
```

---

## ⚙️ 配置文件示例 (`config.json`)

```json
{
  "translator": "deepseek",
  "deepseek": {
    "api_key": "YOUR_DEEPSEEK_API_KEY",
    "model": "deepseek-chat"
  },
  "target_lang": "CHS",
  "font_path": "fonts/SourceHanSansCN-Bold.otf",
  "telegraph": {
    "access_token": "YOUR_TELEGRAPH_TOKEN"
  }
}
```

---

## 📄 开源许可证

本项目基于 [AGPL-3.0 License](LICENSE) 开源协议。
