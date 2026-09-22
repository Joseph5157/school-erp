# School, AcademicYear, ClassGrade, Section, Guardian, Applicant,
# ApplicantGuardian, Student, and StudentGuardian are deliberately not
# registered here. The Django admin site's own is_staff gate would be a
# second, unguarded mutation path outside
# `core.authorization.administrator_required`, which is the single shared
# mechanism required by
# docs/adr/0004-phase-1-authorization-foundation.md.
