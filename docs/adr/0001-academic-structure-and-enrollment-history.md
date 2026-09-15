# 0001. Academic structure and enrollment history

## Status

Accepted

## Context

Phase 1 requires modeling Class/Grade, Section, Academic Year, and Academic Enrollment so that historical placement data is never overwritten (`docs/DOMAIN_MODEL.md` — "Academic Enrollment", "Historical data"; `docs/REQUIREMENTS.md` — "Academic Enrollment and assignment").

Phase 1 planning review identified an open modeling question left unresolved by the existing documentation: whether Section should carry a direct Academic Year relationship, and whether class/section offerings should be allowed to vary by Academic Year in Phase 1. `docs/REQUIREMENTS.md` previously implied that a Section requires "a valid Class/Grade and Academic Year relationship," which would make Section itself year-scoped. This ADR resolves that ambiguity and is the basis for the corresponding documentation correction described below.

## Decision

FROZEN:

- Class/Grade is a reusable, year-agnostic reference concept. It is not recreated per Academic Year.
- Section is also year-agnostic in Phase 1, and belongs to exactly one Class/Grade.
- Academic Year is **not** placed directly on Section in Phase 1.
- Academic Enrollment is the record that connects Student + Academic Year + Class/Grade + Section + enrollment status.
- The Section selected for an Academic Enrollment must belong to the Class/Grade selected for that same enrollment.
- Academic Year belongs to Academic Enrollment, not to Section.
- A Student may accumulate many historical Academic Enrollments over time.
- A Student may have at most one ACTIVE Academic Enrollment at any time.
- A Student's current placement is derived from their ACTIVE Academic Enrollment — it is never stored as a separately maintained mutable field.
- Creating a new placement must preserve the prior enrollment record rather than overwrite it.

CURRENT:

- If a future requirement emerges for class/section offerings to vary materially by Academic Year (for example, a Section only offered in certain years), that must be introduced through a later, explicit architecture/domain decision. It is not pre-built into Phase 1.

## Alternatives considered

- **Model Section as year-scoped** (Section directly related to Academic Year, effectively recreated each year). Rejected for Phase 1: adds structural complexity not justified by any stated Phase 1 requirement, and complicates referring to "the same section" across years. Left as the documented future path if a real requirement emerges (see the CURRENT decision above).
- **Model Class/Grade as year-scoped.** Rejected: nothing in the domain model requires grade levels themselves to change per year; only placement (enrollment) is year-specific.
- **Store "current placement" as a denormalized, in-place-updated field on Student.** Rejected: directly conflicts with the FROZEN historical-integrity principle in `docs/DOMAIN_MODEL.md` ("Avoid destructive updates that rewrite history").

## Consequences

- Section creation only requires a valid Class/Grade relationship, not an Academic Year relationship. `docs/REQUIREMENTS.md`'s Section management acceptance criteria are corrected to match (see documentation updates accompanying this ADR).
- Academic Enrollment becomes the single place where Year/Class/Section compatibility is validated (the enrollment's Section must belong to the enrollment's Class/Grade), keeping that responsibility in one module.
- Enforcing "at most one ACTIVE enrollment per Student" requires an explicit constraint or equivalent application-level check at implementation time; this ADR fixes the rule, not the mechanism.
- If class/section offerings ever need to vary by year, that requires a new ADR amending or superseding this one rather than an ad hoc schema change.

## Related requirements/domain decisions

- `docs/DOMAIN_MODEL.md` — "Academic Enrollment", "Class and Section"
- `docs/REQUIREMENTS.md` — "Section management", "Academic Enrollment and assignment"
