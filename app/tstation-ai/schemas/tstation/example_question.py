from enum import Enum


class SupportedLanguage(str, Enum):
    EN = "en"
    KO = "ko"

class QuestionCategory(str, Enum):
    HOLISTIC  = "holistic"
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    CONVERSION = "conversion"
    SERVICE = "service"

