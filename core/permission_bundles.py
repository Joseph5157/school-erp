"""Permission combinations that go together (Security Gate 4B).

A custom role is a login holding some permissions but not others. Since each class of personal
data needs its own view permission (core/data_access.py), holding a page's permission without the
data's leaves the page limited or a file refused. Each rule below says: a role that holds `held`
normally also needs `needed`, and what it loses without it. The `role_permission_gaps` command
reports roles with such gaps; docs/PERMISSIONS.md lists the recommended combinations.

A gap is information, not an error: a deliberately limited role (for example a teacher-aide who
may see students but never guardians) is meant to have one.
"""

# (permission held, permission it normally needs alongside, what is hidden or refused without it)
COMPANIONS = (
    ("core.view_student", "core.view_guardian",
     "student pages hide guardians, and searching students by guardian name, phone or email"),
    ("core.view_student", "core.view_attendanceentry",
     "student pages hide monthly attendance and the absent filter"),
    ("core.view_applicant", "core.view_guardian",
     "applicant pages hide guardians"),
    ("core.view_guardian", "core.view_student",
     "guardian pages hide linked students, and searching guardians by a student's name"),
    ("core.view_guardian", "core.view_applicant",
     "guardian pages hide linked applicants, and searching guardians by an applicant's name"),
    ("core.view_attendanceregister", "core.view_attendanceentry",
     "register pages hide each student's status and absence note"),
    ("core.view_assessment", "core.view_studentresult",
     "assessment pages hide scores, grades, pass/fail and who entered them"),
    ("core.view_termpublication", "core.view_studentresult",
     "publication pages hide marks and the remark"),
    ("core.publish_termpublication", "core.view_termpublication",
     "cannot open the publication pages that publishing happens on"),
    ("core.publish_termpublication", "core.view_studentresult",
     "publishes report cards without being able to see their marks"),
    ("core.view_importbatch", "core.run_import",
     "import pages hide the staged student rows (names, dates of birth, admission numbers)"),
    ("core.issue_document", "core.view_student",
     "cannot choose a student or open bonafide certificates"),
    ("core.issue_document", "core.view_studentresult",
     "cannot list or open report cards"),
    ("core.issue_document", "core.view_attendanceentry",
     "cannot issue or open attendance summaries"),
)


def gaps_for(permissions):
    """The rules a set of permission names breaks, as sorted (held, needed, effect) tuples."""
    held = set(permissions)
    return sorted(
        (rule_held, rule_needed, effect)
        for rule_held, rule_needed, effect in COMPANIONS
        if rule_held in held and rule_needed not in held
    )
