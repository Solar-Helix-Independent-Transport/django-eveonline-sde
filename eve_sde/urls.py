"""App URLs"""

# Django
from django.urls import path

# Django EVE SDE
from eve_sde import views

app_name: str = "esde"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.index, name="index"),
]
