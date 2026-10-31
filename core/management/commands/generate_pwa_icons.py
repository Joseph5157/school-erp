"""Draw the placeholder app icons (PWA Gate 1): a cobalt tile with a white open book.

Code-drawn so no binary design asset is needed before final branding is approved. Re-run after
changing the colour or glyph: `python manage.py generate_pwa_icons`.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from core.pwa_views import ICON_COLOUR

SUPERSAMPLE = 4  # draw large, then shrink, for smooth edges
WHITE = (255, 255, 255, 255)

# The two pages of the open book, left and right, in glyph units: x runs -1..1, y is down.
LEFT_PAGE = [(-0.95, -0.52), (-0.07, -0.30), (-0.07, 0.62), (-0.95, 0.40)]
RIGHT_PAGE = [(-x, y) for x, y in LEFT_PAGE]


def draw_icon(size, *, rounded, glyph_width):
    """`rounded` icons keep transparent corners; the others fill the whole square (maskable/Apple).

    `glyph_width` is the book's width as a fraction of the icon; maskable icons keep it inside the
    central safe zone so a circular crop never clips it.
    """
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=ICON_COLOUR)
    else:
        draw.rectangle((0, 0, big - 1, big - 1), fill=ICON_COLOUR)
    scale = big * glyph_width / 2
    centre = big / 2
    for page in (LEFT_PAGE, RIGHT_PAGE):
        draw.polygon([(centre + x * scale, centre + y * scale) for x, y in page], fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


class Command(BaseCommand):
    help = "Generate the PWA icons into static/pwa/."

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / "static" / "pwa"
        out.mkdir(parents=True, exist_ok=True)
        icons = {
            "icon-192.png": draw_icon(192, rounded=True, glyph_width=0.62),
            "icon-512.png": draw_icon(512, rounded=True, glyph_width=0.62),
            # Maskable safe zone is the central 80%: keep the glyph well inside it.
            "icon-maskable-512.png": draw_icon(512, rounded=False, glyph_width=0.50),
            # iOS rounds the corners itself and turns transparency black, so this one is opaque.
            "apple-touch-icon.png": draw_icon(180, rounded=False, glyph_width=0.58),
        }
        for name, image in icons.items():
            image.save(out / name, optimize=True)
            self.stdout.write(f"wrote static/pwa/{name}")
