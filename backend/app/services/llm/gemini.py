import json
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import logger
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)


class LLMExtractionError(AppException):
    """Raised when LLM extraction fails or returns malformed clinical data."""

    def __init__(self, message: str = "Clinical evidence extraction failed", code: str = "LLM_EXTRACTION_FAILED"):
        super().__init__(code=code, message=message, status_code=502)


class GeminiProvider:
    """Production provider using Google GenAI SDK (gemini-2.5-flash) for structured clinical NLP."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise LLMExtractionError(
                    message="GEMINI_API_KEY is not configured.", code="LLM_CONFIG_MISSING"
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.error(f"Failed to initialize google.genai Client: {exc}")
                raise LLMExtractionError(f"Failed to initialize Gemini client: {exc}")
        return self._client

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        """Extracts structured evidence items, duration, and severity using Gemini 2.5 Flash."""
        client = self._get_client()

        catalog_summary = ""
        if context and "evidence_catalog" in context:
            # Provide relevant subset or top evidences to constrain extraction
            catalog_summary = f"\nControlled Evidence Catalog Sample:\n{context['evidence_catalog']}\n"

        system_instruction = (
            "You are a clinical NLP evidence extraction assistant for an outpatient care-navigation platform. "
            "Your task is to extract only symptoms, negations, durations, and severity explicitly stated by the patient. "
            "CRITICAL RULES:\n"
            "1. Do NOT hallucinate or assume unmentioned symptoms.\n"
            "2. If the patient denies or negates a symptom (e.g., 'no fever', 'I don't have chest pain'), "
            "set status='ABSENT'.\n"
            "3. If the patient expresses uncertainty (e.g., 'not sure if I have fever', 'maybe'), "
            "set status='UNKNOWN'.\n"
            "4. Only assign status='PRESENT' if the patient affirmatively confirms having the symptom.\n"
            "5. Map extracted symptoms to DDXPlus evidence codes (e.g., E_53 for pain, E_91 for fever, E_50 for cough, "
            "E_54_@_V_180 for chest pain, E_88 for shortness of breath, E_127 for headache, E_14 for vomiting) where applicable.\n"
            "6. Output MUST strictly match the ExtractedEvidenceResult JSON schema."
        )

        prompt = (
            f"Patient message: \"{message}\"\n"
            f"{catalog_summary}\n"
            "Extract all clinical evidence, duration, and severity."
        )

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ExtractedEvidenceResult,
                    temperature=0.0,
                ),
            )

            result_json = json.loads(response.text)
            return ExtractedEvidenceResult.model_validate(result_json)
        except (json.JSONDecodeError, ValidationError) as parse_err:
            logger.warning(f"Gemini output parsing failed: {parse_err}")
            raise LLMExtractionError(f"Malformed LLM response: {parse_err}")
        except Exception as exc:
            logger.error(f"Gemini API call failed: {exc}")
            raise LLMExtractionError(f"Gemini communication error: {exc}")

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Phrases a controlled medical evidence question in empathetic conversational language."""
        client = self._get_client()

        system_instruction = (
            "You are an empathetic outpatient care-navigation assistant. "
            "Given a controlled clinical evidence question, phrase it in natural, compassionate, and clear conversational language. "
            "RULES:\n"
            "1. You MUST NOT alter the clinical meaning of the question.\n"
            "2. Do NOT diagnose or state 'You have X disease'.\n"
            "3. Keep the phrasing concise, supportive, and outpatient-appropriate.\n"
            "4. Return ONLY the phrased question as plain text."
        )

        prompt = f"Controlled question: \"{controlled_question}\" (Evidence ID: {evidence_id})"

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                ),
            )
            phrased = response.text.strip()
            # If Gemini returned an empty or degenerate string, fallback to controlled question
            if not phrased or len(phrased) < 5:
                return controlled_question
            return phrased
        except Exception as exc:
            logger.warning(f"Gemini phrasing failed, using controlled question: {exc}")
            return controlled_question

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        client = self._get_client()
        conversation_text = "\n".join(
            f"{m.get('sender', 'user')}: {m.get('content', '')}" for m in messages
        )
        prompt = (
            "Summarize the patient's reported symptoms, timeline, and negative findings in 2-3 concise sentences:\n"
            f"{conversation_text}"
        )
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as exc:
            logger.warning(f"Gemini dialogue summarization failed: {exc}")
            return "Patient reported outpatient symptoms requiring clinical evaluation."
