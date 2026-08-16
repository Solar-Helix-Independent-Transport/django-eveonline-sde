"""
Tests for the standalone lookup models in misc.py:
- AccountingEntryType: journalMessage/description are optional per-row in the
    SDE source, so a row lacking them should still load cleanly.
- NotificationType: displayName is missing on a handful of rows in the SDE
    source, so name has to tolerate that (unlike TypeBase's non-null name).
- CorporationRole/CorporationRoleGroup/CorporationRoleGroupMembership: the
    membership model flattens corporationRoles.jsonl's roleGroupIDs list
    into one row per (role, role group) pair - same flatten-and-wipe pattern
    as ItemTypeMaterials/TypeDogma/TypeEffect in types.py. roleGroupIDs is
    itself missing on one role in the SDE source, so that role should load
    with zero membership rows rather than failing.
- MetenoxMoonDrill: keyed straight off ItemType's pk via a OneToOneField,
    same shape as SovereigntyUpgrade in sovereignty.py.
- SkillPlan/SkillPlanMilestone/SkillPlanSkillRequirement: milestones and
    skillRequirements are two independent lists on the same skillPlans.jsonl
    row, each flattened into its own join model, same flatten-and-wipe
    pattern as CorporationRoleGroupMembership.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.misc import (
    AccountingEntryType,
    CorporationRole,
    CorporationRoleGroup,
    CorporationRoleGroupMembership,
    MetenoxMoonDrill,
    NotificationType,
    SkillPlan,
    SkillPlanMilestone,
    SkillPlanSkillRequirement,
)
from eve_sde.models.types import ItemType


class AccountingEntryTypeLoadTests(TestCase):

    def test_loads_internal_name_and_lang_fields(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "internalName": "player_trading",
            "name": {"en": "Player Trading", "de": "Spieler-Handel"},
            "journalMessage": {"en": "Direct trade between {name1} and {name2}"},
            "description": {"en": "Player to player trading"},
        }
        with open(os.path.join(tmpdir, "accountingEntryTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        AccountingEntryType.load_from_sde(tmpdir)

        entry = AccountingEntryType.objects.get(pk=1)
        self.assertEqual(entry.internal_name, "player_trading")
        self.assertEqual(entry.name, "Player Trading")
        self.assertEqual(entry.name_de, "Spieler-Handel")
        self.assertEqual(entry.journal_message, "Direct trade between {name1} and {name2}")
        self.assertEqual(entry.description, "Player to player trading")

    def test_journal_message_and_description_are_optional(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {"_key": 0, "internalName": "undefined", "name": {"en": "Undefined"}}
        with open(os.path.join(tmpdir, "accountingEntryTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        AccountingEntryType.load_from_sde(tmpdir)

        entry = AccountingEntryType.objects.get(pk=0)
        self.assertIsNone(entry.journal_message)
        self.assertIsNone(entry.description)


class NotificationTypeLoadTests(TestCase):

    def test_loads_internal_name_and_lang_name(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "internalName": "CharMedalMsg",
            "displayName": {"en": "Medal Awarded", "de": "Orden erhalten"},
        }
        with open(os.path.join(tmpdir, "notificationTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        NotificationType.load_from_sde(tmpdir)

        entry = NotificationType.objects.get(pk=1)
        self.assertEqual(entry.internal_name, "CharMedalMsg")
        self.assertEqual(entry.name, "Medal Awarded")
        self.assertEqual(entry.name_de, "Orden erhalten")

    def test_missing_display_name_loads_with_null_name(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {"_key": 297, "internalName": "FreelanceProjectACLDeleted"}
        with open(os.path.join(tmpdir, "notificationTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        NotificationType.load_from_sde(tmpdir)

        entry = NotificationType.objects.get(pk=297)
        self.assertIsNone(entry.name)
        self.assertEqual(entry.internal_name, "FreelanceProjectACLDeleted")

    def test_str_includes_name_and_id(self):
        notification_type = NotificationType(id=3, name="Medal Awarded")
        self.assertEqual(str(notification_type), "Medal Awarded (3)")


class CorporationRoleGroupLoadTests(TestCase):

    def test_loads_all_fields(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "appliesTo": "roles",
            "appliesToGrantable": "grantableRoles",
            "isDivisional": False,
            "isLocational": True,
            "name": {"en": "General", "de": "Allgemein"},
        }
        with open(os.path.join(tmpdir, "corporationRoleGroups.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        CorporationRoleGroup.load_from_sde(tmpdir)

        group = CorporationRoleGroup.objects.get(pk=1)
        self.assertEqual(group.name, "General")
        self.assertEqual(group.name_de, "Allgemein")
        self.assertEqual(group.applies_to, "roles")
        self.assertEqual(group.applies_to_grantable, "grantableRoles")
        self.assertFalse(group.is_divisional)
        self.assertTrue(group.is_locational)


class CorporationRoleLoadTests(TestCase):

    def test_loads_name_description_and_short_name(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 0,
            "name": {"en": "Director", "de": "Direktor"},
            "description": {"en": "Can do anything like a CEO."},
            "shortName": "roleDirector",
            "roleGroupIDs": [1],
        }
        with open(os.path.join(tmpdir, "corporationRoles.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        CorporationRole.load_from_sde(tmpdir)

        role = CorporationRole.objects.get(pk=0)
        self.assertEqual(role.name, "Director")
        self.assertEqual(role.name_de, "Direktor")
        self.assertEqual(role.description, "Can do anything like a CEO.")
        self.assertEqual(role.short_name, "roleDirector")


class CorporationRoleGroupMembershipLoadTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        CorporationRoleGroup.objects.create(id=1, name="General")
        CorporationRoleGroup.objects.create(id=4, name="Hangar Access (Headquarters)")

    def _write_roles(self, rows):
        with open(os.path.join(self.tmpdir, "corporationRoles.jsonl"), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def test_flattens_one_row_per_role_group_id(self):
        CorporationRole.objects.create(id=1, name="Project Hangar Take")
        self._write_roles([{"_key": 1, "roleGroupIDs": [1, 4]}])

        CorporationRoleGroupMembership.load_from_sde(self.tmpdir)

        self.assertEqual(CorporationRoleGroupMembership.objects.count(), 2)
        group_ids = set(
            CorporationRoleGroupMembership.objects.filter(
                corporation_role_id=1
            ).values_list("role_group_id", flat=True)
        )
        self.assertEqual(group_ids, {1, 4})

    def test_missing_role_group_ids_loads_with_no_membership_rows(self):
        CorporationRole.objects.create(id=61, name="Terrestrial Logistics Officer")
        self._write_roles([{"_key": 61}])

        CorporationRoleGroupMembership.load_from_sde(self.tmpdir)

        self.assertEqual(CorporationRoleGroupMembership.objects.count(), 0)

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        CorporationRole.objects.create(id=1, name="Project Hangar Take")
        self._write_roles([{"_key": 1, "roleGroupIDs": [1, 4]}])

        CorporationRoleGroupMembership.load_from_sde(self.tmpdir)
        CorporationRoleGroupMembership.load_from_sde(self.tmpdir)

        self.assertEqual(CorporationRoleGroupMembership.objects.count(), 2)

    def test_str_includes_role_and_group_names(self):
        role = CorporationRole.objects.create(id=1, name="Project Hangar Take")
        group = CorporationRoleGroup.objects.get(pk=1)
        membership = CorporationRoleGroupMembership.objects.create(
            corporation_role=role, role_group=group
        )
        self.assertEqual(str(membership), "Project Hangar Take (General)")


class MetenoxMoonDrillLoadTests(TestCase):

    def test_loads_keyed_off_the_item_type_pk(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemType.objects.create(id=81826, name="Metenox Moon Drill")

        row = {
            "_key": 81826,
            "miningCycleTime": 3600,
            "miningEfficiency": 0.4,
            "reagentsConsumedPerCycle": 200,
        }
        with open(os.path.join(tmpdir, "metenoxMoonDrill.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        MetenoxMoonDrill.load_from_sde(tmpdir)

        drill = MetenoxMoonDrill.objects.get(pk=81826)
        self.assertEqual(drill.mining_cycle_time, 3600)
        self.assertEqual(drill.mining_efficiency, 0.4)
        self.assertEqual(drill.reagents_consumed_per_cycle, 200)

    def test_str_includes_item_type_name_and_id(self):
        item_type = ItemType.objects.create(id=81826, name="Metenox Moon Drill")
        drill = MetenoxMoonDrill.objects.create(item_type=item_type)
        self.assertEqual(str(drill), "Metenox Moon Drill (81826)")


class SkillPlanLoadTests(TestCase):

    def test_loads_name_description_and_raw_ids(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 4,
            "internalName": "Minmatar Soldier of Fortune - Faction Militia",
            "name": {"en": "Minmatar Militia Fighter"},
            "description": {"en": "Battle for the freedom of the Minmatar Republic."},
            "careerPathID": 7,
            "factionID": 500002,
            "milestones": [],
            "skillRequirements": [],
        }
        with open(os.path.join(tmpdir, "skillPlans.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        SkillPlan.load_from_sde(tmpdir)

        plan = SkillPlan.objects.get(pk=4)
        self.assertEqual(plan.name, "Minmatar Militia Fighter")
        self.assertEqual(plan.internal_name, "Minmatar Soldier of Fortune - Faction Militia")
        self.assertEqual(plan.description, "Battle for the freedom of the Minmatar Republic.")
        self.assertEqual(plan.career_path_id_raw, 7)
        self.assertEqual(plan.faction_id_raw, 500002)
        self.assertIsNone(plan.npc_corporation_division_id_raw)


class SkillPlanMilestoneAndSkillRequirementLoadTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        SkillPlan.objects.create(id=4, name="Minmatar Militia Fighter")
        ItemType.objects.create(id=3329, name="Gunnery")
        ItemType.objects.create(id=3327, name="Small Hybrid Turret")

    def _write_skill_plan(self, milestones, skill_requirements):
        row = {"_key": 4, "milestones": milestones, "skillRequirements": skill_requirements}
        with open(os.path.join(self.tmpdir, "skillPlans.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_flattens_milestones_independently_of_skill_requirements(self):
        self._write_skill_plan(
            milestones=[{"level": 3, "typeID": 3329}],
            skill_requirements=[{"level": 1, "typeID": 3327}],
        )

        SkillPlanMilestone.load_from_sde(self.tmpdir)
        SkillPlanSkillRequirement.load_from_sde(self.tmpdir)

        self.assertEqual(SkillPlanMilestone.objects.count(), 1)
        milestone = SkillPlanMilestone.objects.get()
        self.assertEqual(milestone.item_type_id, 3329)
        self.assertEqual(milestone.level, 3)
        self.assertEqual(str(milestone), "Minmatar Militia Fighter (Gunnery 3)")

        self.assertEqual(SkillPlanSkillRequirement.objects.count(), 1)
        requirement = SkillPlanSkillRequirement.objects.get()
        self.assertEqual(requirement.item_type_id, 3327)
        self.assertEqual(requirement.level, 1)
        self.assertEqual(str(requirement), "Minmatar Militia Fighter (Small Hybrid Turret 1)")

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        self._write_skill_plan(
            milestones=[{"level": 3, "typeID": 3329}],
            skill_requirements=[{"level": 1, "typeID": 3327}],
        )

        SkillPlanMilestone.load_from_sde(self.tmpdir)
        SkillPlanMilestone.load_from_sde(self.tmpdir)
        SkillPlanSkillRequirement.load_from_sde(self.tmpdir)
        SkillPlanSkillRequirement.load_from_sde(self.tmpdir)

        self.assertEqual(SkillPlanMilestone.objects.count(), 1)
        self.assertEqual(SkillPlanSkillRequirement.objects.count(), 1)
