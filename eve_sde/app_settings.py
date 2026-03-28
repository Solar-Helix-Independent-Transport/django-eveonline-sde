"""App Settings"""

# Django
from django.conf import settings

# # put your app settings here

# Chunks for the update tasks
# Reduce for memory constrained systems
ESDE_CHUNK_SIZE = getattr(settings, "ESDE_CHUNK_SIZE", 5000)
ESDE_BATCH_SIZE = getattr(settings, "ESDE_BATCH_SIZE", 500)

# Fix for Docker environments
# if persistent storage is used for `myauth` set to True for smaller update tasks.
ESDE_TASK_SPLIT = getattr(settings, "ESDE_TASK_SPLIT", False)
