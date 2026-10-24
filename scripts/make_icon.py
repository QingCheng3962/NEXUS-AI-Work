"""生成 NEXUS 应用图标（构建时使用）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon() -> Path:
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 背景渐变
    gradient = Image.new("RGBA", (size, size))
    top = (99, 102, 241)
    bottom = (34, 211, 238)
    pixels = gradient.load()
    for y in range(size):
        ratio = y / (size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)) + (255,)
        for x in range(size):
            pixels[x, y] = color

    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=220, fill=255)
    image.paste(gradient, (0, 0), mask)

    # 内部深色玻璃层
    inner = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rounded_rectangle(
        (74, 74, size - 74, size - 74), radius=160, fill=(9, 14, 28, 205)
    )
    image.alpha_composite(inner)

    draw = ImageDraw.Draw(image)
    # 环
    draw.arc((235, 235, size - 235, size - 235), start=205, end=515, fill=(34, 211, 238, 255), width=22)
    draw.arc((300, 300, size - 300, size - 300), start=25, end=155, fill=(167, 139, 250, 230), width=14)

    # 字母 N
    font = _font(470)
    text = "N"
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        ((size - width) / 2 - box[0], (size - height) / 2 - box[1] - 10),
        text,
        font=font,
        fill=(255, 255, 255, 255),
    )

    icon_path = ASSETS / "nexus.ico"
    image.save(icon_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.resize((256, 256), Image.LANCZOS).save(ASSETS / "nexus.png")
    return icon_path


if __name__ == "__main__":
    print(make_icon())
