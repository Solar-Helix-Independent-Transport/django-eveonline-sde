# Third Party
from modeltranslation.translator import TranslationOptions, translator

from .models.map import Constellation, Planet, Region, SolarSystem
from .models.types import ItemCategory, ItemGroup, ItemType


class NameAndDescriptionTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class NameTranslationOptions(TranslationOptions):
    fields = ('name', )


translator.register(Region, NameAndDescriptionTranslationOptions)
translator.register(Constellation, NameTranslationOptions)
translator.register(SolarSystem, NameTranslationOptions)
translator.register(Planet, NameTranslationOptions)
translator.register(ItemCategory, NameTranslationOptions)
translator.register(ItemGroup, NameTranslationOptions)
translator.register(ItemType, NameAndDescriptionTranslationOptions)
# translator.register(Moon, NameTranslationOptions)
