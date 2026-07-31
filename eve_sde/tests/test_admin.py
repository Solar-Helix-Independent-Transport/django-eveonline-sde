"""
Tests for the read-only admin configuration in admin.py: the NoEdit
permission guard shared by every registered admin, the display helpers that
walk FK chains (region/constellation/system), and the select_related
querysets that back them.
"""
# Django
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

# Django EVE SDE
from eve_sde import admin as esde_admin
from eve_sde.models import (
    BlueprintActivity,
    BlueprintActivityMaterial,
    BlueprintActivityProduct,
    Constellation,
    DogmaAttribute,
    DogmaAttributeCategory,
    DogmaEffect,
    EveSDE,
    EveSDESection,
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,
    ItemType,
    ItemTypeMaterials,
    Moon,
    NPCStation,
    Planet,
    Region,
    SolarSystem,
    SovereigntyUpgrade,
    Stargate,
    TypeDogma,
    TypeEffect,
)
from eve_sde.models.base import JSONModel


class NoEditPermissionTests(TestCase):

    def setUp(self):
        self.admin = esde_admin.RegionAdmin(Region, admin.site)
        self.request = RequestFactory().get("/")

    def test_no_add_change_or_delete_permission(self):
        self.assertFalse(self.admin.has_add_permission(self.request))
        self.assertFalse(self.admin.has_change_permission(self.request))
        self.assertFalse(self.admin.has_delete_permission(self.request))

    def test_no_change_or_delete_permission_with_an_object(self):
        region = Region.objects.create(id=1, name="The Forge")
        self.assertFalse(self.admin.has_change_permission(self.request, region))
        self.assertFalse(self.admin.has_delete_permission(self.request, region))


class EveryJSONModelIsRegisteredAndReadOnlyTests(TestCase):
    """
    Every concrete JSONModel subclass should have a read-only admin - this
    walks the real app registry rather than a hardcoded list, so it keeps
    itself honest as new SDE models are added.
    """

    def test_every_concrete_jsonmodel_is_registered_read_only(self):
        request = RequestFactory().get("/")
        missing = []
        not_read_only = []

        for model in apps.get_app_config("eve_sde").get_models():
            if not issubclass(model, JSONModel) or model._meta.abstract:
                continue

            model_admin = admin.site._registry.get(model)
            if model_admin is None:
                missing.append(model.__name__)
                continue

            if (
                model_admin.has_add_permission(request)
                or model_admin.has_change_permission(request)
                or model_admin.has_delete_permission(request)
            ):
                not_read_only.append(model.__name__)

        self.assertEqual(missing, [], f"Models missing an admin registration: {missing}")
        self.assertEqual(not_read_only, [], f"Models with a non-read-only admin: {not_read_only}")


class MapAdminDisplayHelperTests(TestCase):

    def setUp(self):
        self.request = RequestFactory().get("/")
        self.region = Region.objects.create(id=1, name="The Forge")
        self.constellation = Constellation.objects.create(id=2, name="Kimotoro", region=self.region)
        self.system = SolarSystem.objects.create(id=3, name="Jita", constellation=self.constellation)

    def test_solar_system_admin_display_helpers(self):
        admin_instance = esde_admin.SolarSystemAdmin(SolarSystem, admin.site)
        self.assertEqual(admin_instance.get_region(self.system), "The Forge")
        self.assertEqual(admin_instance.get_constellation(self.system), "Kimotoro")

    def test_solar_system_admin_queryset_still_resolves_the_right_object(self):
        admin_instance = esde_admin.SolarSystemAdmin(SolarSystem, admin.site)
        qs = admin_instance.get_queryset(self.request)
        self.assertEqual(qs.get(pk=self.system.pk).name, "Jita")

    def test_constellation_admin_display_helper(self):
        admin_instance = esde_admin.ConstellationAdmin(Constellation, admin.site)
        self.assertEqual(admin_instance.get_region(self.constellation), "The Forge")

    def test_constellation_admin_queryset_still_resolves_the_right_object(self):
        admin_instance = esde_admin.ConstellationAdmin(Constellation, admin.site)
        qs = admin_instance.get_queryset(self.request)
        self.assertEqual(qs.get(pk=self.constellation.pk).name, "Kimotoro")

    def test_moon_admin_display_helpers(self):
        planet = Planet.objects.create(id=4, name="Jita IV", solar_system=self.system)
        moon = Moon.objects.create(id=5, name="Jita IV - Moon 1", solar_system=self.system, planet=planet)

        admin_instance = esde_admin.MoonAdmin(Moon, admin.site)
        self.assertEqual(admin_instance.get_region(moon), "The Forge")
        self.assertEqual(admin_instance.get_constellation(moon), "Kimotoro")
        self.assertEqual(admin_instance.get_system(moon), "Jita")

        qs = admin_instance.get_queryset(self.request)
        self.assertEqual(qs.get(pk=moon.pk).name, "Jita IV - Moon 1")

    def test_planet_admin_display_helpers(self):
        planet = Planet.objects.create(id=6, name="Jita IV", solar_system=self.system)

        admin_instance = esde_admin.PlanetAdmin(Planet, admin.site)
        self.assertEqual(admin_instance.get_region(planet), "The Forge")
        self.assertEqual(admin_instance.get_constellation(planet), "Kimotoro")
        self.assertEqual(admin_instance.get_system(planet), "Jita")

        qs = admin_instance.get_queryset(self.request)
        self.assertEqual(qs.get(pk=planet.pk).name, "Jita IV")


