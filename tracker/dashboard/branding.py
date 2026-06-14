"""Pokemon-themed branding for PokeHart Collectors: favicon, header logo, CSS.

The title is rendered as HTML text using the embedded "Pokemon Solid" web font
(base64 @font-face, self-contained) so it genuinely looks like the Pokemon logo --
SVG-image headers can't load custom fonts, so the wordmark is real HTML text
beside a base64 Poke Ball image.
"""

import base64
from pathlib import Path

_FONT = Path(__file__).resolve().parent / "assets" / "pokemon-solid.woff"


def make_favicon():
    """A Poke Ball PNG for the browser tab (falls back to an emoji if PIL missing)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return "\U0001F3B4"
    s = 128
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    d.ellipse([3, 3, s - 3, s - 3], fill=(26, 26, 26, 255))
    d.ellipse([9, 9, s - 9, s - 9], fill=(244, 244, 244, 255))
    d.pieslice([9, 9, s - 9, s - 9], 180, 360, fill=(238, 21, 21, 255))
    band = int(s * 0.085)
    d.rectangle([9, c - band, s - 9, c + band], fill=(26, 26, 26, 255))
    r = int(s * 0.19)
    d.ellipse([c - r, c - r, c + r, c + r], fill=(26, 26, 26, 255))
    rr = int(s * 0.13)
    d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=(250, 250, 250, 255))
    return img


_BALL_SVG = """<svg viewBox="-104 -104 208 208" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="bk" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#ff4d4d"/><stop offset="55%" stop-color="#ee1515"/><stop offset="100%" stop-color="#b00010"/>
  </linearGradient></defs>
  <circle r="100" fill="#1a1a1a"/>
  <path d="M -95 0 A 95 95 0 0 1 95 0 Z" fill="url(#bk)"/>
  <path d="M -95 0 A 95 95 0 0 0 95 0 Z" fill="#f5f5f5"/>
  <rect x="-96" y="-13" width="192" height="26" fill="#1a1a1a"/>
  <circle r="30" fill="#1a1a1a"/><circle r="20" fill="#ffffff"/>
  <ellipse cx="-38" cy="-42" rx="34" ry="22" fill="#ffffff" opacity="0.28" transform="rotate(-35 -38 -42)"/>
</svg>"""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _font_b64() -> str:
    try:
        return _b64(_FONT.read_bytes())
    except Exception:
        return ""


def header_html():
    font = _font_b64()
    ball = _b64(_BALL_SVG.encode("utf-8"))
    face = (f"@font-face {{ font-family:'PokeSolid'; font-display:swap; "
            f"src:url(data:font/woff;base64,{font}) format('woff'); }}" if font else "")
    title_font = "'PokeSolid', 'Arial Black', sans-serif" if font else "'Arial Black', sans-serif"
    return f"""
<style>
{face}
.ph-frame {{ width:fit-content; max-width:94%; margin:0.5rem auto 1.1rem; padding:12px 34px;
  border:2px solid transparent; border-radius:18px;
  background:linear-gradient(180deg,#141925,#0e1118) padding-box,
             linear-gradient(160deg,#facc15,#3b82f6,#22d3ee) border-box;
  box-shadow:0 0 26px rgba(59,130,246,0.38); }}
.ph-wrap {{ display:flex; align-items:center; justify-content:center; gap:22px; margin:0; }}
.ph-ball {{ height:92px; width:auto; flex:0 0 auto; }}
.ph-title {{ font-family:{title_font}; color:#FFCB05; font-size:74px; line-height:1.02;
  -webkit-text-stroke:3.6px #2a5fc0; paint-order:stroke fill;
  text-shadow:2px 6px 0 rgba(12,34,92,0.6); }}
.ph-collect {{ font-family:{title_font}; color:#FFCB05; font-size:27px; letter-spacing:3px;
  -webkit-text-stroke:1.6px #2a5fc0; paint-order:stroke fill; margin-top:3px; }}
.ph-tag {{ color:#8A92A0; font-family:Verdana, sans-serif; font-size:12px; margin-top:6px; }}
</style>
<div class="ph-frame"><div class="ph-wrap">
  <img class="ph-ball" src="data:image/svg+xml;base64,{ball}" alt=""/>
  <div>
    <div class="ph-title">PokeHa<span style="display:inline-block;width:0.07em"></span>rt</div>
    <div class="ph-collect">COLLECTORS</div>
    <div class="ph-tag">UK price comparison · restock alerts · profit strategy</div>
  </div>
</div></div>
"""


CSS = """
<style>
  .block-container { padding-top: 2.2rem; }

  div[class*="st-key-settile_"] {
    border-radius: 16px !important;
    border: 2px solid transparent !important;
    background: linear-gradient(180deg, #161a24, #0f1219) padding-box,
               linear-gradient(160deg, #facc15, #3b82f6, #22d3ee) border-box !important;
    box-shadow: 0 0 16px rgba(59,130,246,0.30);
    transition: transform .15s ease, box-shadow .15s ease;
  }
  div[class*="st-key-settile_"]:hover {
    transform: translateY(-4px);
    box-shadow: 0 0 26px rgba(59,130,246,0.65), 0 10px 26px rgba(0,0,0,.5);
  }

  .stButton > button, .stLinkButton > a {
    border-radius: 10px !important;
    font-weight: 700 !important;
  }
  div[data-testid="stImage"] img { object-fit: contain; }
</style>
"""
