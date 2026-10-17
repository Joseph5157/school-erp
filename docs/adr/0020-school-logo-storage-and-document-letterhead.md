# 0020. School logo storage and document letterhead

## Status

Proposed (2026-10-17, Phase 7 follow-up). Not yet accepted or frozen.

Extends ADR 0016 (issued documents are immutable; reprints render from the
stored payload) by adding a logo reference to the letterhead. Changes no
frozen decision.

## Context

The app has no media storage. `School` holds only text (name, address,
affiliation number, principal). Issued documents carry a text letterhead copied
into `IssuedDocument.payload` at issue time. The navigation brand is the fixed
text "School ERP". The Phase 7 plan lists a letterhead logo as still open
because the app has no image handling or persistent media storage.

Hosting facts that shape the decision (Railway staging, auto-deploys on every
merge):

- The container filesystem is discarded on each deploy, so an uploaded file
  on local disk would disappear.
- A Railway volume would bind the web service to one instance, sit outside the
  database backups, and not be visible to the separate cron service.
- A bucket would add credentials, a storage library, a public-or-private URL
  decision, and PDF rendering that fetches remote URLs.

The logo is small, rarely changed, and needed by both the web pages and the
PDF renderer. ADR 0016 requires a reprint to match the original, so a document
must be able to show the exact logo it was issued with even after the logo is
replaced or removed.

## Decision

- **D1 Logo bytes live in Postgres.** A new model `SchoolLogo` holds one row
  per logo version: the normalized image bytes, its SHA-256, the uploader and
  the upload time. No file, `MEDIA_ROOT`, `MEDIA_URL` or external storage is
  introduced. Every row has a protected foreign key (`on_delete=PROTECT`) to
  `School`, even though `School` is currently a singleton, so logo history
  explicitly belongs to the school.
- **D2 Versions are immutable.** Rows are append-only. Database triggers
  refuse UPDATE and DELETE, as for `IssuedDocument`. Replacing a logo adds a
  version.
- **D3 Removal is a tombstone.** "Remove" adds a version flagged as a removal
  with no image and no SHA-256. Nothing is updated or deleted, so earlier
  versions stay available to the documents that reference them. A database
  check constraint enforces the two shapes: an active version has the image
  and the SHA-256 present; a tombstone has neither.
- **D4 Current logo.** "Latest" is deterministic: the newest row of the
  school ordered by `uploaded_at`, then `pk`. The logo shown in the UI is that
  version, and only if it is not a tombstone. If it is a tombstone, or no
  version exists, the UI shows the text brand.
- **D5 Accepted uploads.** PNG or JPEG only. SVG and every other type are
  refused. The format is determined by decoding the image, not by file
  extension or the browser's content type.
- **D6 Limits.** At most 512 KB uploaded. At most 2000 x 2000 pixels, with a
  decompression-bomb guard on the pixel count. An image over either limit is
  refused, not shrunk to fit. A file that cannot be decoded is refused.
- **D7 Normalization.** An accepted image is decoded, stripped of metadata
  (EXIF and any other embedded data), downscaled so the width is at most 600
  pixels while keeping proportions, and re-encoded as PNG. Only the normalized
  PNG is stored. The original upload is not kept.
- **D8 Permissions.** Upload, replace and remove require the same permission
  as editing the School (`core.change_school`) through
  `administrator_required`. Teachers and guardians cannot change the logo.
  Each change writes a security event with the actor and the new version.
- **D9 Serving.** A login-required view returns the current logo as
  `image/png`. No public media URL exists. Any signed-in user may fetch it.
- **D10 Documents reference a version.** From Gate 2, the letterhead stored in
  a new `IssuedDocument.payload` includes `logo_version_id` when a current logo
  exists. A reprint renders the image from that stored version, so it matches
  the original even if the logo has since been replaced or removed. The PDF
  engine embeds the image as a `data:` URI; it fetches no file and no URL.
- **D11 Older documents.** A payload with no `logo_version_id` is rendered
  text-only, exactly as issued. Existing documents are not backfilled.
- **D12 Missing reference is an error.** If a payload names a `logo_version_id`
  and that version is missing or has no image, rendering fails with an
  integrity error. It does not fall back to text, because that would silently
  change an issued document. Triggers (D2) make this condition unreachable
  through the application.
- **D13 No logo is normal.** With no current logo, new documents are issued
  text-only and carry no `logo_version_id`; the header shows the text brand.
  No placeholder image is drawn.
- **D14 Bucket deferred.** Object storage is not adopted now. Revisit it, with
  its own ADR, if larger media such as student photos are required.
- **D15 Delivery gates.**
  - Gate 1: the `SchoolLogo` model and triggers, upload, replace and remove on
    the School page, validation and normalization, the serving view, the
    header display with fallback, and the security events. Documents are
    untouched.
  - Gate 2: the immutable letterhead integration (D10 to D12) in
    `letterhead()` and `_letterhead.html`, covering the bonafide certificate,
    attendance summary, report-card PDF and the future Transfer Certificate.
  Gate 2 starts only after Gate 1 is merged.

## Alternatives rejected

- Local disk or `FileSystemStorage`: lost on every deploy.
- Railway volume: single-instance, outside database backups, invisible to the
  cron service, extra operations for one small image.
- Bucket storage now: credentials, a new dependency, and remote fetches during
  PDF rendering, for one rarely changed image.
- A single mutable logo column on `School`: replacing it would change what a
  reprint shows, contradicting ADR 0016.
- Embedding the logo bytes in each document payload: repeats about the same
  image in every issued document. A reference to one immutable version stores
  it once.
- SVG: can carry script and external references that the PDF renderer would
  follow.
- Falling back to text when a referenced version is missing: hides a broken
  record and alters an issued document.

## Consequences

- Gate 1 is additive: one new table and its triggers, a security event type
  (possibly a choices migration), and an explicit Pillow pin in
  `requirements.txt` (already installed with WeasyPrint). `School` is not
  changed and there is no data migration.
- Gate 2 changes the letterhead shape in new payloads only. Existing payloads
  and published report cards are unchanged and keep rendering text-only.
- Logo history grows with every replacement, at most about 600 px wide per
  version. This is accepted; there is no purge, consistent with append-only
  records elsewhere.
- Backups, restores and the staging database carry the logo with no extra
  steps.
- The Django admin stays unused for this model, consistent with ADR 0004.

## Related

- `docs/adr/0016-phase-7-issued-documents-and-pdf-generation.md`
- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`