class SovereigntyUpgradeAdminTests(TestCase):

    def test_name_returns_the_item_type_name(self):
        item_type = ItemType.objects.create(id=100, name="Cynosural Field Generator")
        upgrade = SovereigntyUpgrade.objects.create(item_type=item_type)

        admin_instance = esde_admin.SovereigntyUpgradeAdmin(SovereigntyUpgrade, admin.site)
        self.assertEqual(admin_instance._name(upgrade), "Cynosural Field Generator")


class FreelanceJobSchemaParameterInlineTests(TestCase):

    def test_no_add_permission(self):
        inline = esde_admin.FreelanceJobSchemaParameterInline(FreelanceJobSchema, admin.site)
        request = RequestFactory().get("/")
        self.assertFalse(inline.has_add_permission(request))


class NewAdminQuerysetTests(TestCase):
    """
    system checks validate list_display/search_fields against real model
    fields, but a typo'd relation path inside a custom get_queryset's
    select_related() is only ever caught by actually evaluating the
    queryset - these do that for every newly-registered admin that has one.
    """

    def test_item_type_materials_admin_queryset(self):
        item_type = ItemType.objects.create(id=1, name="Widget")
        material = ItemType.objects.create(id=2, name="Tritanium")
        row = ItemTypeMaterials.objects.create(item_type=item_type, material_item_type=material, quantity=10)

        admin_instance = esde_admin.ItemTypeMaterialsAdmin(ItemTypeMaterials, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=row.pk).item_type.name, "Widget")

    def test_dogma_attribute_admin_queryset(self):
        category = DogmaAttributeCategory.objects.create(id=1, name="Fitting")
        attribute = DogmaAttribute.objects.create(id=2, name="mass", attribute_category=category)

        admin_instance = esde_admin.DogmaAttributeAdmin(DogmaAttribute, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=attribute.pk).attribute_category.name, "Fitting")

    def test_type_dogma_admin_queryset(self):
        item_type = ItemType.objects.create(id=1, name="Widget")
        attribute = DogmaAttribute.objects.create(id=2, name="mass")
        row = TypeDogma.objects.create(item_type=item_type, dogma_attribute=attribute, value=1.0)

        admin_instance = esde_admin.TypeDogmaAdmin(TypeDogma, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=row.pk).dogma_attribute.name, "mass")

    def test_type_effect_admin_queryset(self):
        item_type = ItemType.objects.create(id=1, name="Widget")
        effect = DogmaEffect.objects.create(id=2, name="onlineEffect")
        row = TypeEffect.objects.create(item_type=item_type, dogma_effect=effect)

        admin_instance = esde_admin.TypeEffectAdmin(TypeEffect, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=row.pk).dogma_effect.name, "onlineEffect")

    def test_stargate_admin_queryset(self):
        src = SolarSystem.objects.create(id=1, name="Jita")
        dst = SolarSystem.objects.create(id=2, name="Perimeter")
        gate = Stargate.objects.create(id=1000, name="Jita >> Perimeter", solar_system=src, destination=dst)

        admin_instance = esde_admin.StargateAdmin(Stargate, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=gate.pk).destination.name, "Perimeter")

    def test_npc_station_admin_queryset(self):
        system = SolarSystem.objects.create(id=1, name="Jita")
        station = NPCStation.objects.create(id=1000, name="Jita IV - Station", solar_system=system)

        admin_instance = esde_admin.NPCStationAdmin(NPCStation, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=station.pk).solar_system.name, "Jita")

    def test_blueprint_activity_admin_queryset(self):
        blueprint_type = ItemType.objects.create(id=1, name="Widget Blueprint")
        activity = BlueprintActivity.objects.create(
            id="1:manufacturing", activity="manufacturing", blueprint_item_type=blueprint_type,
        )

        admin_instance = esde_admin.BlueprintActivityAdmin(BlueprintActivity, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=activity.pk).blueprint_item_type.name, "Widget Blueprint")

    def test_blueprint_activity_product_and_material_admin_querysets(self):
        blueprint_type = ItemType.objects.create(id=1, name="Widget Blueprint")
        activity = BlueprintActivity.objects.create(
            id="1:manufacturing", activity="manufacturing", blueprint_item_type=blueprint_type,
        )
        output_type = ItemType.objects.create(id=2, name="Widget")
        product = BlueprintActivityProduct.objects.create(
            blueprint_activity=activity, item_type=output_type, quantity=1,
        )
        material = BlueprintActivityMaterial.objects.create(
            blueprint_activity=activity, item_type=output_type, quantity=5,
        )

        product_admin = esde_admin.BlueprintActivityProductAdmin(BlueprintActivityProduct, admin.site)
        product_qs = product_admin.get_queryset(RequestFactory().get("/"))
        self.assertEqual(product_qs.get(pk=product.pk).blueprint_activity.blueprint_item_type.name, "Widget Blueprint")

        material_admin = esde_admin.BlueprintActivityMaterialAdmin(BlueprintActivityMaterial, admin.site)
        material_qs = material_admin.get_queryset(RequestFactory().get("/"))
        self.assertEqual(material_qs.get(pk=material.pk).item_type.name, "Widget")

    def test_freelance_job_schema_parameter_admin_queryset(self):
        schema = FreelanceJobSchema.objects.create(id="BoostShield", title="Boost Shield")
        parameter = FreelanceJobSchemaParameter.objects.create(
            id="BoostShield:target", schema=schema, key="target",
        )

        admin_instance = esde_admin.FreelanceJobSchemaParameterAdmin(FreelanceJobSchemaParameter, admin.site)
        qs = admin_instance.get_queryset(RequestFactory().get("/"))
        self.assertEqual(qs.get(pk=parameter.pk).schema.title, "Boost Shield")


