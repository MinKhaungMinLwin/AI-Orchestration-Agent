import logging

from fastapi import APIRouter, HTTPException
from schemas.tstation.example_question import QuestionCategory, SupportedLanguage
from services.tstation.example_question import ExampleQuestionsService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/chat/example_questions/{language}", response_model=dict)
async def get_example_questions(language: str):
    """
    Get example questions for a given language for T-station

    Parameters:

        language (str): The language code, supported in ["en", "ko"]

    Returns:

        list_categories (list): List categories
        categories (list): List question categories
            - name (str): Name of category when show in UI
            - explanation (str): Explanation of category when show in UI
            - questions (list): List of questions
    """
    try:
        # Handler language supported
        supported_languages = [lang.value for lang in SupportedLanguage]
        if language not in supported_languages:
            raise ValueError(f"Language '{language}' is not supported. Supported languages: {supported_languages}")

        return {
            "list_categories": [category.value for category in QuestionCategory],
            "categories": ExampleQuestionsService.get_example_questions_by_language(language),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(f"Error while /chat/example_questions/{language}")
        raise HTTPException(status_code=500, detail="Internal server error")
