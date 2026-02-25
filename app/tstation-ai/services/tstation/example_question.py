import json
import logging
from pathlib import Path
from typing import Dict

from config.env import settings

logger = logging.getLogger(__name__)


class ExampleQuestionsService(object):
    __instance = None

    @staticmethod
    def get_example_questions_by_language(language: str) -> Dict:
        """Load example questions from JSON file"""

        # Load from file
        file_path = Path(settings.APP_STATIC_DIR) / f"files/example_questions/{language}.json"
        if not file_path.exists():
            raise Exception(f"Can't find the file at: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data
