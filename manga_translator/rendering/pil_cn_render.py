"""
PIL-based CJK text rendering for manga-image-translator.
Replaces the freetype-based renderer for Chinese/Japanese/Korean text.

Key improvements over default renderer:
1. Proper CJK character-level line wrapping (no hyphenation garbage)
2. PIL's native stroke rendering for clean white outlines
3. Better font metrics for Chinese characters
4. Padding/margin for bubble fill
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Optional, List
import os

# Project-relative font path
from ..utils import BASE_PATH


def _get_cjk_font(font_size: int = 30) -> ImageFont.FreeTypeFont:
    """Get a CJK font, with fallback chain."""
    font_candidates = [
        os.path.join(BASE_PATH, 'fonts', 'NotoSansSC-Regular.ttf'),
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        os.path.join(BASE_PATH, 'fonts', 'NotoSansMonoCJK-VF.ttf.ttc'),
    ]
    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, font_size)
            except Exception:
                continue
    # Last resort: PIL default
    return ImageFont.load_default()


def _is_punct(char: str) -> bool:
    """Check if character is Chinese/Japanese punctuation that shouldn't start a line."""
    return char in '，。！？、；：」』》）】〗」》〉"\'!?,.;:)}>…～—'

def _is_open_punct(char: str) -> bool:
    """Check if character is opening punctuation that shouldn't end a line."""
    return char in '「『《（【〖〈『《"\'({[<'

