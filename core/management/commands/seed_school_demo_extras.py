"""Fill the School profile, logo, timetable and announcements of a seed_school_demo school.

Everything goes through the domain workflows: the School row is validated with
full_clean(), the logo is added through core.school_logo, timetable slots are
created with TimetableSlot.create (so the clash rule applies) from the existing
subject assignments, and notices are published through core.announcements.

Not re-runnable: it refuses to run when any Announcement or timetable Period
already exists.
"""

import math
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from core import announcements, school_logo
from core.management.commands.seed_demo import DEMO_ADMIN_USERNAME
from core.models import (
    AcademicYear,
    Announcement,
    AssessmentTeacherAssignment,
    School,
    TimetablePeriod,
    TimetableSlot,
)

PERIODS = 8
WEEKDAYS = range(5)  # Monday to Friday
CELLS = PERIODS * len(WEEKDAYS)

# Periods per week an offering would like, by subject; capped by what its teacher can take.
WANTED_PER_WEEK = {
    "Telugu": 3, "Hindi": 3, "English": 6, "Mathematics": 6, "Environmental Science": 4,
    "Science": 6, "Social Studies": 6, "Computer Science": 3,
}

SCHOOL_PROFILE = {
    "address": "Plot 24, Gandhi Nagar Main Road, Vijayawada, Andhra Pradesh 520010",
    "affiliation_number": "AP/CBSE/2410187",
    "principal_name": "Dr. Ramakrishna Murthy",
}

NOTICES = [
    (
        "Term 2 begins on Monday",
        "Dear parents, classes for Term 2 resume on Monday at the usual time. "
        "Students should come in the full school uniform and carry the Term 2 "
        "timetable pasted in their diary. Please make sure all textbooks and "
        "notebooks for the new term are ready.",
    ),
    (
        "Parent-Teacher Meeting on Saturday",
        "We invite you to meet your child's class teacher to discuss the Term 1 "
        "report card. The meeting is on Saturday from 9:30 am to 12:30 pm in the "
        "child's own classroom. Please carry the report card and the diary.",
    ),
    (
        "Annual Day celebrations",
        "Our Annual Day will be held in the school auditorium next month at 5:00 pm. "
        "Students who take part in dance, drama and music will practise after school "
        "from next week. Parents are warmly invited to attend the programme.",
    ),
    (
        "School closed for Dussehra",
        "The school will remain closed for the Dussehra holidays. Classes resume on "
        "the first working day after the holidays. Please make sure your child "
        "completes the holiday homework given by the class teacher.",
    ),
]


def make_logo_png():
    """A 400 x 400 green shield with an open book, drawn in memory."""
    size = 400
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    green, dark, white = (31, 122, 77), (18, 77, 48), (255, 255, 255)
    shield = [(60, 40), (340, 40), (340, 220), (200, 370), (60, 220)]
    draw.polygon(shield, fill=dark)
    inner = [(80, 58), (320, 58), (320, 212), (200, 342), (80, 212)]
    draw.polygon(inner, fill=green)
    # open book: two pages meeting at the spine, with text lines
    draw.polygon([(200, 150), (200, 290), (110, 270), (110, 130)], fill=white)
    draw.polygon([(200, 150), (200, 290), (290, 270), (290, 130)], fill=white)
    draw.line([(200, 150), (200, 290)], fill=dark, width=4)
    for offset in (160, 185, 210, 235):
        draw.line([(126, offset - 4), (186, offset + 6)], fill=green, width=3)
        draw.line([(214, offset + 6), (274, offset - 4)], fill=green, width=3)
    # star above the book
    cx, cy, r = 200, 105, 24
    points = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        angle = -1.5708 + i * 0.62832
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=white)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def colour_edges(edges):
    """Give every (section, teacher) edge a cell number so no vertex repeats a cell.

    A bipartite multigraph with maximum degree D can be edge-coloured with D
    colours (Konig), so every section and every teacher meets each cell at most
    once. Returns a list of cells parallel to `edges`.
    """
    at = {}  # (side, vertex) -> {cell: edge index}
    colour = [None] * len(edges)

    def free_cell(vertex):
        used = at.setdefault(vertex, {})
        return next(c for c in range(CELLS) if c not in used)

    for index, (section, teacher) in enumerate(edges):
        u, v = ("s", section), ("t", teacher)
        a, b = free_cell(u), free_cell(v)
        shared = next((c for c in range(CELLS) if c not in at[u] and c not in at[v]), None)
        if shared is not None:
            chosen = shared
        else:
            # a is free at u but used at v; b is free at v but used at u. Flip the a/b
            # path that starts at v so that a becomes free at v.
            path = []
            vertex, want = v, a
            while want in at[vertex]:
                e = at[vertex][want]
                path.append(e)
                s, t = edges[e]
                vertex = ("s", s) if vertex[0] == "t" else ("t", t)
                want = b if want == a else a
            for e in path:
                s, t = edges[e]
                del at[("s", s)][colour[e]]
                del at[("t", t)][colour[e]]
            for e in path:
                s, t = edges[e]
                colour[e] = b if colour[e] == a else a
                at[("s", s)][colour[e]] = e
                at[("t", t)][colour[e]] = e
            chosen = a
        colour[index] = chosen
        at[u][chosen] = index
        at[v][chosen] = index
    return colour


