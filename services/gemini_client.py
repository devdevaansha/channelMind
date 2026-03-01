import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Max transcript chars sent to Gemini (stay within context window)
_MAX_TRANSCRIPT_CHARS = 100_000
_MAX_CLASSIFY_CHARS = 20_000


class GeminiClient:
    """
    Wrapper for Google Gemini API via google-generativeai.
    Authentication uses GOOGLE_APPLICATION_CREDENTIALS (service account).
    """

    def __init__(self, model: Optional[str] = None):
        import google.generativeai as genai
        from django.conf import settings

        genai.configure()  # picks up GOOGLE_APPLICATION_CREDENTIALS automatically
        model_name = model or settings.GEMINI_MODEL
        self._model = genai.GenerativeModel(model_name)
        logger.info("GeminiClient initialized with model=%s", model_name)

    def summarize(self, transcript_text: str, video_title: str) -> str:
        """
        Generate a markdown summary of a transcript.
        Returns a markdown string.
        """
        truncated = transcript_text[:_MAX_TRANSCRIPT_CHARS]
        prompt = (
            f"You are summarizing a YouTube video titled: '{video_title}'.\n"
            "Write a concise markdown document with these sections:\n"
            "## Overview\n## Key Points\n## Conclusion\n\n"
            f"Transcript:\n{truncated}"
        )
        logger.info("Requesting Gemini summary for '%s'", video_title)
        response = self._generate_with_retry(prompt)
        return response.text

    def classify_category(
        self, transcript_text: str, categories: list[str]
    ) -> tuple[str, float]:
        """
        Classify a transcript into one of the given category names.
        Returns (category_name, confidence) where confidence is 0.0–1.0.
        Falls back to "Other" on parse errors.
        """
        truncated = transcript_text[:_MAX_CLASSIFY_CHARS]
        cats_str = ", ".join(f'"{c}"' for c in categories)
        prompt = (
            f"Classify this transcript into exactly one of these categories: {cats_str}.\n"
            'If none fit well, use "Other".\n'
            'Respond with only valid JSON: {"category": "<name>", "confidence": <0.0-1.0>}\n\n'
            f"Transcript excerpt:\n{truncated}"
        )

        logger.info("Requesting Gemini category classification")
        response = self._generate_with_retry(prompt)

        try:
            # Strip possible markdown code fences
            text = response.text.strip().strip("```json").strip("```").strip()
            result = json.loads(text)
            return str(result["category"]), float(result["confidence"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to parse Gemini classification response: %s", e)
            return "Other", 0.0

    def _generate_with_retry(self, prompt: str, max_retries: int = 3):
        import google.api_core.exceptions as gexc

        for attempt in range(max_retries):
            try:
                return self._model.generate_content(prompt)
            except gexc.ResourceExhausted:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning("Gemini rate limited; retrying in %ds", wait)
                time.sleep(wait)
        raise RuntimeError("Gemini API exhausted retries")
