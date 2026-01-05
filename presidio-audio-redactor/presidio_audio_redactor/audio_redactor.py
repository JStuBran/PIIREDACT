"""Audio Redactor - Transcribe audio and redact PII from the transcript."""

from typing import Optional, List
import whisper
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import EngineResult


class AudioRedactor:
    """Redact PII from audio files by transcribing and anonymizing the text."""

    def __init__(
        self,
        whisper_model: str = "base",
        analyzer: Optional[AnalyzerEngine] = None,
        anonymizer: Optional[AnonymizerEngine] = None,
    ):
        """
        Initialize the AudioRedactor.

        Args:
            whisper_model: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
            analyzer: Custom AnalyzerEngine instance (uses default if None)
            anonymizer: Custom AnonymizerEngine instance (uses default if None)
        """
        self.whisper_model = whisper.load_model(whisper_model)
        self.analyzer = analyzer or AnalyzerEngine()
        self.anonymizer = anonymizer or AnonymizerEngine()

    def transcribe(self, audio_path: str) -> dict:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to the audio file

        Returns:
            Whisper transcription result dict with 'text' and 'segments'
        """
        return self.whisper_model.transcribe(audio_path)

    def analyze(
        self,
        text: str,
        language: str = "en",
        entities: Optional[List[str]] = None,
    ) -> List[RecognizerResult]:
        """
        Analyze text for PII entities.

        Args:
            text: Text to analyze
            language: Language code (default: 'en')
            entities: List of entity types to detect (detects all if None)

        Returns:
            List of RecognizerResult with detected PII
        """
        return self.analyzer.analyze(
            text=text,
            language=language,
            entities=entities,
        )

    def anonymize(
        self,
        text: str,
        analyzer_results: List[RecognizerResult],
    ) -> EngineResult:
        """
        Anonymize PII in text.

        Args:
            text: Original text
            analyzer_results: Results from analyze()

        Returns:
            EngineResult with anonymized text
        """
        return self.anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
        )

    def redact(
        self,
        audio_path: str,
        language: str = "en",
        entities: Optional[List[str]] = None,
    ) -> dict:
        """
        Transcribe audio and redact PII from the transcript.

        Args:
            audio_path: Path to the audio file
            language: Language code for PII detection (default: 'en')
            entities: List of entity types to detect (detects all if None)

        Returns:
            Dict with 'original_text', 'redacted_text', and 'pii_findings'
        """
        transcription = self.transcribe(audio_path)
        original_text = transcription["text"]

        pii_results = self.analyze(
            text=original_text,
            language=language,
            entities=entities,
        )

        anonymized = self.anonymize(
            text=original_text,
            analyzer_results=pii_results,
        )

        return {
            "original_text": original_text,
            "redacted_text": anonymized.text,
            "pii_findings": [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score,
                }
                for r in pii_results
            ],
        }