class Command(BaseCommand):
    help = "Add school profile details, a logo, a timetable and announcements to the demo school."

    def add_arguments(self, parser):
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("Set DJANGO_DEBUG=True or pass --allow-non-debug.")
        if Announcement.objects.exists() or TimetablePeriod.objects.exists():
            raise CommandError(
                "Announcements or timetable periods already exist; this only runs once."
            )
        self.admin = get_user_model().objects.get(username=DEMO_ADMIN_USERNAME)
        self.year = AcademicYear.objects.get()
        self.school = School.objects.get()

        with transaction.atomic():
            self._profile()
            self._logo()
            periods = self._periods()
            slots, possible = self._timetable(periods)
            notices = self._announcements()
        self.stdout.write(self.style.SUCCESS("Demo school extras created."))
        self.stdout.write(
            f"  School profile and logo set, {len(periods)} periods, {slots} timetable slots "
            f"({slots} of {possible} Section-period cells filled), {notices} announcements."
        )

    def _profile(self):
        for field, value in SCHOOL_PROFILE.items():
            setattr(self.school, field, value)
        self.school.full_clean()
        self.school.save()

    def _logo(self):
        school_logo.replace_logo(self.school, make_logo_png(), actor=self.admin)

    def _periods(self):
        periods = []
        for sequence in range(1, PERIODS + 1):
            period = TimetablePeriod(
                academic_year=self.year, sequence=sequence, label=f"Period {sequence}"
            )
            period.full_clean()
            period.save()
            periods.append(period)
        return periods

    def _timetable(self, periods):
        assignments = list(
            AssessmentTeacherAssignment.objects.filter(offering__academic_year=self.year)
            .select_related("offering__subject", "section")
            .order_by("section__class_grade__name", "section__name", "offering__display_order")
        )
        sections_of = {}
        for row in assignments:
            sections_of[row.teacher_id] = sections_of.get(row.teacher_id, 0) + 1
        # Periods per week for each assignment: what the subject asks for, but never
        # more than the teacher can give each of their Sections in a 40-cell week.
        edges, owners = [], []
        for row in assignments:
            weekly = min(WANTED_PER_WEEK[row.offering.subject.name],
                         CELLS // sections_of[row.teacher_id])
            for _ in range(weekly):
                edges.append((row.section_id, row.teacher_id))
                owners.append(row)
        cells = colour_edges(edges)

        created = 0
        for row, cell in zip(owners, cells):
            TimetableSlot.create(
                period=periods[cell // len(WEEKDAYS)], weekday=cell % len(WEEKDAYS),
                section=row.section, offering=row.offering, start_date=self.year.start_date,
            )
            created += 1
        possible = len({row.section_id for row in assignments}) * CELLS
        return created, possible

    def _announcements(self):
        for title, body in NOTICES:
            announcements.publish(
                title=title, body=body, audience=Announcement.Audience.ALL, actor=self.admin
            )
        return len(NOTICES)
