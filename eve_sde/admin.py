"""Admin models"""

# Third Party
from solo.admin import SingletonModelAdmin

# Django
from django.contrib import admin
from django.utils.html import format_html

# Django EVE SDE
from eve_sde import models


class NoEdit(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.EveSDE)
class EveSDEAdmin(SingletonModelAdmin):
    """
    Global SDE state (current build/release date/last check) - a single,
    read-only settings-style page rather than a changelist.
    """

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(models.EveSDESection)
class EveSDESectionAdmin(NoEdit):
    """Per-model import status - one row per SDE model, updated by the import tasks."""

    list_display = ('sde_section', 'build_number', 'last_update', 'row_health')
    search_fields = ('sde_section', )
    ordering = ('sde_section', )

    @admin.display(description="Rows")
    def row_health(self, obj):
        color = "green" if obj.total_lines == obj.total_rows else "red"
        return format_html('<span style="color: {}">{}/{}</span>', color, obj.total_lines, obj.total_rows)


# Show the currently-loaded SDE build number next to the app's name (which
# already carries the package version via AppConfig.verbose_name) on the
# admin index/app-index pages - this is the only supported hook for a
# per-app dynamic label without requiring the host project to swap in a
# custom AdminSite.
_get_app_list = admin.site.get_app_list


def _get_app_list_with_sde_build(request, app_label=None):
    app_list = _get_app_list(request, app_label)
    for app in app_list:
        if app["app_label"] == "eve_sde":
            build_number = models.EveSDE.get_solo().build_number
            app["name"] = f"{app['name']} (SDE Build {build_number or 'not loaded'})"
    return app_list


admin.site.get_app_list = _get_app_list_with_sde_build


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


@admin.register(models.Stargate)
class StargateAdmin(NoEdit):
    list_display = ('name', 'solar_system', 'destination')
    search_fields = ('name', 'solar_system__name', 'destination__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('solar_system', 'destination')


@admin.register(models.NPCStation)
class NPCStationAdmin(NoEdit):
    list_display = ('name', 'solar_system')
    search_fields = ('name', 'solar_system__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('solar_system')


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


@admin.register(models.ItemMarketGroup)
class ItemMarketGroupAdmin(NoEdit):
    list_display = ('name', 'parent_group')
    search_fields = ('name', )


@admin.register(models.ItemTypeMaterials)
class ItemTypeMaterialsAdmin(NoEdit):
    list_display = ('item_type', 'material_item_type', 'quantity', 'quantity_min', 'quantity_max')
    search_fields = ('item_type__name', 'material_item_type__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item_type', 'material_item_type')


@admin.register(models.DogmaAttributeCategory)
class DogmaAttributeCategoryAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


@admin.register(models.DogmaUnit)
class DogmaUnitAdmin(NoEdit):
    list_display = ('name', 'display_name')
    search_fields = ('name', )


@admin.register(models.DogmaAttribute)
class DogmaAttributeAdmin(NoEdit):
    list_display = ('name', 'display_name', 'attribute_category')
    search_fields = ('name', )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('attribute_category')


@admin.register(models.DogmaEffect)
class DogmaEffectAdmin(NoEdit):
    list_display = ('name', 'display_name')
    search_fields = ('name', )


@admin.register(models.TypeDogma)
class TypeDogmaAdmin(NoEdit):
    list_display = ('item_type', 'dogma_attribute', 'value')
    search_fields = ('item_type__name', 'dogma_attribute__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item_type', 'dogma_attribute')


@admin.register(models.TypeEffect)
class TypeEffectAdmin(NoEdit):
    list_display = ('item_type', 'dogma_effect', 'is_default')
    search_fields = ('item_type__name', 'dogma_effect__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item_type', 'dogma_effect')


@admin.register(models.Archetype)
class ArchetypeAdmin(NoEdit):
    list_display = ('name', )
    search_fields = ('name', )


@admin.register(models.BlueprintActivity)
class BlueprintActivityAdmin(NoEdit):
    list_display = ('blueprint_item_type', 'activity', 'time', 'max_production_limit')
    search_fields = ('blueprint_item_type__name', )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('blueprint_item_type')


@admin.register(models.BlueprintActivityProduct)
class BlueprintActivityProductAdmin(NoEdit):
    list_display = ('blueprint_activity', 'item_type', 'quantity', 'probability')
    search_fields = ('blueprint_activity__blueprint_item_type__name', 'item_type__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'blueprint_activity__blueprint_item_type', 'item_type'
        )


@admin.register(models.BlueprintActivityMaterial)
class BlueprintActivityMaterialAdmin(NoEdit):
    list_display = ('blueprint_activity', 'item_type', 'quantity')
    search_fields = ('blueprint_activity__blueprint_item_type__name', 'item_type__name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'blueprint_activity__blueprint_item_type', 'item_type'
        )


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


@admin.register(models.FreelanceJobSchemaParameter)
class FreelanceJobSchemaParameterAdmin(NoEdit):
    list_display = ('schema', 'key', 'kind', 'title')
    search_fields = ('schema__title', 'key')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('schema')


@admin.register(models.SovereigntyUpgrade)
class SovereigntyUpgradeAdmin(NoEdit):
    """
    SovereigntyUpgrade admin model
    """

    list_display = ('_name',)
    search_fields = ('item_type__name',)

    def _name(self, obj):
        """
        Return the item type name

        :param obj:
        :type obj:
        :return:
        :rtype:
        """

        return obj.item_type.name
