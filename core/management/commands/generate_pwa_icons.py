"""Draw the app icons: the Everclass ERP mark, a loop with a sprout, on a white tile.

Code-drawn from the same 64-unit drawing as templates/partials/_brand_mark.html and
static/brand/everclass-mark.svg. Re-run after changing any of them: `python manage.py generate_pwa_icons`.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from core.pwa_views import ICON_COLOUR

SUPERSAMPLE = 4  # draw large, then shrink, for smooth edges
UNITS = 64  # the mark's drawing grid
TEAL = "#1bb5a8"
NAVY = "#0b2a4a"
YELLOW = "#f5b82e"

# Each shape is a run of cubic Beziers, copied from the SVG paths.
LOOP = (
    ((32, 37), (38, 25), (54, 25), (54, 37)),
    ((54, 37), (54, 49), (38, 49), (32, 37)),
    ((32, 37), (26, 25), (10, 25), (10, 37)),
    ((10, 37), (10, 49), (26, 49), (32, 37)),
)
SWEEP = LOOP[1]  # the navy lower-right part of the loop
OVER = ((30, 41), (34, 33))  # the teal strand redrawn over the crossing
CRESCENT = (((40, 41), (45, 43.5), (50, 41), (50, 35)), ((50, 35), (48, 38.5), (44.5, 40.5), (40, 41)))
STEM = ((45, 26), (45, 22), (45.5, 19), (47.5, 16))
LEAVES = (
    (((47.5, 16), (49.5, 11.5), (53, 10), (56, 10.5)), ((56, 10.5), (54.5, 14.5), (51, 16.5), (47.5, 16))),
    (((46, 20), (43, 18), (42, 15), (42.5, 12.5)), ((42.5, 12.5), (45.5, 13.5), (47, 16.5), (46, 20))),
)
LOOP_WIDTH = 5.5
STEM_WIDTH = 2.6


def curve(points, steps=32):
    """Points along a cubic Bezier."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    result = []
    for step in range(steps + 1):
        t = step / steps
        u = 1 - t
        result.append((
            u**3 * x0 + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3,
            u**3 * y0 + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3,
        ))
    return result


def run(segments):
    """Points along consecutive Beziers."""
    points = []
    for segment in segments:
        points.extend(curve(segment))
    return points


def draw_icon(size, *, rounded, glyph_scale):
    """`rounded` icons keep transparent corners; the others fill the whole square (maskable/Apple).

    `glyph_scale` shrinks the mark about the centre; maskable icons keep it inside the central
    safe zone so a circular crop never clips it.
    """
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=ICON_COLOUR)
    else:
        draw.rectangle((0, 0, big - 1, big - 1), fill=ICON_COLOUR)

    unit = big / UNITS * glyph_scale

    def place(points):
        return [
            (big / 2 + (x - UNITS / 2) * unit, big / 2 + (y - UNITS / 2) * unit) for x, y in points
        ]

    def stroke(points, colour, width, *, round_caps=True):
        placed = place(points)
        pixels = round(width * unit)
        draw.line(placed, fill=colour, width=pixels, joint="curve")
        if round_caps:  # a dot at every point smooths the joints and rounds both ends
            for x, y in placed:
                draw.ellipse(
                    (x - pixels / 2, y - pixels / 2, x + pixels / 2, y + pixels / 2), fill=colour
                )

    # Same order as the SVG: loop, crescent, navy sweep, the strand over the crossing, sprout.
    stroke(run(LOOP), TEAL, LOOP_WIDTH)
    draw.polygon(place(run(CRESCENT)), fill=YELLOW)
    stroke(curve(SWEEP), NAVY, LOOP_WIDTH, round_caps=False)
    stroke(list(OVER), TEAL, LOOP_WIDTH, round_caps=False)
    stroke(curve(STEM), TEAL, STEM_WIDTH)
    for leaf in LEAVES:
        draw.polygon(place(run(leaf)), fill=TEAL)
    return image.resize((size, size), Image.LANCZOS)


class Command(BaseCommand):
    help = "Generate the PWA icons into static/pwa/."

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / "static" / "pwa"
        out.mkdir(parents=True, exist_ok=True)
        icons = {
            "icon-192.png": draw_icon(192, rounded=True, glyph_scale=1),
            "icon-512.png": draw_icon(512, rounded=True, glyph_scale=1),
            # Maskable safe zone is the central 80%: keep the glyph well inside it.
            "icon-maskable-512.png": draw_icon(512, rounded=False, glyph_scale=0.72),
            # iOS rounds the corners itself and turns transparency black, so this one is opaque.
            "apple-touch-icon.png": draw_icon(180, rounded=False, glyph_scale=0.9),
        }
        for name, image in icons.items():
            image.save(out / name, optimize=True)
            self.stdout.write(f"wrote static/pwa/{name}")
