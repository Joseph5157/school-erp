from django import forms
from django.core.exceptions import ValidationError

from core.models import AcademicYear, ClassGrade, School, Section


class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ["name"]


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class ClassGradeForm(forms.ModelForm):
    class Meta:
        model = ClassGrade
        fields = ["name"]


class SectionForm(forms.ModelForm):
    """Create a Section within a specific Class/Grade context.

    `class_grade` is supplied by the view from the URL rather than taken from
    the request, so a Section cannot be created against an arbitrary or
    missing Class/Grade. Because `class_grade` is not a form field, Django's
    automatic unique validation cannot see it, so the per-Class/Grade name
    uniqueness rule (docs/adr/0001) is checked explicitly here.
    """

    class Meta:
        model = Section
        fields = ["name"]

    def __init__(self, *args, class_grade=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_grade = class_grade
        if class_grade is not None:
            self.instance.class_grade = class_grade

    def clean_name(self):
        name = self.cleaned_data["name"]
        class_grade = self.class_grade or self.instance.class_grade
        duplicates = Section.objects.filter(class_grade=class_grade, name=name)
        if self.instance.pk is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError("A Section with this name already exists for this Class/Grade.")
        return name
