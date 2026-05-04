#!/usr/bin/env python3
"""
把 manga-translator 翻译输出目录推送到 Telegraph + Telegram 频道

用法：
    python3 push_translated_to_telegraph.py <output_dir> [--title "标题"] [--no-channel]

示例：
    python3 push_translated_to_telegraph.py /root/manga-translator/output/348355/
    python3 push_translated_to_telegraph.py /root/manga-translator/output/348355/ --title "Haruka NTR Matome 汉化"
"""
import json
import logging
import os
import sys
import re
import time
from pathlib import Path

BASE_DIR = "/root/tg_media_parser_bot"
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from config import load_settings, _load_env_file
from telegraph_api import TelegraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("push_translated")

# 加载 bot 的 .env
_load_env_file(os.path.join(BASE_DIR, ".env"))
settings = load_settings()

# ── 参数解析 ──
if len(sys.argv) < 2:
    print("用法: python3 push_translated_to_telegraph.py <output_dir> [--title 标题] [--no-channel]")
    sys.exit(1)

output_dir = sys.argv[1]
args = sys.argv[2:]
title_override = None
send_to_channel = True

i = 0
while i < len(args):
    if args[i] == "--title" and i + 1 < len(args):
        title_override = args[i + 1]
        i += 2
    elif args[i] == "--no-channel":
        send_to_channel = False
        i += 1
    else:
        i += 1

if not os.path.isdir(output_dir):
    print(f"❌ 目录不存在: {output_dir}")
    sys.exit(1)

# ── 收集图片 ──
image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
image_files = sorted([
    f for f in os.listdir(output_dir)
    if os.path.splitext(f)[1].lower() in image_exts
])

if not image_files:
    print(f"❌ 目录里没有图片: {output_dir}")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"📤 推送翻译结果到 Telegraph")
print(f"   目录: {output_dir}")
print(f"   图片: {len(image_files)} 张")
print(f"{'='*60}\n")

# ── 提取标题 ──
if not title_override:
    # 从路径推断：output/348355/ → 用目录名
    dir_name = os.path.basename(os.path.abspath(output_dir))
    title_override = f"汉化本子 {dir_name}"

clean_title = re.sub(r'[\\[\\]{}()*#+|^~{}<>]', '', title_override)[:128]
print(f"📖 标题: {clean_title}")

# ── 上传到 Telegraph ──
telegraph = TelegraphClient(
    access_token=settings.telegraph_access_token,
    short_name=settings.telegraph_short_name,
    author_name=settings.telegraph_author_name,
    request_timeout=settings.request_timeout,
    catbox_userhash=settings.catbox_userhash,
    use_public_image_host=settings.telegraph_use_public_image_host,
    public_image_backend=settings.public_image_backend,
    public_image_base_url=settings.public_image_base_url,
    public_image_root=settings.public_image_root,
    fallback_public_image_base_url=settings.public_image_fallback_base_url,
    fallback_public_image_root=settings.public_image_fallback_root,
    r2_account_id=settings.r2_account_id,
    r2_bucket_name=settings.r2_bucket_name,
    r2_access_key_id=settings.r2_access_key_id,
    r2_secret_access_key=settings.r2_secret_access_key,
    r2_region=settings.r2_region,
    r2_endpoint_url=settings.r2_endpoint_url,
    r2_key_prefix=settings.r2_key_prefix,
)

img_urls = []
success = 0
fail = 0

print("📤 上传图片到 Telegraph...")
for i, fname in enumerate(image_files):
    fpath = os.path.join(output_dir, fname)
    try:
        img_url = telegraph.upload_file(fpath)
        if img_url:
            img_urls.append(img_url)
            success += 1
            if (i + 1) % 10 == 0 or i == len(image_files) - 1:
                print(f"   [{i+1}/{len(image_files)}] ✅ {fname}")
    except Exception as e:
        fail += 1
        print(f"   [{i+1}] ❌ {fname}: {e}")

print(f"\n   上传完成: 成功 {success}, 失败 {fail}")

if not img_urls:
    print("❌ 没有成功上传的图片")
    sys.exit(1)

# ── 分页（Telegraph 每页最多 80 张图） ──
MAX_PER_PAGE = 80
page_urls = []

for page_idx in range(0, len(img_urls), MAX_PER_PAGE):
    page_images = img_urls[page_idx:page_idx + MAX_PER_PAGE]
    page_num = page_idx // MAX_PER_PAGE + 1
    total_pages = (len(img_urls) - 1) // MAX_PER_PAGE + 1

    content = [{"tag": "img", "attrs": {"src": url}} for url in page_images]
    page_title = f"{clean_title}" if total_pages == 1 else f"{clean_title} ({page_num}/{total_pages})"

    try:
        page = telegraph.create_page(title=page_title, content=content)
        page_url = page if isinstance(page, str) else page.get("url", "")
        page_urls.append(page_url)
        print(f"📄 页面 {page_num}/{total_pages}: {page_url}")
    except Exception as e:
        print(f"❌ 创建页面失败: {e}")
        sys.exit(1)

# ── 推送到频道 ──
channel_id = settings.auto_forward_channel_id
if send_to_channel and channel_id:
    print(f"\n📤 推送到频道 {channel_id}...")
    try:
        from telegram_api import TelegramBotClient
        bot = TelegramBotClient(
            settings.bot_token,
            api_base=settings.telegram_api_base,
            request_timeout=settings.request_timeout,
        )
        # 构建频道消息
        page_links = "\n".join([f"📄 [第 {i+1} 页]({u})" if len(page_urls) > 1 
                                else f"📄 [Telegraph 图集]({u})" 
                                for i, u in enumerate(page_urls)])
        msg = (
            f"📖 **{clean_title}**\n"
            f"{page_links}\n"
            f"共 {len(image_files)} 页 | 翻译: DeepSeek v4-flash | 嵌字: PIL 自适应"
        )
        sent = bot.send_message(int(channel_id), msg)
        mid = sent.get("message_id", "?") if isinstance(sent, dict) else sent
        print(f"   ✅ 频道消息已发: message_id={mid}")
    except Exception as e:
        print(f"   ❌ 频道推送失败: {e}")

# ── 输出结果 ──
print(f"\n{'='*60}")
print(f"✅ 全部完成!")
for i, u in enumerate(page_urls):
    print(f"   Telegraph ({i+1}): {u}")
print(f"{'='*60}")

# 输出 JSON 给调用方（Hermes 可以通过 stdout 获取 URL）
result = {
    "title": clean_title,
    "page_count": len(image_files),
    "telegraph_urls": page_urls,
    "primary_url": page_urls[0] if page_urls else "",
}
print(f"\n__RESULT__{json.dumps(result, ensure_ascii=False)}")
