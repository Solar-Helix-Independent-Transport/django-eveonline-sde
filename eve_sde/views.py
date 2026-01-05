# Standard Library
import os

# Django
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

from .models import EveSDE, EveSDESection


@login_required
@permission_required("eve_sde.admin_access")
def index(request):

    sections = EveSDESection.objects.all()

    # render to template
    return render(request, 'esde/index.html', context={"sections": sections, "global": EveSDE.get_solo()})
