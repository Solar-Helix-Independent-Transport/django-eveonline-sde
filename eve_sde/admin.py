"""Admin models"""

# Django
from django.contrib import admin

from . import models


class NoEdit(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.SolarSystem)
class SolarSystemAdmin(NoEdit):
    list_display = ['name', 'get_region', 'get_constellation']
    search_fields = [
        'name',
        'constellation__region__name',
        'constellation__name'
    ]

    def get_region(self, obj):
        return obj.constellation.region.name

    def get_constellation(self, obj):
        return obj.constellation.name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('constellation', 'constellation__region')


@admin.register(models.Region)
class RegionAdmin(NoEdit):
    list_display = ['name']
    search_fields = ['name']


@admin.register(models.Constellation)
class ConstellationAdmin(NoEdit):
    list_display = ['name', 'get_region']
    search_fields = ['name', 'region__name']

    def get_region(self, obj):
        return obj.region.name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('region')


@admin.register(models.Moon)
class MoonAdmin(NoEdit):
    list_display = ['name', 'get_region', 'get_constellation', 'get_system']
    search_fields = [
        'name',
        'solar_system__constellation__region__name',
        'solar_system__constellation__name',
        'solar_system__name'
    ]

    def get_region(self, obj):
        return obj.solar_system.constellation.region.name

    def get_constellation(self, obj):
        return obj.solar_system.constellation.name

    def get_system(self, obj):
        return obj.solar_system.name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'solar_system__constellation__region',
            'solar_system__constellation',
            'solar_system'
        )


@admin.register(models.Planet)
class PlanetAdmin(NoEdit):
    list_display = ['name', 'get_region', 'get_constellation', 'get_system']
    search_fields = [
        'name',
        'solar_system__constellation__region__name',
        'solar_system__constellation__name',
        'solar_system__name'
    ]

    def get_region(self, obj):
        return obj.solar_system.constellation.region.name

    def get_constellation(self, obj):
        return obj.solar_system.constellation.name

    def get_system(self, obj):
        return obj.solar_system.name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'solar_system__constellation__region',
            'solar_system__constellation',
            'solar_system'
        )


@admin.register(models.ItemType)
class ItemTypeAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


@admin.register(models.ItemGroup)
class ItemGroupAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


@admin.register(models.ItemCategory)
class ItemCategoryAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


@admin.register(models.Archetype)
class ArchetypeAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


class FreelanceJobSchemaParameterInline(admin.TabularInline):
    model = models.FreelanceJobSchemaParameter
    fields = ('key', 'kind', 'matcher_type', 'accepted_value_types', 'optional', 'title')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(models.FreelanceJobSchema)
class FreelanceJobSchemaAdmin(NoEdit):
    list_display = ('title', 'id', 'content_tags')
    search_fields = ('title', 'id')
    inlines = (FreelanceJobSchemaParameterInline, )
