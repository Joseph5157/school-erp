"""Which permission each class of personal data needs (Security Gate 4B).

A route's own permission is the door to a page. Some pages also embed another class of data:
a student page lists guardians, a guardian page lists children, an assessment page lists marks.
Embedded data needs its own class's view permission, held by the signed-in login directly or
through a group (`user.has_perm` honours both). A view without that permission leaves the section
out of the page context and out of its queries (search and filter clauses are dropped, so they
cannot reveal what the page hides); it does not turn the whole page into a 403 unless the page
exists only to show that data.

Documents follow the same rule: `DOCUMENT_PERMISSIONS` says what each issued document type
contains. docs/PERMISSIONS.md describes the model, the deliberate bundles and the recommended
roles. `core/tests/route_inventory.py` reads these constants, so a view that checks one of them
shows it in the pinned route inventory.
"""

GUARDIAN = "core.view_guardian"
STUDENT = "core.view_student"
APPLICANT = "core.view_applicant"
ATTENDANCE_ENTRY = "core.view_attendanceentry"
STUDENT_RESULT = "core.view_studentresult"
RUN_IMPORT = "core.run_import"

# What opening an issued document needs, by its type (IssuedDocument.DocumentType).
DOCUMENT_PERMISSIONS = {
    "BONAFIDE": (STUDENT,),
    "REPORT_CARD": (STUDENT_RESULT,),
    "ATTENDANCE_SUMMARY": (ATTENDANCE_ENTRY,),
}


def document_permissions(document_type):
    """The permissions an issued document of this type needs, or None for an unknown type."""
    return DOCUMENT_PERMISSIONS.get(document_type)


def can_open_document(user, document):
    """May this login open the issued document? Unknown types are never openable."""
    needed = document_permissions(document.document_type)
    return needed is not None and user.has_perms(needed)


def openable_document_types(user):
    """The issued-document types this login may open, for filtering a list in the query."""
    return [
        document_type
        for document_type, needed in DOCUMENT_PERMISSIONS.items()
        if user.has_perms(needed)
    ]
