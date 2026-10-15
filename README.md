<div align="center">

# 漫画翻译工作台 · Manga Image Translator CN

**拖进漫画、粘贴链接，自动完成「识别 → 翻译 → 去字 → 嵌字」，开箱即用的网页工作台**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![GPU](https://img.shields.io/badge/GPU-NVIDIA%20%7C%20Intel%20Arc%20%7C%20CPU-orange.svg)](#-显卡支持)

基于 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)，针对中文用户与 Windows 桌面使用重新打磨。

</div>

---

## 📖 这是什么

一个在自己电脑上运行的漫画翻译工具。把漫画图片（或一个网页链接）交给它，它会自动：

1. **找出对白**：检测气泡里的文字并识别（日文、中文、韩文、英文都能自动识别）；
2. **翻译**：交给 DeepSeek 大模型翻成地道的中文（也可以翻成日、韩、英、繁体）；
3. **去字**：用 AI 把原文从画面上干净地抹掉；
4. **嵌字**：按气泡大小自动排版、换行、加白边，把译文放回去。

全程在浏览器里操作，**不需要会用命令行**。除了 DeepSeek 翻译这一步需要联网，其余都在本机完成，显卡能用就用显卡。

---

## ✨ 功能一览

**网页工作台**
- 拖入图片 / 整个文件夹，或**直接粘贴漫画网页链接**自动下载并翻译（由 [gallery-dl](https://github.com/mikf/gallery-dl) 支持数百个站点）
- 每页实时进度、预计剩余时间；失败的页可单独重试
- 点开任意一页，拖动滑块对比原图与译图（←/→ 翻页，空格切换，Esc 关闭）
- 结果自动保存到本地文件夹，支持一键打开、打包下载；保存位置可自定义
- 两套主题：**森林小岛**（原创三花猫吉祥物）与**漫画卡通**，并可选白天 / 夜间 / 跟随系统
- 双击 `启动翻译工作台.bat` 即可启动，并自动打开浏览器

**翻译与嵌字**
- DeepSeek 原生接口，默认关闭推理模式，速度快、成本低
- 目标语言：简体中文、繁体中文、日语、韩语、英语
- 中日韩译文使用 PIL 渲染：按语言自动选字体（中文微软雅黑、日文游黑体、韩文 Malgun Gothic），中日文逐字折行、韩文英文按词折行，避免标点出现在行首
- 分格检测：按漫画阅读顺序（从右到左）排列对白，翻译上下文更连贯

**性能**
- 支持 NVIDIA（CUDA）、Intel Arc（XPU）显卡加速，没有显卡也能用 CPU 运行
- 模型常驻内存：启动后每页本地处理约 1–3 秒，大部分时间花在等待翻译结果
- 网页约 5 秒打开，翻译引擎约 20 秒就绪

---

## 🆚 与原版的主要区别

| | 原版 zyddnys/manga-image-translator | 本项目 |
| :--- | :--- | :--- |
| 使用方式 | 命令行 / 开发向网页 | **桌面级网页工作台**，双击启动 |
| 链接导入 | 无 | 粘贴链接自动下载并翻译 |
| 中日韩嵌字 | Freetype 逐字渲染 | PIL 渲染，按语言选字体与折行方式 |
| 翻译 | 多种翻译器 | 重点优化 DeepSeek：解析修复、关闭推理、错误快速失败 |
| 显卡 | CUDA 为主 | CUDA / Intel XPU，XPU 去字启用 bf16 |
| 修复的问题 | — | `--use-gpu` 等参数失效、网页服务内部鉴权缺失导致无法翻译、OpenCV 5 下分格检测失败等 |

---

## 🚀 安装（Windows）

### 1. 准备

| 需要安装 | 说明 |
| :--- | :--- |
| [Python 3.12](https://www.python.org/downloads/) | 安装时勾选 *Add python.exe to PATH* |
| [Git](https://git-scm.com/download/win) | 用于下载代码 |
| [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) | 勾选「**使用 C++ 的桌面开发**」，部分依赖需要编译 |
| NVIDIA 显卡驱动 580 或更新 | 仅 NVIDIA 显卡需要 |

### 2. 下载代码并创建运行环境

```bash
git clone https://github.com/uncat2310/manga-image-translator-cn.git
cd manga-image-translator-cn
python -m venv venv
venv\Scripts\activate
```

### 3. 按显卡安装依赖（选一个）

```bash
pip install -r requirements-cuda.txt   # NVIDIA 显卡（RTX 20 / 30 / 40 / 50 系列）
pip install -r requirements-xpu.txt    # Intel Arc 独显或核显
pip install -r requirements.txt        # 没有独立显卡，只用 CPU
```

> GTX 10 / 16 系列显卡：把 `requirements-cuda.txt` 里的 `cu130` 改成 `cu126` 后再安装。
>
> 也可以用 [uv](https://github.com/astral-sh/uv) 加速：`uv pip install -r requirements-cuda.txt`

### 4. 启动

双击项目文件夹里的 **`启动翻译工作台.bat`**。第一次启动会自动下载模型（约 1 GB），之后浏览器会自动打开工作台。

想在桌面放快捷方式：右键 `启动翻译工作台.bat` → 显示更多选项 → 发送到 → 桌面快捷方式。

### 5. 填写 DeepSeek Key

在 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 创建 API Key，然后在工作台右上角 **⚙ 设置** 里粘贴保存即可。Key 只保存在本机项目的 `.env` 文件中，不会上传。

---

## 🖥️ 使用工作台

1. **添加漫画**：拖入图片或文件夹，或在顶部粘贴网页链接并点「下载并翻译」。
2. **起个名字**：右侧「当前作品」里的作品名称，就是结果保存的文件夹名。
3. **调整设置**（可选）：
   - **翻译方式**：DeepSeek 翻译 / 保留原文只重新排版 / 只去除文字
   - **译成**：简体中文、繁体中文、日语、韩语、英语
   - **文字方向**：自动 / 竖排 / 横排
   - **处理精度**：快速 / 标准 / 精细（扫描图分辨率高、字小时用精细）
   - **字号微调**、**高级选项**（去字模型、文字识别模型、描边）
4. **开始翻译**，完成后点任意一页查看对比，或点「打开文件夹」「下载全部」。

右上角 **⚙ 设置** 里可以切换主题与外观、更改保存位置、填写 DeepSeek Key 和选择模型（`deepseek-flash` 快且便宜，`deepseek-v4-pro` 质量更高）。

> 请只翻译你有权使用的内容，并遵守来源网站的使用条款。

---

## 🎮 显卡支持

| 显卡 | 依赖文件 | 说明 |
| :--- | :--- | :--- |
| NVIDIA RTX 20 / 30 / 40 / 50 | `requirements-cuda.txt` | CUDA 13，驱动需 580+；30 系及以上去字使用 bf16 |
| NVIDIA GTX 10 / 16 | `requirements-cuda.txt`（改为 `cu126`） | 不支持 bf16，自动改用 fp32 |
| Intel Arc 独显 / 核显 | `requirements-xpu.txt` | XPU 加速，去字使用 bf16 |
| AMD（Linux） | `requirements-rocm.txt` | ROCm |
| 无显卡 | `requirements.txt` | CPU 运行，速度较慢但可用 |

启动器会自动检测显卡并记住结果；换了显卡后可运行 `venv\Scripts\python studio_launcher.py --redetect` 重新检测。工作台右上角会显示当前使用的设备。

---

## ⌨️ 命令行用法

除了工作台，也可以直接用命令行批量翻译：

```bash
# 翻译 input 文件夹中的图片，结果写入 output（--use-gpu 可放在 local 前后）
python -m manga_translator local --use-gpu --config-file config.json -i input/ -o output/
```

### `.env`（翻译接口）

```env
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_MODEL=deepseek-flash        # 或 deepseek-v4-pro
DEEPSEEK_THINKING=disabled           # 改为 enabled 开启推理（更慢、更贵）
```

### `config.json`（翻译流程）

完整模板见 [`config-example.json`](config-example.json)，全部字段可运行 `python -m manga_translator config-help` 查看。

```json
{
  "translator": { "translator": "deepseek", "target_lang": "CHS" },
  "detector": { "detector": "default", "detection_size": 2048 },
  "ocr": { "ocr": "48px" },
  "inpainter": { "inpainter": "lama_large", "inpainting_size": 2048, "inpainting_precision": "bf16" }
}
```

### 发布图集

```bash
python publish.py --mode telegraph --title "漫画第1话" output/漫画第1话
```

首次运行会自动注册 Telegraph 账号；配置见 [`publish_config.example.json`](publish_config.example.json)。

### Docker

```bash
docker run -d --name manga-translator -p 5003:5003 --env-file .env \
  -v $(pwd)/models:/app/models --entrypoint python \
  ghcr.io/uncat2310/manga-image-translator-cn:latest \
  server/main.py --start-instance --host=0.0.0.0 --port=5003
```

---

## ❓ 常见问题

**启动窗口一直停在「正在加载翻译引擎」**
第一次启动需要下载模型，取决于网速可能要几分钟；之后约 20 秒即可就绪。

**右上角显示的是 CPU，没用上显卡**
确认安装的是对应显卡的依赖文件（NVIDIA 用 `requirements-cuda.txt`）；NVIDIA 驱动需 580 以上。装好后用 `--redetect` 重新检测。

**提示 DeepSeek 拒绝了请求**
API Key 无效或模型名不可用。在设置里重新填写 Key，模型选 `deepseek-flash` 或 `deepseek-v4-pro`。

**第一页特别慢，后面就快了**
显卡第一次处理新尺寸的图片需要预热，属于正常现象。

**译文挤在一起或超出气泡**
试试把「处理精度」调高，或用「字号微调」调小字号；竖排/横排也可以手动指定。

**端口被占用**
运行 `venv\Scripts\python studio_launcher.py --port 8200` 换一个端口。

---

## 📁 项目结构

```text
启动翻译工作台.bat        双击启动
studio_launcher.py        启动器：检测显卡、启动服务、打开浏览器
server/studio.py          工作台后端接口（设置、保存、链接导入）
server/studio_web/        工作台网页（Vue 3，无需构建）
manga_translator/         翻译流水线（检测、识别、翻译、去字、嵌字）
fonts/                    内置字体
models/                   首次运行自动下载的模型（不上传）
output/                   默认保存位置（不上传）
```

---

## 🙏 致谢与许可

- [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)：本项目的基础
- [gallery-dl](https://github.com/mikf/gallery-dl)：网页链接下载
- [Vue](https://vuejs.org/)：工作台界面
- [DeepSeek](https://platform.deepseek.com/)：翻译模型

本项目以 [GPL-3.0](LICENSE) 协议开源。工作台中的吉祥物、图标与插画均为本项目原创。
