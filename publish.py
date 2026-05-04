#!/usr/bin/env python3
"""
manga-image-translator 翻译结果发布工具
========================================

独立脚本，零外部依赖（仅需 requests，manga-translator 已自带）。

模式：
  local     - 【默认】复制翻译结果到本地目录，开箱即用
  telegraph - 【进阶】上传 Catbox 图床 → 创建 Telegraph 聚合页面，一条链接分享全本

用法：
  python3 publish.py output/348355/                          # 默认 local 模式
  python3 publish.py output/348355/ --mode telegraph         # Telegraph 聚合发布
  python3 publish.py output/348355/ --mode telegraph --title "本子标题"
  python3 publish.py output/348355/ --mode local -o ./my_published/

Telegraph 模式前置条件：
  1. 去 https://catbox.moe/user/ 注册账号，获取 userhash
  2. 填入 publish_config.json 的 catbox.userhash 字段
  3. 运行 --mode telegraph 即可（Telegraph 账户自动注册）

配置文件：
  首次运行自动创建 publish_config.json，只需填入 catbox userhash 即可启用进阶功能
"""

import argparse
import json
import logging
import os
import shutil
import sys
from typing import List, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("publish")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "publish_config.json")

TELEGRAPH_API = "https://api.telegra.ph"

DEFAULT_CONFIG = {
    "_comment": (
        "manga-translator 发布配置。\n"
        "  - local 模式无需任何配置，开箱即用。\n"
        "  - telegraph 模式需要 catbox userhash：去 https://catbox.moe/user/ 注册获取\n"
        "  - telegraph access_token 留空即可，首次运行自动注册\n"
        "  - telegram 频道推送可选：填 bot_token 和 channel_id 启用"
    ),
    "mode": "local",
    "catbox": {
        "userhash": ""
    },
    "telegraph": {
        "access_token": "",
        "short_name": "manga-translator",
        "author_name": "manga-translator"
    },
    "telegram": {
        "bot_token": "",
        "channel_id": ""
    },
    "local": {
        "output_dir": "./published"
    }
}


def load_config() -> dict:
    """加载配置，首次运行自动创建模板文件。"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    logger.info(f"首次运行，创建配置模板: {CONFIG_PATH}")
    logger.info("  → 如需启用 Telegraph 聚合发布，请编辑此文件填入 catbox.userhash")
    logger.info("  → 获取 userhash: https://catbox.moe/user/")
    with open(CONFIG_PATH, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return DEFAULT_CONFIG


# ═══════════════════════════════════════════════════════════
#  Catbox 图床上传
#  ═══════════════════════════════════════════════════════════
#  文档: https://catbox.moe/tools.php
#  注册获取 userhash: https://catbox.moe/user/
#  userhash 填入 publish_config.json → catbox.userhash
# ═══════════════════════════════════════════════════════════

def upload_to_catbox(filepath: str, userhash: str) -> Optional[str]:
    """
    上传单个文件到 Catbox 图床。
    返回直链 URL（如 https://files.catbox.moe/xxxxx.jpg），失败返回 None。
    """
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload", "userhash": userhash},
                files={"fileToUpload": f},
                timeout=60
            )
        if resp.status_code == 200 and resp.text.strip().startswith("http"):
            return resp.text.strip()
        else:
            logger.error(f"Catbox 上传失败 [{resp.status_code}]: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Catbox 上传异常: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  Telegraph API（创建聚合页面）
#  ═══════════════════════════════════════════════════════════
#  文档: https://telegra.ph/api
#  上传使用 Catbox 图床（Telegraph 自身上传端点不稳定）。
#  Telegraph 账户自动注册，无需手动操作。
# ═══════════════════════════════════════════════════════════

def telegraph_create_account(short_name: str, author_name: str) -> str:
    """创建 Telegraph 账户，返回 access_token（自动保存到配置文件）。"""
    resp = requests.get(f"{TELEGRAPH_API}/createAccount", params={
        "short_name": short_name[:32],
        "author_name": author_name[:128]
    }, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"创建 Telegraph 账户失败: {data}")
    return data["result"]["access_token"]


def telegraph_create_page(access_token: str, title: str, image_urls: List[str]) -> str:
    """
    创建 Telegraph 聚合页面。
    image_urls: Catbox 直链列表（每张图片一个 URL）
    返回 Telegraph 页面 URL。
    """
    # Telegraph 每页最多容纳 80 张图
    if len(image_urls) > 80:
        logger.warning(f"图片数量 ({len(image_urls)}) 超过单页上限 80，仅使用前 80 张")
        image_urls = image_urls[:80]

    content = [{"tag": "img", "attrs": {"src": url}} for url in image_urls]
    payload = {
        "access_token": access_token,
        "title": title[:256],
        "content": json.dumps(content),
        "return_content": False
    }
    resp = requests.post(f"{TELEGRAPH_API}/createPage", data=payload, timeout=30)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"创建 Telegraph 页面失败: {data}")
    return data["result"]["url"]


# ═══════════════════════════════════════════════════════════
#  核心逻辑
# ═══════════════════════════════════════════════════════════

def collect_images(input_dir: str) -> List[str]:
    """收集目录中的图片，按文件名排序。"""
    img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    files = sorted([
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in img_exts
    ])
    if not files:
        raise FileNotFoundError(f"目录中没有图片: {input_dir}")
    return files


def mode_local(image_paths: List[str], output_dir: str) -> List[str]:
    """
    【默认】本地输出模式。
    将所有翻译结果复制到指定目录，无需任何配置。
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for fpath in image_paths:
        dest = os.path.join(output_dir, os.path.basename(fpath))
        shutil.copy2(fpath, dest)
        results.append(dest)
    logger.info(f"本地输出: {len(results)} 张 → {output_dir}")
    return results


