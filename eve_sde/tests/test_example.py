"""
Example Test
"""

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models import ItemType


class TestExample(TestCase):
    fixtures = ["eve_sde_sde"]

    """
    TestExample
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Test setup
        :return:
        :rtype:
        """

        super().setUpClass()

    def test_example(self):
        """
        Dummy test function
        :return:
        :rtype:
        """

        self.assertEqual(True, ItemType.objects.filter(id=81143).exists())
