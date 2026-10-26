from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.models import Applicant, Student


class EnglishStudentNameTests(SimpleTestCase):
    def check(self, model, name):
        field = model._meta.get_field("full_name")
        field.run_validators(name)

    def test_english_names_pass(self):
        for model in (Applicant, Student):
            for name in ("Anusha Rao", "D'Souza-Smith Jr.", "K. Lakshmi Prasad"):
                self.check(model, name)

    def test_telugu_names_rejected(self):
        for model in (Applicant, Student):
            for name in ("అనూష రావు", "అనూష రావు / Anusha Rao"):
                with self.assertRaises(ValidationError):
                    self.check(model, name)
