"""生成 Anvil 应用图标：极简灰色像素铁砧。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# 16 × 16 像素铁砧。H = 高光，B = 砧身，S = 阴影，. = 透明。
ANVIL_PIXELS = [
    "................",
    "................",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..BBBBBBBBBBBB..",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    ".....SSSSSS.....",
    "......SSSS......",
    "......SSSS......",
    ".....SSSSSS.....",
    "....SSSSSSSS....",
    "...SSSSSSSSSS...",
    "..SSSSSSSSSSSS..",
    "................",
]
PALETTE = {
    "H": (226, 232, 240, 255),
    "B": (148, 163, 184, 255),
    "S": (100, 116, 139, 255),
}


def make_icon() -> Path:
    pixel = 64
    size = pixel * 16
    image = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(image)

    # 深色圆角底板，和应用的极简灰色调一致。
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=int(size * 0.22),
        fill=(15, 23, 42, 255),
        outline=(71, 85, 105, 255),
        width=max(2, size // 128),
    )
    for y, row in enumerate(ANVIL_PIXELS):
        for x, cell in enumerate(row):
            color = PALETTE.get(cell)
            if color is None:
                continue
            draw.rectangle(
                (x * pixel, y * pixel, (x + 1) * pixel - 1, (y + 1) * pixel - 1),
                fill=color,
            )

    icon_path = ASSETS / "anvil.ico"
    image.save(
        icon_path,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    image.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "anvil.png")
    return icon_path


if __name__ == "__main__":
    path = make_icon()
    print(f"图标已生成：{path}")