class EveSDEAdminTests(TestCase):
    """
    EveSDE (global SDE state - build number/release date/last check) is a
    django-solo singleton: it gets its own read-only settings-style page
    rather than a changelist. Add/delete are already denied by
    SingletonModelAdmin itself; change is denied by our own override so the
    page renders read-only rather than as an editable settings form.
    """

    def setUp(self):
        self.admin = esde_admin.EveSDEAdmin(EveSDE, admin.site)
        self.request = RequestFactory().get("/")

    def test_no_add_change_or_delete_permission(self):
        self.assertFalse(self.admin.has_add_permission(self.request))
        self.assertFalse(self.admin.has_change_permission(self.request))
        self.assertFalse(self.admin.has_delete_permission(self.request))


class EveSDESectionAdminTests(TestCase):

    def setUp(self):
        self.admin = esde_admin.EveSDESectionAdmin(EveSDESection, admin.site)

    def test_row_health_is_green_when_lines_match_rows(self):
        section = EveSDESection.objects.create(
            sde_section="ItemCategory", build_number=1, last_update="2024-01-01T00:00:00Z",
            total_lines=10, total_rows=10,
        )
        self.assertIn("color: green", self.admin.row_health(section))
        self.assertIn("10/10", self.admin.row_health(section))

    def test_row_health_is_red_when_lines_and_rows_differ(self):
        section = EveSDESection.objects.create(
            sde_section="ItemCategory", build_number=1, last_update="2024-01-01T00:00:00Z",
            total_lines=10, total_rows=8,
        )
        self.assertIn("color: red", self.admin.row_health(section))
        self.assertIn("10/8", self.admin.row_health(section))


class AdminAppListBuildNumberTests(TestCase):
    """
    admin.site.get_app_list is patched so the eve_sde app's label in the
    admin index/app-index pages carries the currently-loaded SDE build
    number alongside the package version already in AppConfig.verbose_name.
    """

    def setUp(self):
        User = get_user_model()
        self.request = RequestFactory().get("/admin/")
        self.request.user = User.objects.create_superuser(
            username="admin", password="password", email="a@a.com",
        )

    def test_app_name_includes_the_current_build_number(self):
        state = EveSDE.get_solo()
        state.build_number = 3142455
        state.save()

        app_list = admin.site.get_app_list(self.request)
        eve_sde_app = next(app for app in app_list if app["app_label"] == "eve_sde")

        self.assertIn("SDE Build 3142455", eve_sde_app["name"])

    def test_app_name_falls_back_when_no_build_is_loaded_yet(self):
        app_list = admin.site.get_app_list(self.request, app_label="eve_sde")
        eve_sde_app = next(app for app in app_list if app["app_label"] == "eve_sde")

        self.assertIn("SDE Build not loaded", eve_sde_app["name"])

    def test_other_apps_are_left_untouched(self):
        app_list = admin.site.get_app_list(self.request)
        other_app = next(app for app in app_list if app["app_label"] == "authentication")

        self.assertNotIn("SDE Build", other_app["name"])
