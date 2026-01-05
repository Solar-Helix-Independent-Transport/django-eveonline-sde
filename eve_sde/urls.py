"""App URLs"""

# Django
from django.urls import path

from . import views

app_name: str = "esde"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.index, name="index"),
]
