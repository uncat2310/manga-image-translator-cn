# manga-image-translator-cn

**基于 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) 的中文优化分支**

> 🇨🇳 针对中文（简体/繁体）漫画翻译场景深度优化：PIL 自适应中文嵌字渲染、DeepSeek 原生翻译器、Telegraph 图床一键发布。

---

## ✨ 相较原版的改进

| 改进点 | 原版 | 本项目 |
|--------|------|--------|
| **中文嵌字** | freetype 逐字渲染，英文 hyphenator 排版，中文溢出/截断 | **PIL + 思源黑体**，CJK 逐字换行，自适应字号，白边描边 |
| **翻译器** | openai / sugoi 离线 | **DeepSeek v4-flash 原生接口**，中文流畅自然 |
| **交付方式** | 本地图片文件 | **一键推送到 Telegraph**（复用 R2→Catbox 图床链），一条链接 | 
| **配置加载** | 命令行参数零散 | `config.json` 集中管理，`--config-file` 显式加载 |
| **部署** | Docker 镜像 | **宿主机直接部署**（Python 3.11 venv + systemd），稳定简单 |

## 📸 效果对比

*Coming soon*

## 🚀 快速开始

### 前置要求
- Python 3.11（**不要用 3.13**，缺 Pillow/manga-ocr 预编译包）
- CPU-only 即可运行（Intel Xeon E3-1245 V2 验证通过）

### 1. 克隆并安装

```bash
git clone https://github.com/uncat2310/manga-image-translator-cn.git manga-translator
cd manga-translator
python3.11 -m venv venv
source venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
mkdir -p input output fonts
```

### 2. 配置 API Key

创建 `.env`：
```bash
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-flash
```

### 3. 配置 `config.json`

```json
{
  "translator": {"translator": "deepseek", "target_lang": "CHS"},
  "detector": {"detector": "default", "detection_size": 2048, "text_threshold": 0.5, "box_threshold": 0.7, "unclip_ratio": 2.3},
  "ocr": {"ocr": "48px", "min_text_length": 0},
  "inpainter": {"inpainter": "lama_large", "inpainting_size": 2048, "inpainting_precision": "fp32"},
  "renderer": {"renderer": "default"},
  "kernel_size": 3,
  "mask_dilation_offset": 20
}
```

### 4. 翻译单张

```bash
python -m manga_translator local -i input/test.jpg --config-file config.json
# 输出: result/final.png
```

### 5. 全本汉化（nhentai → Telegraph）

```bash
# Step 1: 下载
gallery-dl "https://nhentai.net/g/GALLERY_ID/"

# Step 2: 批量翻译（关键：必须带 --config-file！）
python -m manga_translator local \
  -i "input_dir/" -o "output_dir/" \
  --config-file config.json --overwrite

# Step 3: 推送到 Telegraph
python3 push_translated_to_telegraph.py "output_dir/" --title "本子标题 (Chinese)"

# 返回 Telegraph 链接 → 发送给用户
```

## 🛠️ 核心组件

### PIL 中文渲染器 (`manga_translator/rendering/pil_cn_render.py`)

替换原版 freetype 渲染器，专为 CJK 文字优化：
- **思源黑体** 自适应字号（0.8× 递缩至适配气泡）
- **白边描边**：PIL 原生 stroke + 手动 fallback
- **颜色安全转换**：numpy 数组 → int tuple
- 自动检测 `target_lang` 为 CJK 时路由至此渲染器

### Telegraph 发布 (`push_translated_to_telegraph.py`)

复用 [tg-media-parser-bot](https://github.com/uncat2310/tg-media-parser-bot) 的 TelegraphClient：
- 上传链：R2 → Catbox（自动回退）
- 自动分页（每页 80 张）
- 可选推送到 Telegram 频道
- 输出 JSON 结果供调用方解析

## ⚠️ 关键注意事项

1. **`--config-file` 必须显式传入** — `local` 命令不会自动加载 `config.json`
2. **Python 3.11 only** — 3.13 缺少预编译包
3. **CPU 需设置 `inpainting_precision: "fp32"`** — 默认 bf16 不支持
4. **批处理勿用 `| tail` 管道** — 会缓冲全部输出不可见
5. **DeepSeek 比 OpenCode Go 可靠** — 后者有 ~25% 空响应率

## 📊 性能基准

| 图源 | 页数 | 耗时 | 速度 |
|------|------|------|------|
| nhentai 431891 | 6 | 3.8 分钟 | 38s/页 |
| nhentai 348355 | 8 | 3.9 分钟 | 29s/页 |

> 环境：Intel Xeon E3-1245 V2, 31GB RAM, CPU-only, DeepSeek v4-flash

## 📦 依赖版本

- Python 3.11
- torch==2.11.0+cpu, torchvision==0.26.0+cpu
- transformers==5.7.0, manga-ocr==0.1.14
- opencv-python==4.11.0.86, openai==1.63.0
- Pillow==12.1.1
- gallery-dl（外部，用于 nhentai 下载）

## 🙏 致谢

本项目基于 **[zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)** 开发。
感谢原作者 [zyddnys](https://github.com/zyddnys) 及全体贡献者提供的优秀基础框架。

---

*改进于 2026-05-04 | [uncat2310](https://github.com/uncat2310)*
