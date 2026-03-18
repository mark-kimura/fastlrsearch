#!/usr/bin/env python3
"""Generate the FastLRSearch app icon (.icns).

Works on any platform (Linux, macOS, Windows). Requires Pillow.

Usage:
    python macos/generate_icon.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)


def create_icon_image(size: int) -> Image.Image:
    """Create the app icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded rectangle, dark blue-purple
    margin = int(size * 0.08)
    radius = int(size * 0.18)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(30, 36, 68),
    )

    # Magnifying glass circle
    cx, cy = int(size * 0.42), int(size * 0.40)
    r = int(size * 0.20)
    line_w = max(2, int(size * 0.04))
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=(100, 180, 255),
        width=line_w,
    )

    # Handle
    hx1 = cx + int(r * 0.7)
    hy1 = cy + int(r * 0.7)
    hx2 = cx + int(r * 1.4)
    hy2 = cy + int(r * 1.4)
    draw.line([hx1, hy1, hx2, hy2], fill=(100, 180, 255), width=line_w)

    # "F" letter inside the magnifying glass
    font_size = int(r * 1.2)
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",          # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "C:\\Windows\\Fonts\\arial.ttf",                 # Windows
    ]
    font = None
    for fp in font_paths:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "F", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw // 2, cy - th // 2 - bbox[1]),
        "F",
        fill=(220, 230, 255),
        font=font,
    )

    return img


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_icns = script_dir / "AppIcon.icns"

    # Pillow can save .icns directly on any platform.
    # It needs a list of sizes to include in the icon.
    sizes = [16, 32, 48, 64, 128, 256, 512, 1024]
    images = [create_icon_image(s) for s in sizes]

    # Save as .icns — Pillow uses the largest image and appends the rest
    images[-1].save(
        output_icns,
        format="ICNS",
        append_images=images[:-1],
    )
    print(f"Created {output_icns}")

    # Save as .ico for Windows (sizes up to 256px)
    ico_sizes = [16, 32, 48, 64, 128, 256]
    ico_images = [create_icon_image(s) for s in ico_sizes]
    windows_dir = project_root / "windows"
    windows_dir.mkdir(exist_ok=True)
    output_ico = windows_dir / "FastLRSearch.ico"
    ico_images[-1].save(
        output_ico,
        format="ICO",
        append_images=ico_images[:-1],
    )
    print(f"Created {output_ico}")

    # Also save a PNG preview
    output_png = script_dir / "AppIcon_512.png"
    images[sizes.index(512)].save(output_png)
    print(f"Created {output_png} (preview)")


if __name__ == "__main__":
    main()
