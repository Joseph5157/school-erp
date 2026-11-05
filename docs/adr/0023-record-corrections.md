# ADR 0023: Correcting Applicant and Student details

Status: accepted, 2026-11-05.

## Context
A mistake in a child's name, date of birth, phone or email could not be fixed after registration. These details identify a child and appear on official documents, so a correction must leave a trace.

## Decision
- **Editable fields:** full name, date of birth, email and phone. Status and admission number keep their own workflows.
- **Applicant:** correctable only until a Student exists. After that it stays as recorded at application.
- **Student:** correctable at any time, including when inactive. The source Applicant is not changed.
- **History:** every correction needs a reason and writes one `RecordCorrection` row with who, when, and the old and new values. Database triggers refuse UPDATE and DELETE.
- **Permissions:** the existing `change_applicant` and `change_student`.

## Consequences
- `IssuedDocument.payload` is a frozen copy, so issued documents and their reprints keep the old details.
- Finalized results and on-screen report cards store no student name, so they show the corrected name immediately. New documents use it too.
- `progress_to_student` does not lock the Applicant. A correction saved at the same moment as progression could leave the Student with the old values. Staff can correct the Student afterwards.
