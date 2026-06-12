import json
import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY must be set to use Gemini-backed tools")

    return genai.Client(api_key=GEMINI_API_KEY)


def generate_json(prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        client = get_gemini_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                responseMimeType="application/json",
            ),
        )
        return json.loads(response.text or "{}")
    except Exception as exc:
        return {
            **fallback,
            "llm_error": str(exc),
        }