def mode_telegraph(image_paths: List[str], config: dict, title: str) -> str:
    """
    【进阶】Telegraph 聚合发布模式。
    
    流程：
      1. 上传所有图片到 Catbox 图床
      2. 用 Catbox 直链创建 Telegraph 聚合页面
      3. 返回 Telegraph 页面 URL（一条链接分享全本）
    
    前置条件：
      - publish_config.json 中配置 catbox.userhash
      - 获取 userhash: https://catbox.moe/user/
    """
    # ── Step 0: 检查配置 ──
    userhash = config.get("catbox", {}).get("userhash", "").strip()
    if not userhash:
        raise RuntimeError(
            "Catbox userhash 未配置！\n"
            "  1. 去 https://catbox.moe/user/ 注册账号，获取 userhash\n"
            "  2. 编辑 publish_config.json，填入 catbox.userhash 字段\n"
            "  3. 重新运行"
        )

    # ── Step 1: 上传到 Catbox ──
    total = len(image_paths)
    logger.info(f"上传 {total} 张图片到 Catbox...")
    img_urls = []

    for i, fpath in enumerate(image_paths):
        url = upload_to_catbox(fpath, userhash)
        if url:
            img_urls.append(url)
        else:
            logger.error(f"  [{i+1}/{total}] 上传失败: {os.path.basename(fpath)}")
        
        if (i + 1) % 5 == 0 or i == total - 1:
            logger.info(f"  进度: {i+1}/{total} (成功 {len(img_urls)})")

    if not img_urls:
        raise RuntimeError("所有图片上传 Catbox 失败，无法继续")

    logger.info(f"Catbox 上传完成: {len(img_urls)}/{total} 张")

    # ── Step 2: 创建 Telegraph 页面 ──
    tg_config = config.get("telegraph", {})
    access_token = tg_config.get("access_token", "").strip()

    if not access_token:
        logger.info("Telegraph 账户不存在，自动注册...")
        access_token = telegraph_create_account(
            tg_config.get("short_name", "manga-translator"),
            tg_config.get("author_name", "manga-translator")
        )
        # 自动保存 token，下次不用重新注册
        tg_config["access_token"] = access_token
        config["telegraph"] = tg_config
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Telegraph 账户已创建并保存到 publish_config.json")

    logger.info(f"创建 Telegraph 聚合页面...")
    page_url = telegraph_create_page(access_token, title, img_urls)
    logger.info(f"Telegraph 页面: {page_url}")

    return page_url


# ═══════════════════════════════════════════════════════════
#  命令行入口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="manga-translator 翻译结果发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认：本地输出翻译结果
  python3 publish.py output/348355/

  # 进阶：上传 Catbox → Telegraph 聚合页面，一条链接分享全本
  python3 publish.py output/348355/ --mode telegraph --title "本子汉化标题"

  # 指定本地输出目录
  python3 publish.py output/348355/ --mode local -o ./my_translated/

前置条件（仅 telegraph 模式需要）:
  1. 去 https://catbox.moe/user/ 注册，获取 userhash
  2. 编辑 publish_config.json，填入 catbox.userhash
  3. 不需要 Telegraph 账户（脚本自动注册）
        """
    )
    parser.add_argument("input", help="翻译输出目录（包含翻译后的图片文件）")
    parser.add_argument("--mode", choices=["local", "telegraph"], default="local",
                        help="发布模式（默认: local 本地输出）")
    parser.add_argument("--title", help="Telegraph 页面标题（仅 telegraph 模式）")
    parser.add_argument("-o", "--output-dir", default="./published",
                        help="local 模式输出目录（默认: ./published）")

    args = parser.parse_args()

    # 加载配置
    config = load_config()
    mode = args.mode or config.get("mode", "local")

    if not os.path.isdir(args.input):
        print(f"❌ 目录不存在: {args.input}")
        sys.exit(1)

    # 自动生成标题
    if not args.title:
        dir_name = os.path.basename(os.path.abspath(args.input))
        args.title = f"汉化 {dir_name}"

    print(f"\n{'='*60}")
    print(f"📤 发布翻译结果")
    print(f"   源目录: {args.input}")
    print(f"   模式: {mode}")
    print(f"{'='*60}\n")

    image_paths = collect_images(args.input)
    print(f"🖼️  共 {len(image_paths)} 张图片\n")

    if mode == "local":
        output_dir = args.output_dir or config.get("local", {}).get("output_dir", "./published")
        results = mode_local(image_paths, output_dir)
        print(f"\n✅ 完成！本地路径: {output_dir}/")
        for r in results:
            print(f"   {r}")

    elif mode == "telegraph":
        try:
            page_url = mode_telegraph(image_paths, config, args.title)
            result = {
                "mode": "telegraph",
                "title": args.title,
                "page_count": len(image_paths),
                "url": page_url
            }
            print(f"\n✅ 完成！Telegraph 聚合页面: {page_url}")
            print(f"\n__RESULT__{json.dumps(result, ensure_ascii=False)}")
        except RuntimeError as e:
            print(f"\n❌ 发布失败: {e}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
