# Third Party
from modeltranslation.translator import TranslationOptions, translator

from .models import Constellation, Moon, Planet, Region, SolarSystem


class RegionTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class NameTranslationOptions(TranslationOptions):
    fields = ('name', )


translator.register(Region, RegionTranslationOptions)
translator.register(Constellation, NameTranslationOptions)
translator.register(SolarSystem, NameTranslationOptions)
translator.register(Planet, NameTranslationOptions)
# translator.register(Moon, NameTranslationOptions)
