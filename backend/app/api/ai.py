from fastapi import APIRouter, HTTPException

from app.integrations.gemini.provider import GeminiProvider


router = APIRouter(
    prefix="/ai",
    tags=["ai"],
)


@router.get("/connection")
async def test_ai_connection():
    try:
        provider = GeminiProvider()

        return provider.test_connection()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )