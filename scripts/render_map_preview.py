#!/usr/bin/env python3
"""Rasterise a map preview SVG into a PNG so the geometry can be looked at.

`npm run map:preview` writes the app's own map SVG (the same one the browser
renders) out of a real mount, with no browser involved.  An SVG is fine to open
in a browser, but a PNG is easier to drop next to a design review -- and easier
to look at when the viewer is a terminal-adjacent tool.

    cd frontend && npm run map:preview              # -> frontend/.cache/map-preview.svg
    .venv/bin/python scripts/render_map_preview.py  # -> frontend/.cache/map-preview.png

This is a development tool, not part of the product or the test suite.  It needs
Pillow, which the prototype environment already has.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SUPERSAMPLE = 2


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:  # pragma: no cover - only on machines without DejaVu
        return ImageFont.load_default()


def _points(path: str, step: int) -> list[tuple[float, float]]:
    """Flatten an SVG path of M/L/Q commands into screen points."""
    out: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    for command, args in re.findall(r"([MLQ])([-\d.,\s]+)", path):
        numbers = [float(value) for value in re.split(r"[,\s]+", args.strip()) if value]
        if command in {"M", "L"}:
            for index in range(0, len(numbers), 2):
                current = (numbers[index] * step, numbers[index + 1] * step)
                out.append(current)
        elif command == "Q":
            x0, y0 = current
            cx, cy, x1, y1 = [value * step for value in numbers[:4]]
            for tick in (index / 16 for index in range(1, 17)):
                rest = 1 - tick
                out.append(
                    (
                        rest * rest * x0 + 2 * rest * tick * cx + tick * tick * x1,
                        rest * rest * y0 + 2 * rest * tick * cy + tick * tick * y1,
                    )
                )
            current = (x1, y1)
    return out


TOKEN_RE = re.compile(r":root\s*\{(.*?)\}", re.S)
TOKEN_DEF = re.compile(r"--([a-z0-9-]+):\s*([^;]+);")


def tokens_from_css(css_path: Path) -> dict[str, str]:
    """The app's own custom properties, so the preview is the app's colours."""
    if not css_path.exists():
        return {}
    block = TOKEN_RE.search(css_path.read_text())
    if not block:
        return {}
    return {name: value.strip() for name, value in TOKEN_DEF.findall(block.group(1))}


def resolve_tokens(svg: str, tokens: dict[str, str]) -> str:
    for _ in range(4):  # tokens may refer to other tokens
        changed = False
        for name, value in tokens.items():
            marker = f"var(--{name})"
            if marker in svg:
                svg = svg.replace(marker, value)
                changed = True
        if not changed:
            break
    return svg


def render(svg_path: Path, out_path: Path, css_path: Path | None = None) -> tuple[int, int]:
    svg = svg_path.read_text()
    svg = resolve_tokens(svg, tokens_from_css(css_path) if css_path else {})
    view = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not view:
        raise SystemExit(f"{svg_path} has no viewBox")
    width, height = int(float(view.group(1))), int(float(view.group(2)))
    scale = SUPERSAMPLE
    ground = re.search(r'<rect[^>]*fill="(#[0-9a-fA-F]{6})"', svg)
    ground = ground.group(1) if ground else "#f1f4fb"

    image = Image.new("RGB", (width * scale, height * scale), ground)
    draw = ImageDraw.Draw(image)
    label_font = _font(FONT, 9 * scale)
    grid_font = _font(FONT_BOLD, 8 * scale)
    terminal_font = _font(FONT_BOLD, 11 * scale)

    patterns = {
        match.group(1): {
            "size": (float(match.group(2)), float(match.group(3))),
            "stroke": (re.search(r'stroke="([^"]+)"', match.group(0)) or [None, "#e4e8f3"])[1],
            "width": float((re.search(r'strokeWidth="([\d.]+)"', match.group(0)) or [None, "1"])[1]),
        }
        for match in re.finditer(
            r'<pattern id="([^"]+)" width="([\d.]+)" height="([\d.]+)"[^>]*>(.*?)</pattern>',
            svg,
            re.S,
        )
        if "vignette" not in match.group(1)
    }
    for match in re.finditer(r'<rect[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"[^>]*fill="url\(#([^)]+)\)"', svg):
        pattern = patterns.get(match.group(3))
        if not pattern:
            continue
        step_x, step_y = pattern["size"]
        colour = pattern["stroke"] if pattern["stroke"].startswith("#") else "#e4e8f3"
        x = 0.0
        while x <= float(match.group(1)):
            draw.line([x * scale, 0, x * scale, height * scale], fill=colour, width=max(1, int(pattern["width"] * scale)))
            x += step_x
        y = 0.0
        while y <= float(match.group(2)):
            draw.line([0, y * scale, width * scale, y * scale], fill=colour, width=max(1, int(pattern["width"] * scale)))
            y += step_y

    for line in re.finditer(r"<line[^>]*>", svg):
        numbers = {key: float(value) for key, value in re.findall(r'(x1|y1|x2|y2)="([-\d.]+)"', line.group(0))}
        if len(numbers) == 4:
            draw.line(
                [numbers["x1"] * scale, numbers["y1"] * scale, numbers["x2"] * scale, numbers["y2"] * scale],
                fill="#d3d8e3",
                width=1,
            )

    def stroke_group(selector: str, casing: bool) -> None:
        for match in re.finditer(rf'<path class="{selector}"[^>]*d="([^"]+)"([^>]*)>', svg):
            attrs = match.group(2)
            width_match = re.search(r'strokeWidth="([\d.]+)"', attrs)
            stroke_width = float(width_match.group(1)) if width_match else 6.0
            stroke = re.search(r'stroke="([^"]+)"', attrs)
            colour = stroke.group(1) if stroke and stroke.group(1).startswith("#") else "#ffffff"
            dashed = re.search(r'strokeDasharray="([^"]+)"', attrs)
            points = _points(match.group(1), scale)
            if casing:
                draw.line(points, fill="#ffffff", width=int(stroke_width * scale), joint="curve")
                continue
            if dashed:
                for start, end in zip(points, points[1:]):
                    if (start[0] + start[1]) % 18 < 9:
                        draw.line([start, end], fill=colour, width=int(stroke_width * scale))
            else:
                draw.line(points, fill=colour, width=int(stroke_width * scale), joint="curve")

    stroke_group("map__route-casing", casing=True)
    stroke_group("map__route", casing=False)

    for match in re.finditer(
        r'<circle[^>]*cx="([-\d.]+)"[^>]*cy="([-\d.]+)"[^>]*r="([\d.]+)"[^>]*class="map__stop"'
        r'[^>]*stroke="([^"]+)"',
        svg,
    ):
        x, y, radius, colour = (
            float(match.group(1)) * scale,
            float(match.group(2)) * scale,
            float(match.group(3)) * scale,
            match.group(4),
        )
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="#ffffff", outline=colour, width=2 * scale)

    for match in re.finditer(r'<circle[^>]*cx="([^"]+)"[^>]*cy="([^"]+)"[^>]*r="([^"]+)"[^>]*fill="([^"]*)"[^>]*stroke="([^"]*)"', svg):
        x = float(match.group(1)) * scale
        y = float(match.group(2)) * scale
        radius = float(match.group(3)) * scale
        fill = match.group(4) if match.group(4).startswith("#") else "#ffffff"
        stroke = match.group(5) if match.group(5).startswith("#") else "#0b0e16"
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=fill, outline=stroke, width=int(2.4 * scale))

    for match in re.finditer(r'<text[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"([^>]*)>([^<]+)</text>', svg):
        x, y = float(match.group(1)) * scale, float(match.group(2)) * scale
        attrs, text = match.group(3), match.group(4)
        class_match = re.search(r'class="([^"]+)"', attrs)
        css_class = class_match.group(1) if class_match else ""
        anchor = "mm" if "middle" in attrs else "lm"
        if "grid" in css_class:
            draw.text((x, y), text, font=grid_font, fill="#9aa1b1", anchor=anchor)
            continue
        font = terminal_font if "map__label" in css_class else label_font
        colour = "#0b0e16" if "map__label" in css_class else "#202534"
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                draw.text((x + dx, y + dy), text, font=font, fill="#ffffff", anchor=anchor)
        draw.text((x, y), text, font=font, fill=colour, anchor=anchor)

    image.resize((width, height), Image.LANCZOS).save(out_path)
    return width, height


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    svg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "frontend/.cache/map-preview.svg"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else svg_path.with_suffix(".png")
    if not svg_path.exists():
        raise SystemExit(f"no {svg_path} -- run `cd frontend && npm run map:preview` first")
    width, height = render(svg_path, out_path, root / "frontend/src/styles/app.css")
    print(f"wrote {out_path} ({width}x{height})")


if __name__ == "__main__":
    main()
