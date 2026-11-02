# 0022. Display-only subject averages in analytics

## Status

Accepted (2026-11-02, school charts PR 2). Records decisions D1 and D2 of
`docs/superpowers/specs/2026-11-02-school-charts-design.md`.

Narrows ADR 0009 ("separate assessments remain separate; no weighted term percentage is
invented") with one analytics exception. It changes no other frozen decision.

## Context

The Overview marks cards, the "Students needing attention" list and the teacher's student page
draw charts per subject (a radar, bullet bars, a term comparison). Each needs one number per
subject per term. ADR 0009 and `docs/UI_DESIGN_RULES.md` forbid inventing a term percentage and
forbid averages on teacher and guardian result views. The Overview's `marks_snapshot` already
counts test percentages into score bands for admin staff; it does not average them. Per-subject
averages are new.

## Decision

D1. The subject number is the plain average of each FINALIZED test's percentage (score as a
percentage of that test's own maximum) in the term, using MARKED results only. ABSENT is left
out and never counted as zero; a score of 0 is a real zero. Subjects group by the name captured
at finalization, so a renamed subject behaves as the report card does.

- It is display-only. It is calculated when the page loads, never stored, never copied into a
  model, and needs no migration.
- It never appears on official report cards, term publications or any guardian view, and never in
  the Guardian Portal. The printed progress summary (D2) is the only printed place.
- A section average is shown only when at least 5 distinct students in that section have marks
  in the subject, so a small section cannot reveal one student's marks.

D2. `docs/UI_DESIGN_RULES.md` gets one exception to "No totals, weighting, averages or ranks on
teacher or guardian result views": the charts on the teacher's student page
(`my_student_detail`), using only results that teacher may already see. The gradebook, marks
entry and guardian views keep the rule, so `my_student_detail` is the only teacher result view
allowed to show these averages, apart from the printed progress summary below. Totals, weighting
and ranks stay forbidden on teacher and guardian views, including those charts.

The printed progress summary is the other allowed place: admins with results permission and
teachers who pass `can_view_report_card_as_teacher` may see it, and it shows published values
only. It is never part of the Guardian Portal.

## Consequences

- Calculations live in `core/marks_analytics.py` and are shared by the Overview and the student
  page, so there is one definition of "subject score".
- A reviewer can reject any new averaging outside these places by pointing at this ADR.
- If the school later wants weighted terms, that is a new ADR; this one does not approve it.