def wrap_text_cjk(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """
    Wrap CJK text into lines that fit within max_width.
    Breaks at character boundaries, with smart handling of punctuation.
    """
    if not text:
        return []
    
    lines = []
    current_line = ''
    current_width = 0.0
    
    i = 0
    while i < len(text):
        char = text[i]
        
        # Handle newlines in source text
        if char == '\n':
            if current_line:
                lines.append(current_line)
            current_line = ''
            current_width = 0.0
            i += 1
            continue
        
        char_width = font.getlength(char)
        
        # If adding this char exceeds max width
        if current_width + char_width > max_width and current_line:
            # Try to keep trailing punctuation on current line
            if i + 1 < len(text) and _is_punct(text[i + 1]):
                # Look ahead - maybe push one more char
                pass
            
            lines.append(current_line)
            current_line = ''
            current_width = 0.0
            
            # Skip leading spaces on new line
            if char in ' 　':
                i += 1
                continue
        
        current_line += char
        current_width += char_width
        i += 1
    
    if current_line:
        lines.append(current_line)
    
    return lines


# CJK target languages that should use PIL rendering
CJK_LANGUAGES = {'CHS', 'CHT', 'JPN', 'KOR', 'zh', 'ja', 'ko', 'zh-CN', 'zh-TW', 'zh-HK'}

# Global font path, set before rendering
_font_path = None


def set_font(path: str):
    """Set the font path to use for CJK rendering."""
    global _font_path
    if path and os.path.exists(path):
        _font_path = path


def is_cjk_lang(target_lang: str) -> bool:
    """Check if target language is CJK."""
    if not target_lang:
        return False
    return target_lang in CJK_LANGUAGES


def put_text_horizontal_cn(
    font_size: int,
    text: str,
    width: int,
    height: int,
    alignment: str,
    reversed_direction: bool,
    fg: Tuple[int, int, int],
    bg: Optional[Tuple[int, int, int]],
    lang: str = 'zh',
    hyphenate: bool = True,
    line_spacing: int = 0,
    font_path: str = None,
) -> np.ndarray:
    """
    Render CJK text using PIL. Drop-in replacement for text_render.put_text_horizontal().
    
    Returns: RGBA numpy array (h, w, 4)
    """
    import cv2
    
    if not text:
        return np.zeros((1, 1, 4), dtype=np.uint8)
    
    # Load font
    font = None
    fp = font_path or _font_path
    if fp and os.path.exists(fp):
        font = ImageFont.truetype(fp, font_size)
    if font is None:
        font = _get_cjk_font(font_size)
    
    # Line spacing for CJK - slightly more than Latin
    spacing_px = int(font_size * 0.15)
    
    # Determine max width for line wrapping
    effective_width = max(width, font_size * 3) - font_size // 2
    
    # === Adaptive font sizing: if text won't fit, scale down ===
    # Try current font size first, then progressively reduce
    for _attempt in range(3):  # Max 3 reduction attempts
        lines = wrap_text_cjk(text, font, effective_width)
        if not lines:
            lines = [text]
        
        n_lines = len(lines)
        line_height = font.getbbox('啊')[3] - font.getbbox('啊')[1]
        total_text_h = line_height * n_lines + spacing_px * (n_lines - 1)
        
        # Check if text height fits within region
        if total_text_h <= height + font_size or _attempt == 2:
            break
        
        # Reduce font size and recalculate
        font_size = max(int(font_size * 0.8), 10)
        font = ImageFont.truetype(fp, font_size) if fp and os.path.exists(fp) else _get_cjk_font(font_size)
        spacing_px = int(font_size * 0.15)
        effective_width = max(width, font_size * 3) - font_size // 2
    
    # Stroke width - thicker for better visibility
    stroke_width = max(int(font_size * 0.15), 2)
    
    # Canvas dimensions
    n_lines = len(lines)
    max_line_width = max(font.getlength(line) for line in lines)
    
    canvas_w = int(max_line_width + stroke_width * 4)
    canvas_h = int(line_height * n_lines + spacing_px * (n_lines - 1) + stroke_width * 4)
    
    canvas_w = max(canvas_w, 4)
    canvas_h = max(canvas_h, 4)
    
    # Create RGBA canvas
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Colors - ensure they are proper int tuples (not numpy arrays)
    def _to_rgb_tuple(c):
        if c is None:
            return None
        try:
            return tuple(int(v) for v in c)
        except (TypeError, ValueError):
            return (0, 0, 0)
    
    text_fill = _to_rgb_tuple(fg)
    # bg can be a numpy array or None — check properly
    has_bg = bg is not None and not (hasattr(bg, 'any') and not bg.any())
    stroke_fill = _to_rgb_tuple(bg) if has_bg else (255, 255, 255)
    sw_int = int(stroke_width)
    
    for i, line in enumerate(lines):
        y_pos = sw_int * 2 + i * (line_height + spacing_px)
        line_width = font.getlength(line)
        
        if alignment == 'center':
            x_pos = (canvas_w - line_width) / 2
        elif alignment == 'right':
            x_pos = canvas_w - line_width - sw_int * 2
        else:
            x_pos = sw_int * 2
        
        # PIL 12.x stroke rendering - ensure all params are proper types
        text_pos = (int(x_pos), int(y_pos))
        try:
            draw.text(
                text_pos,
                line,
                font=font,
                fill=text_fill,
                stroke_width=sw_int,
                stroke_fill=stroke_fill,
            )
        except Exception:
            # Fallback: draw stroke manually via offset
            if bg:
                for dx in range(-sw_int, sw_int + 1):
                    for dy in range(-sw_int, sw_int + 1):
                        if dx*dx + dy*dy <= sw_int*sw_int:
                            draw.text(
                                (text_pos[0] + dx, text_pos[1] + dy),
                                line, font=font, fill=stroke_fill
                            )
            draw.text(text_pos, line, font=font, fill=text_fill)
    
    # Crop to content (like cv2.boundingRect does in the original)
    result = np.array(canvas)
    alpha = result[:, :, 3]
    if alpha.max() == 0:
        return result
    
    coords = cv2.findNonZero(alpha)
    if coords is None:
        return result
    x, y, w, h = cv2.boundingRect(coords)
    return result[y:y+h, x:x+w]


def render_textblock_list_cn(
    font_path: str,
    img: np.ndarray,
    text_regions: list,
    original_img: np.ndarray = None,
) -> np.ndarray:
    """
    Render all text regions using PIL-based CJK rendering.
    Takes inpainted image and text regions, returns image with text.
    
    This is a simplified version that does direct PIL compositing,
    avoiding the freetype+OpenCV warp pipeline entirely.
    """
    from PIL import Image as PILImage
    
    img_pil = PILImage.fromarray(img).convert('RGBA')
    img_w, img_h = img_pil.size
    
    for region in text_regions:
        translation = region.get_translation_for_rendering() if hasattr(region, 'get_translation_for_rendering') else region.translation
        if not translation:
            continue
        
        # Get the bounding box for this text region
        # The region has min_rect (4 corners) and xyxy (axis-aligned bbox)
        x1, y1, x2, y2 = map(int, region.xyxy)
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        
        # Determine font size based on region height
        font_size = max(region.font_size if hasattr(region, 'font_size') and region.font_size > 0 else 16, 10)
        
        # Adaptive sizing: if text is short and region is large, use larger font
        if len(translation) < 15 and bbox_h > 50:
            # Try to scale up
            proposed_size = int(bbox_h / len(translation.split('\n')) * 0.7)
            font_size = min(proposed_size, font_size)
        
        font_size = min(font_size, 100)  # Cap
        font_size = max(font_size, 12)   # Floor
        
        # Load font
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = _get_cjk_font(font_size)
        
        # Wrap text
        # Add padding so text doesn't touch bubble edges
        padding = int(font_size * 0.3)
        max_line_w = bbox_w - padding * 2
        lines = wrap_text_cjk(translation, font, max_line_w)
        
        if not lines:
            continue
        
        # Calculate text block dimensions
        line_height = font.getbbox('测')[3] - font.getbbox('测')[1]
        spacing = int(font_size * 0.2)
        text_block_h = line_height * len(lines) + spacing * (len(lines) - 1)
        text_block_w = max(font.getlength(line) for line in lines)
        
        # Stroke
        stroke_w = max(int(font_size * 0.1), 1)
        
        # Determine foreground/background colors from region
        fg, bg = (0, 0, 0), (255, 255, 255)  # Default: black text, white stroke
        if hasattr(region, 'get_font_colors'):
            fg, bg = region.get_font_colors()
        
        # Create a text overlay
        # Add extra space for stroke
        text_canvas_w = int(text_block_w + stroke_w * 4 + padding * 2)
        text_canvas_h = int(text_block_h + stroke_w * 4 + padding * 2)
        text_canvas = PILImage.new('RGBA', (text_canvas_w, text_canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_canvas)
        draw.fontmode = 'L'
        
        for i, line in enumerate(lines):
            y = stroke_w * 2 + padding + i * (line_height + spacing)
            line_w = font.getlength(line)
            x = (text_canvas_w - line_w) / 2  # Center
            
            draw.text(
                (x, y),
                line,
                font=font,
                fill=fg,
                stroke_width=stroke_w,
                stroke_fill=bg,
            )
        
        # Paste text overlay onto image, centered in the region
        paste_x = x1 + (bbox_w - text_canvas_w) // 2
        paste_y = y1 + (bbox_h - text_canvas_h) // 2
        
        # Clamp to image bounds
        paste_x = max(0, min(paste_x, img_w - text_canvas_w))
        paste_y = max(0, min(paste_y, img_h - text_canvas_h))
        
        # Composite
        img_pil.paste(text_canvas, (paste_x, paste_y), text_canvas)
    
    return np.array(img_pil.convert('RGB'))
