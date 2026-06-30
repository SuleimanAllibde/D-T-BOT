import io
import os
from PIL import Image, ImageDraw, ImageFilter

CARD_WIDTH = 1296
CARD_HEIGHT = 864 

DEFAULT_BG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pics", "welcome.png")


async def _load_background():
    try:
        if os.path.exists(DEFAULT_BG):
            img = Image.open(DEFAULT_BG)
            return img.convert("RGBA")
    except Exception:
        pass
    return None


def _make_avatar(avatar_bytes: bytes, size: int):
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.LANCZOS)
    
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse([0, 0, size, size], fill=255)
    
    gp = max(16, size // 8)
    glow = Image.new("RGBA", (size + gp * 2, size + gp * 2), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([0, 0, size + gp * 2, size + gp * 2], fill=(88, 101, 242, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(max(6, size // 12)))
    
    return avatar, mask, glow, gp


async def generate_card(avatar_bytes: bytes,
                        avatar_x: int = 80, avatar_y: int = 86,
                        avatar_size: int = 128) -> io.BytesIO:
                        
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (32, 34, 37))

    bg_img = await _load_background()
    if bg_img:
        bg_img = bg_img.resize((CARD_WIDTH, CARD_HEIGHT), Image.LANCZOS)
        card.paste(bg_img, (0, 0))

    avatar_img, mask, glow, gp = _make_avatar(avatar_bytes, avatar_size)
    card_rgba = card.convert("RGBA")
    card_rgba.paste(glow, (avatar_x - gp, avatar_y - gp), glow)
    card_rgba.paste(avatar_img, (avatar_x, avatar_y), mask)
    
    final_card = card_rgba.convert("RGB")

    buf = io.BytesIO()
    final_card.save(buf, "JPEG", quality=95, optimize=True)
    buf.seek(0)
    return buf