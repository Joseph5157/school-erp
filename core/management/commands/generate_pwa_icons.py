"""Draw the app icons: the School ERP mark, an open book and a rising sun on a green tile.

Code-drawn from the same 64-unit drawing as templates/partials/_brand_mark.html. Re-run after
changing either: `python manage.py generate_pwa_icons`.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from core.pwa_views import ICON_COLOUR

SUPERSAMPLE = 4  # draw large, then shrink, for smooth edges
UNITS = 64  # the mark's drawing grid
WHITE = (255, 255, 255, 255)
GOLD = "#e9b949"
WASH = "#e3efe9"

RAYS = (((32, 7), (32, 12)), ((17.5, 13), (20.5, 17)), ((46.5, 13), (43.5, 17)))
SUN = ((32, 27), 9.5)
# The left page: top curve, then bottom curve. The right page mirrors it.
PAGE_TOP = ((8, 31), (16, 27), (25, 28), (31, 33))
PAGE_BOTTOM = ((31, 54), (25, 49), (16, 48), (8, 52))
# The text lines on the left page. The right page mirrors them.
TEXT_LINES = (((13, 37), (18, 36), (22, 37), (26, 39)), ((13, 43), (18, 42), (22, 43), (26, 45)))


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


def mirror(points):
    return [(UNITS - x, y) for x, y in points]


def draw_icon(size, *, rounded, glyph_scale):
    """`rounded` icons keep transparent corners; the others fill the whole square (maskable/Apple).

    `glyph_scale` shrinks the book and sun about the centre; maskable icons keep them inside the
    central safe zone so a circular crop never clips them.
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

    def stroke(points, colour, width):
        placed = place(points)
        pixels = round(width * unit)
        draw.line(placed, fill=colour, width=pixels, joint="curve")
        for x, y in (placed[0], placed[-1]):  # round caps
            draw.ellipse(
                (x - pixels / 2, y - pixels / 2, x + pixels / 2, y + pixels / 2), fill=colour
            )

    for ray in RAYS:
        stroke(ray, GOLD, 2.6)
    (sun_x, sun_y), radius = SUN
    (x, y), = place([(sun_x, sun_y)])
    draw.ellipse((x - radius * unit, y - radius * unit, x + radius * unit, y + radius * unit), fill=GOLD)

    page = curve(PAGE_TOP) + curve(PAGE_BOTTOM)
    for outline in (page, mirror(page)):
        draw.polygon(place(outline), fill=WHITE)
    for line in TEXT_LINES:
        stroke(curve(line), WASH, 2)
        stroke(mirror(curve(line)), WASH, 2)
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
