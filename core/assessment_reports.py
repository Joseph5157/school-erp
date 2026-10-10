"""Phase 4 reporting (ADR 0009, Gate 9).

Every report derives from the same canonical data: StudentResult rows of
FINALIZED assessments, with their current accepted values (after audited
corrections), the historical AcademicEnrollment each result references, and
the grading bands frozen on the assessment at finalization. Reports never
store a copy of marks. No rank, GPA, weighting, promotion or transcripts.
"""

from collections import OrderedDict

from core.models import Assessment, StudentResult, TermRemark


def finalized_results(queryset=None):
    queryset = StudentResult.objects.all() if queryset is None else queryset
    return queryset.filter(assessment__status=Assessment.Status.FINALIZED).select_related(
        "assessment__term__academic_year",
        "assessment__offering__subject",
        "assessment__offering__class_grade",
        "assessment__section__class_grade",
        "academic_enrollment__student",
        "academic_enrollment__section__class_grade",
        "academic_enrollment__academic_year",
    )


def result_sheet(assessment):
    """Report 1: one finalized assessment's results, by Student name."""
    if not assessment.is_finalized:
        return None
    return list(
        finalized_results(StudentResult.objects.filter(assessment=assessment)).order_by(
            "academic_enrollment__student__full_name", "pk"
        )
    )


def student_history(student):
    """Report 2: every finalized result of a Student, oldest first.

    Each row keeps the Section/Grade/year of the enrollment the result was
    recorded against, so history stays correct across transfers.
    """
    return list(
        finalized_results(
            StudentResult.objects.filter(academic_enrollment__student=student)
        ).order_by("assessment__assessment_date", "assessment__offering__subject__name", "pk")
    )


def subject_section_results(offering, section, term=None):
    """Report 3: finalized assessments x Students for one Subject and Section.

    Returns (assessments, rows) where each row is (student, [result or None
    per assessment]). Students are those with a result in any of the
    assessments, i.e. those on each assessment's historical roster.
    """
    assessments = Assessment.objects.filter(
        offering=offering, section=section, status=Assessment.Status.FINALIZED
    )
    if term is not None:
        assessments = assessments.filter(term=term)
    assessments = list(assessments.select_related("term").order_by("assessment_date", "name"))
    results = finalized_results(StudentResult.objects.filter(assessment__in=assessments))
    by_student = OrderedDict()
    for result in sorted(results, key=lambda r: (r.student.full_name, r.student.pk)):
        by_student.setdefault(result.student, {})[result.assessment_id] = result
    rows = [
        (student, [cells.get(a.pk) for a in assessments]) for student, cells in by_student.items()
    ]
    return assessments, rows


def term_report_card(student, term):
    """Report 4: a Student's finalized results for one Term, grouped by Subject.

    Returns a dict with the Term placement, subjects (subject -> results in
    date order) and the optional Term remark. Nothing is totalled or weighted.
    """
    results = finalized_results(
        StudentResult.objects.filter(academic_enrollment__student=student, assessment__term=term)
    ).order_by("assessment__offering__subject__name", "assessment__assessment_date", "pk")
    subjects = OrderedDict()
    for result in results:
        subjects.setdefault(result.assessment.offering.subject, []).append(result)
    return {
        "student": student,
        "term": term,
        "placement": term.enrollment_for(student),
        "subjects": subjects,
        "remark": TermRemark.objects.filter(term=term, student=student).first(),
    }
