from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Authentication identity only. No school-domain fields belong here."""
