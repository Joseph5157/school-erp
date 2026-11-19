"""Admin home Today tab data. Read-only; no HTTP here."""
import datetime

from core.models import School

DEFAULT_REGISTER_CUTOFF = datetime.time(10, 0)


def register_cutoff():
    """The school's register cut-off time, or 10:00 when no School row exists."""
    school = School.objects.first()
    return school.register_cutoff if school else DEFAULT_REGISTER_CUTOFF
