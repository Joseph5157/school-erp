"""HTML-to-PDF rendering for issued documents (spec D6: WeasyPrint)."""

import os
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

FONT_DIR = Path(settings.BASE_DIR) / "static" / "fonts"

# On Windows WeasyPrint finds Pango through MSYS2; Linux servers use system packages.
_MSYS2_BIN = r"C:\msys64\mingw64\bin"

_FONT_CSS = """
@font-face {{ font-family: 'DocLatin'; font-weight: 400; src: url('{regular}'); }}
@font-face {{ font-family: 'DocLatin'; font-weight: 700; src: url('{bold}'); }}
@font-face {{ font-family: 'DocTelugu'; src: url('{telugu}'); }}
"""


def render_pdf(template_name, context):
    """Render a template to PDF bytes. Fonts are bundled, never the server's."""
    if os.name == "nt" and os.path.isdir(_MSYS2_BIN):
        os.environ.setdefault("WEASYPRINT_DLL_DIRECTORIES", _MSYS2_BIN)
    from weasyprint import CSS, HTML  # lazy: needs system libraries (Pango)

    fonts = CSS(string=_FONT_CSS.format(
        regular=(FONT_DIR / "NotoSans-Regular.ttf").as_uri(),
        bold=(FONT_DIR / "NotoSans-Bold.ttf").as_uri(),
        telugu=(FONT_DIR / "NotoSansTelugu-Regular.ttf").as_uri(),
    ))
    html = render_to_string(template_name, context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(stylesheets=[fonts])
