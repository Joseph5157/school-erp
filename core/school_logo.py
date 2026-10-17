"""School logo validation, normalization and versioning (ADR 0020, Gate 1).

An upload is decoded with Pillow, checked against the size and dimension
limits, stripped of metadata, downscaled and re-encoded as PNG. Only that PNG
is stored, as an immutable `SchoolLogo` version.
"""

import hashlib
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

from accounts.models import SecurityEvent
from core.models import SchoolLogo

MAX_UPLOAD_BYTES = 512 * 1024
MAX_DIMENSION = 2000
STORED_WIDTH = 600
ACCEPTED_FORMATS = ("PNG", "JPEG")

_UNREADABLE = "This file is not a readable PNG or JPEG image."


def _decode(data):
    """Open and fully decode `data`, enforcing format and dimension limits."""
    try:
        image = Image.open(BytesIO(data))
        if image.format not in ACCEPTED_FORMATS:
            raise ValidationError("Only PNG and JPEG images are accepted.")
        width, height = image.size
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise ValidationError(
                f"The image is {width} x {height} pixels; the limit is "
                f"{MAX_DIMENSION} x {MAX_DIMENSION}."
            )
        if width < 1 or height < 1:
            raise ValidationError(_UNREADABLE)
        image.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError,
            ValueError, EOFError):
        raise ValidationError(_UNREADABLE) from None
    return image


def normalize(data):
    """Validate uploaded bytes and return the normalized PNG bytes.

    Raises ValidationError for an oversized, unreadable, mis-typed or
    over-dimension image. Nothing is shrunk to fit the limits.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("The file is larger than 512 KB.")
    # WeasyPrint switches Pillow into truncated-image tolerance when it is imported;
    # a cut-off upload must be refused, so decode with that tolerance off.
    tolerant = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        image = _decode(data)
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = tolerant

    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    if image.width > STORED_WIDTH:
        new_height = max(1, round(image.height * STORED_WIDTH / image.width))
        image = image.resize((STORED_WIDTH, new_height), Image.LANCZOS)
    # A fresh image carries no EXIF, ICC profile or text chunks from the upload.
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    out = BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue()


def read_upload(upload):
    """Read an uploaded file, refusing anything over the byte limit."""
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("The file is larger than 512 KB.")
    return data


@transaction.atomic
def replace_logo(school, data, *, actor):
    """Validate `data` and add it as the school's newest logo version."""
    png = normalize(data)
    digest = hashlib.sha256(png).hexdigest()
    current = SchoolLogo.current_for(school)
    if current is not None and current.sha256 == digest:
        raise ValidationError("This is already the current logo.")
    version = SchoolLogo.objects.create(
        school=school, image=png, sha256=digest, uploaded_by=actor
    )
    SecurityEvent.record(
        SecurityEvent.EventType.SCHOOL_LOGO_CHANGED, actor=actor,
        detail={"school_id": school.pk, "logo_version_id": version.pk, "sha256": digest},
    )
    return version


@transaction.atomic
def remove_logo(school, *, actor):
    """Add a tombstone version; earlier versions are kept untouched."""
    if SchoolLogo.current_for(school) is None:
        raise ValidationError("There is no logo to remove.")
    version = SchoolLogo.objects.create(school=school, is_removal=True, uploaded_by=actor)
    SecurityEvent.record(
        SecurityEvent.EventType.SCHOOL_LOGO_REMOVED, actor=actor,
        detail={"school_id": school.pk, "logo_version_id": version.pk},
    )
    return version
