"""Audio Redactor - Transcribe audio and redact PII from the transcript."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import whisper
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import EngineResult

logger = logging.getLogger("presidio-audio-redactor")


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
        logger.info(f"Loading Whisper model: {whisper_model}")
        self.whisper_model = whisper.load_model(whisper_model)
        self.analyzer = analyzer or AnalyzerEngine()
        self.anonymizer = anonymizer or AnonymizerEngine()
        logger.info("AudioRedactor initialized successfully")

    def transcribe(
        self,
        audio_path: str,
        word_timestamps: bool = False,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to the audio file
            word_timestamps: If True, include word-level timestamps in output

        Returns:
            Whisper transcription result dict with 'text', 'segments', and optionally 'words'
        """
        logger.debug(f"Transcribing audio file: {audio_path}")
        # Optimize transcription settings for speed
        result = self.whisper_model.transcribe(
            audio_path,
            word_timestamps=word_timestamps,
            fp16=False,  # CPU doesn't support FP16
            verbose=False,  # Reduce logging overhead
            # Use faster decoding (greedy instead of beam search for speed)
            beam_size=1 if not word_timestamps else 5,  # Smaller beam = faster
        )
        logger.debug(f"Transcription complete. Length: {len(result.get('text', ''))}")
        return result

    def analyze(
        self,
        text: str,
        language: str = "en",
        entities: Optional[List[str]] = None,
        score_threshold: float = 0.0,
    ) -> List[RecognizerResult]:
        """
        Analyze text for PII entities.

        Args:
            text: Text to analyze
            language: Language code (default: 'en')
            entities: List of entity types to detect (detects all if None)
            score_threshold: Minimum confidence score for detected entities

        Returns:
            List of RecognizerResult with detected PII
        """
        logger.debug(f"Analyzing text for PII. Language: {language}, Threshold: {score_threshold}")
        results = self.analyzer.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )
        logger.debug(f"Found {len(results)} PII entities")
        return results

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
        logger.debug(f"Anonymizing {len(analyzer_results)} PII entities")
        return self.anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
        )

    def _extract_word_timestamps(
        self,
        transcription: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extract word-level timestamps from Whisper transcription.

        Args:
            transcription: Whisper transcription result with word_timestamps=True

        Returns:
            List of dicts with 'word', 'start', 'end' for each word
        """
        words = []
        for segment in transcription.get("segments", []):
            for word_info in segment.get("words", []):
                words.append({
                    "word": word_info.get("word", ""),
                    "start": word_info.get("start", 0.0),
                    "end": word_info.get("end", 0.0),
                })
        return words

    def _map_pii_to_timestamps(
        self,
        text: str,
        pii_results: List[RecognizerResult],
        word_timestamps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Map PII text positions to audio timestamps.

        Args:
            text: The full transcribed text
            pii_results: List of RecognizerResult from analysis
            word_timestamps: List of word timestamp dicts from Whisper

        Returns:
            List of PII findings with audio timestamps
        """
        pii_with_timestamps = []
        
        # Build a character-to-word mapping
        char_pos = 0
        char_to_word = {}
        
        for idx, word_info in enumerate(word_timestamps):
            word = word_info["word"]
            # Find the word in the text starting from current position
            word_stripped = word.strip()
            word_start = text.find(word_stripped, char_pos)
            if word_start != -1:
                for i in range(word_start, word_start + len(word_stripped)):
                    char_to_word[i] = idx
                char_pos = word_start + len(word_stripped)
        
        for result in pii_results:
            # Find word indices for PII start and end
            start_word_idx = None
            end_word_idx = None
            
            for char_idx in range(result.start, result.end):
                if char_idx in char_to_word:
                    word_idx = char_to_word[char_idx]
                    if start_word_idx is None:
                        start_word_idx = word_idx
                    end_word_idx = word_idx
            
            pii_info = {
                "entity_type": result.entity_type,
                "text_start": result.start,
                "text_end": result.end,
                "score": result.score,
                "text": text[result.start:result.end],
            }
            
            # Add timestamps if we found matching words
            if start_word_idx is not None and end_word_idx is not None:
                pii_info["audio_start"] = word_timestamps[start_word_idx]["start"]
                pii_info["audio_end"] = word_timestamps[end_word_idx]["end"]
            
            pii_with_timestamps.append(pii_info)
        
        return pii_with_timestamps

    def redact(
        self,
        audio_path: str,
        language: str = "en",
        entities: Optional[List[str]] = None,
        score_threshold: float = 0.0,
        return_timestamps: bool = False,
    ) -> Dict[str, Any]:
        """
        Transcribe audio and redact PII from the transcript.

        Args:
            audio_path: Path to the audio file
            language: Language code for PII detection (default: 'en')
            entities: List of entity types to detect (detects all if None)
            score_threshold: Minimum confidence score for detected entities (0.0-1.0)
            return_timestamps: If True, include audio timestamps for each PII finding

        Returns:
            Dict with 'original_text', 'redacted_text', 'pii_findings', and optionally 'segments'
        """
        logger.info(f"Starting redaction for: {audio_path}")
        
        # Transcribe with word timestamps if needed
        transcription = self.transcribe(audio_path, word_timestamps=return_timestamps)
        original_text = transcription["text"]
        
        logger.debug(f"Transcribed text length: {len(original_text)}")
        
        # Analyze for PII
        pii_results = self.analyze(
            text=original_text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )
        
        # Anonymize
        anonymized = self.anonymize(
            text=original_text,
            analyzer_results=pii_results,
        )
        
        # Build response
        result = {
            "original_text": original_text,
            "redacted_text": anonymized.text,
            "segments": transcription.get("segments", []),
        }
        
        # Add PII findings with optional timestamps
        if return_timestamps:
            word_timestamps = self._extract_word_timestamps(transcription)
            result["pii_findings"] = self._map_pii_to_timestamps(
                original_text, pii_results, word_timestamps
            )
        else:
            result["pii_findings"] = [
                {
                    "entity_type": r.entity_type,
                    "text_start": r.start,
                    "text_end": r.end,
                    "score": r.score,
                    "text": original_text[r.start:r.end],
                }
                for r in pii_results
            ]
        
        logger.info(f"Redaction complete. Found {len(pii_results)} PII entities")
        return result

    def redact_and_save(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        language: str = "en",
        entities: Optional[List[str]] = None,
        score_threshold: float = 0.0,
    ) -> str:
        """
        Transcribe audio, redact PII, and save to a text file.

        Args:
            audio_path: Path to the audio file
            output_path: Path for output file (default: same name with _redacted.txt)
            language: Language code for PII detection (default: 'en')
            entities: List of entity types to detect (detects all if None)
            score_threshold: Minimum confidence score for detected entities (0.0-1.0)

        Returns:
            Path to the saved output file
        """
        result = self.redact(
            audio_path,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )

        if output_path is None:
            audio_file = Path(audio_path)
            output_path = str(audio_file.parent / f"{audio_file.stem}_redacted.txt")

        with open(output_path, "w") as f:
            f.write(result["redacted_text"])

        logger.info(f"Saved redacted text to: {output_path}")
        return output_path
