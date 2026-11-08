"""Progress steps for multi-stage flows, drawn by templates/partials/_steps.html.

Each step is a dict with a label, a state (done, current, upcoming or stopped), the words a
screen reader hears for that state, and an optional short note shown under the label.
"""

DONE = "done"
CURRENT = "current"
UPCOMING = "upcoming"
STOPPED = "stopped"

_STATE_TEXT = {
    DONE: "done",
    CURRENT: "current step",
    UPCOMING: "not started",
    STOPPED: "stopped",
}


def _steps(labels, states, notes=None):
    notes = notes or {}
    return [
        {"label": label, "state": state, "state_text": _STATE_TEXT[state], "note": notes.get(index, "")}
        for index, (label, state) in enumerate(zip(labels, states, strict=True))
    ]


IMPORT_LABELS = ("Upload file", "Check preview", "Import records")


def import_steps(status=None):
    """Steps for a bulk import. ``status`` is an ImportBatch status; None means the upload page."""
    if status is None:
        return _steps(IMPORT_LABELS, (CURRENT, UPCOMING, UPCOMING))
    if status == "VALIDATED":
        return _steps(IMPORT_LABELS, (DONE, CURRENT, UPCOMING))
    if status == "REJECTED":
        return _steps(IMPORT_LABELS, (DONE, STOPPED, UPCOMING), {1: "Has errors"})
    if status == "COMMITTED":
        return _steps(IMPORT_LABELS, (DONE, DONE, DONE))
    stopped_note = {"DISCARDED": "Discarded", "EXPIRED": "Expired", "FAILED": "Failed"}.get(status, "Stopped")
    return _steps(IMPORT_LABELS, (DONE, DONE, STOPPED), {2: stopped_note})


ADMISSION_LABELS = ("Register applicant", "Decide admission", "Enrol as student")


def admission_steps(applicant=None, student=None):
    """Steps for one applicant. No applicant means the register page; a linked student means enrolled."""
    if applicant is None:
        return _steps(ADMISSION_LABELS, (CURRENT, UPCOMING, UPCOMING))
    if student is not None:
        return _steps(ADMISSION_LABELS, (DONE, DONE, DONE))
    status = applicant.admission_status
    if status == "ACCEPTED":
        return _steps(ADMISSION_LABELS, (DONE, DONE, CURRENT), {1: "Accepted"})
    if status == "REJECTED":
        return _steps(ADMISSION_LABELS, (DONE, STOPPED, UPCOMING), {1: "Rejected"})
    return _steps(ADMISSION_LABELS, (DONE, CURRENT, UPCOMING))
