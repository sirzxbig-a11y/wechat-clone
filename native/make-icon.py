#!/usr/bin/env python3
# 生成微信双开重签工具的 App 图标（1024x1024 PNG）
# 用法：python3 make-icon.py
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icon_1024.png")

W = 1024
SS = 2
C = W * SS  # 2048 超采样


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


# ---------- 背景：绿色渐变圆角方块 ----------
img = Image.new("RGBA", (C, C), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
top = (58, 214, 132)   # #3AD684
bot = (8, 150, 82)     # #089652
for y in range(C):
    t = y / (C - 1)
    d.line([(0, y), (C, y)], fill=lerp(top, bot, t) + (255,))

mask = Image.new("L", (C, C), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0, 0, C - 1, C - 1], radius=int(C * 0.225), fill=255)

bg = Image.new("RGBA", (C, C), (0, 0, 0, 0))
bg.paste(img, (0, 0), mask)

S = C / 1024.0


def px(v):
    return int(v * S)


d = ImageDraw.Draw(bg)

# ---------- 后面那个气泡（略透明，制造层次）----------
d.rounded_rectangle([px(165), px(225), px(600), px(595)], radius=px(96), fill=(255, 255, 255, 215))
d.polygon([(px(250), px(545)), (px(250), px(675)), (px(370), px(588))], fill=(255, 255, 255, 215))

# ---------- 前面气泡的投影（紧致、轻）----------
shadow = Image.new("RGBA", (C, C), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle([px(428), px(440), px(812), px(788)], radius=px(98), fill=(0, 60, 30, 60))
shadow = shadow.filter(ImageFilter.GaussianBlur(px(16)))
bg.alpha_composite(shadow)
d = ImageDraw.Draw(bg)

# ---------- 绿色分隔描边（画在气泡底下，露出一圈背景色）----------
d.rounded_rectangle([px(410), px(402), px(820), px(780)], radius=px(104), fill=(14, 158, 88, 255))

# ---------- 前面气泡 ----------
d.rounded_rectangle([px(426), px(418), px(804), px(764)], radius=px(96), fill=(255, 255, 255, 255))
d.polygon([(px(688), px(706)), (px(688), px(826)), (px(578), px(738))], fill=(255, 255, 255, 255))

# 气泡里的两条"聊天内容"线
d.rounded_rectangle([px(470), px(548), px(730), px(592)], radius=px(22), fill=(214, 226, 235, 255))
d.rounded_rectangle([px(470), px(632), px(636), px(676)], radius=px(22), fill=(214, 226, 235, 255))

# ---------- ×2 徽章 ----------
d.ellipse([px(706), px(96), px(934), px(324)], fill=(255, 255, 255, 255))

font = None
for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/System/Library/Fonts/Helvetica.ttc",
          "/System/Library/Fonts/SFNS.ttf"):
    if os.path.exists(p):
        try:
            font = ImageFont.truetype(p, px(126))
            break
        except Exception:
            pass
if font is None:
    font = ImageFont.load_default()

text = "×2"
bbox = d.textbbox((0, 0), text, font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
cx = (706 + 934) / 2 * S
cy = (96 + 324) / 2 * S
d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=(10, 150, 82, 255))

out = bg.resize((W, W), Image.LANCZOS)
out.save(OUT)
print("saved:", OUT)
