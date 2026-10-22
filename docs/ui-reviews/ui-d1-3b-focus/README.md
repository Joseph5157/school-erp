# Focus ring verification for .erp-table-scroll regions (commit f55a62f)

Rule under test: `.erp-table-scroll:focus-visible { outline: 3px solid var(--erp-focus-color); outline-offset: -3px; }`.

Method: disposable local PostgreSQL DB (dropped afterwards), synthetic data only (the same seed as ui-d1-3b), `collectstatic` run, fresh
`runserver --noreload` on 127.0.0.1:8765 (killed by PID afterwards), logged in as the non-superuser School Administrators `admin`.
Playwright Chromium; the region was reached with the keyboard Tab key (so `:focus-visible` genuinely applies; `matches(':focus-visible')` was true every time).
Screenshots are element screenshots of the containing `.erp-panel`. Computed values were read with getComputedStyle on the focused region.

"Before": pre-fix CSS (`git show f55a62f~1:static/css/erp.css`) was served to the page by a Playwright network route for the erp CSS request only. No tracked
or staticfiles file was modified. Only the applicant Guardians region at 1280 was captured as before.

## Results

| Set | Page | Width | Region | Computed outline | Region inside panel box | Ring visible | PNG |
|---|---|---|---|---|---|---|---|
| before | applicant-detail | 1280 | "Guardians" | auto 1px offset 0px rgb(16, 16, 16) | yes | N (1px dark sliver only) | before-applicant-detail-1280-region0.png |
| after | applicant-detail | 1280 | "Guardians" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-applicant-detail-1280-region0.png |
| after | applicant-detail | 390 | "Guardians" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-applicant-detail-390-region0.png |
| after | teacher-detail | 1280 | "Recent security events" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-teacher-detail-1280-region0.png |
| after | teacher-detail | 390 | "Recent security events" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-teacher-detail-390-region0.png |
| after | applicants-list | 1280 | "Applicants" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-applicants-list-1280-region0.png |
| after | applicants-list | 390 | "Applicants" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-applicants-list-390-region0.png |
| after | guardians-list | 1280 | "Guardians" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-guardians-list-1280-region0.png |
| after | guardians-list | 390 | "Guardians" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-guardians-list-390-region0.png |
| after | teachers-list | 1280 | "Teachers" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-teachers-list-1280-region0.png |
| after | teachers-list | 390 | "Teachers" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-teachers-list-390-region0.png |
| after | students-list | 1280 | "Students" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-students-list-1280-region0.png |
| after | students-list | 390 | "Students" | solid 3px offset -3px rgb(11, 110, 79) | yes | Y | after-students-list-390-region0.png |

Colour rgb(11, 110, 79) is the focus colour token. Page-level horizontal overflow (scrollWidth > innerWidth) was false for every page/width.

## Pixel check

For each after-shot the pixels at the region's left edge (offsets 0-2px) were sampled from the screenshot: all were exactly the focus colour on every page/width.
The same check on the top edge matched the focus colour at offsets 1-2px everywhere; at offset 0 on three screenshots (applicants list 1280/390, teachers list 1280)
the sample was the panel border colour. The region top there sits on a fractional pixel (e.g. y=293.83), so this is sampling rounding against the panel's 1px border, and the
screenshots show a continuous ring. Visual inspection of all 12 after-shots and the before-shot confirms it.

## Before vs after

Before: the browser default `auto` outline (1px, offset 0, near-black) is drawn outside the region's box, where `contain: paint` and the panel's `overflow: hidden` clip it;
only a thin 1px dark line on the table-header side remains and the left/right/bottom edges are essentially undrawn. After: a continuous 3px green ring inside all four edges.

## Defects / notes

- No defects found: ring fully visible, not clipped, offset negative, region inside its panel at every tested page and width.
- Only one scroll region per page exists on every tested page, so just region 0 was exercised.
- At 390 the lists scroll horizontally inside the region (scrollWidth > clientWidth); the ring stays fixed to the region box, it does not scroll with the content.
- The ring overlays the first 3px of table content/borders at the region edge (inherent to a negative offset); no text is covered in the captures.
