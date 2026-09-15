from django import forms

from core.models import AcademicYear, School


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
