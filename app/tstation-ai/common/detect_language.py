from enum import Enum

from lingua import Language, LanguageDetectorBuilder


class SupportedLanguage(Enum):
    ENGLISH = Language.ENGLISH
    VIETNAMESE = Language.VIETNAMESE
    KOREAN = Language.KOREAN
    CHINESE = Language.CHINESE
    JAPANESE = Language.JAPANESE
    UNKNOWN = None

    @property
    def display_name(self) -> str:
        return self.value.name.capitalize() if self.value else "Unknown"


# Eager loading
MAIN_LANGUAGES = [lang.value for lang in SupportedLanguage if lang.value]
_detector = (
    LanguageDetectorBuilder
    .from_languages(*MAIN_LANGUAGES)
    .with_minimum_relative_distance(0.8)
    .with_preloaded_language_models()
    .build()
)


def detect_language(text: str) -> SupportedLanguage:
    """
    Detect the language of the given text.
    Returns a SupportedLanguage enum:
        - ENGLISH, VIETNAMESE, KOREAN, CHINESE, JAPANESE
        - UNKNOWN.
    """
    if not text or not text.strip():
        return SupportedLanguage.UNKNOWN

    detected = _detector.detect_language_of(text)
    if detected in MAIN_LANGUAGES:
        try:
            return SupportedLanguage(detected)
        except ValueError:
            return SupportedLanguage.UNKNOWN

    return SupportedLanguage.UNKNOWN
