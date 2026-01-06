"""Unit tests for AudioRedactor."""

import pytest
from unittest.mock import MagicMock, patch

from presidio_analyzer import RecognizerResult

from presidio_audio_redactor import AudioRedactor


class TestAudioRedactorInit:
    """Tests for AudioRedactor initialization."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_init_default(self, mock_load_model):
        """Test default initialization."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        
        mock_load_model.assert_called_once_with("base")
        assert redactor.analyzer is not None
        assert redactor.anonymizer is not None

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_init_custom_model(self, mock_load_model):
        """Test initialization with custom Whisper model."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor(whisper_model="large")
        
        mock_load_model.assert_called_once_with("large")

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_init_custom_engines(self, mock_load_model, analyzer_engine, anonymizer_engine):
        """Test initialization with custom analyzer and anonymizer."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor(
            analyzer=analyzer_engine,
            anonymizer=anonymizer_engine,
        )
        
        assert redactor.analyzer is analyzer_engine
        assert redactor.anonymizer is anonymizer_engine


class TestTranscribe:
    """Tests for transcribe method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_transcribe_basic(self, mock_load_model, mock_whisper_model):
        """Test basic transcription."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        result = redactor.transcribe("test.wav")
        
        mock_whisper_model.transcribe.assert_called_once_with(
            "test.wav",
            word_timestamps=False,
        )
        assert "text" in result
        assert "segments" in result

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_transcribe_with_timestamps(self, mock_load_model, mock_whisper_model_with_timestamps):
        """Test transcription with word timestamps."""
        mock_load_model.return_value = mock_whisper_model_with_timestamps
        
        redactor = AudioRedactor()
        result = redactor.transcribe("test.wav", word_timestamps=True)
        
        mock_whisper_model_with_timestamps.transcribe.assert_called_once_with(
            "test.wav",
            word_timestamps=True,
        )
        assert "words" in result["segments"][0]


class TestAnalyze:
    """Tests for analyze method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_analyze_basic(self, mock_load_model, sample_text):
        """Test basic PII analysis."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        results = redactor.analyze(sample_text)
        
        assert isinstance(results, list)
        # Should find at least PERSON (John Smith) and LOCATION (New York)
        entity_types = [r.entity_type for r in results]
        assert "PERSON" in entity_types

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_analyze_with_threshold(self, mock_load_model, sample_text):
        """Test analysis with score threshold."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        
        # Low threshold should return more results
        low_results = redactor.analyze(sample_text, score_threshold=0.0)
        # High threshold should return fewer results
        high_results = redactor.analyze(sample_text, score_threshold=0.99)
        
        assert len(high_results) <= len(low_results)

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_analyze_specific_entities(self, mock_load_model, sample_text):
        """Test analysis for specific entity types only."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        results = redactor.analyze(sample_text, entities=["PERSON"])
        
        entity_types = [r.entity_type for r in results]
        assert all(et == "PERSON" for et in entity_types)


class TestAnonymize:
    """Tests for anonymize method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_anonymize_basic(self, mock_load_model, sample_text, sample_pii_results):
        """Test basic anonymization."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        result = redactor.anonymize(sample_text, sample_pii_results)
        
        assert result.text is not None
        assert "John Smith" not in result.text
        assert "<PERSON>" in result.text

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_anonymize_empty_results(self, mock_load_model, sample_text):
        """Test anonymization with no PII found."""
        mock_load_model.return_value = MagicMock()
        
        redactor = AudioRedactor()
        result = redactor.anonymize(sample_text, [])
        
        assert result.text == sample_text


class TestRedact:
    """Tests for redact method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_basic(self, mock_load_model, mock_whisper_model):
        """Test basic redaction pipeline."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        result = redactor.redact("test.wav")
        
        assert "original_text" in result
        assert "redacted_text" in result
        assert "pii_findings" in result
        assert "segments" in result
        
        # Original text should have PII
        assert "John Smith" in result["original_text"]
        # Redacted text should not have PII
        assert "John Smith" not in result["redacted_text"]

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_with_threshold(self, mock_load_model, mock_whisper_model):
        """Test redaction with score threshold."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        
        # High threshold should find fewer entities
        result = redactor.redact("test.wav", score_threshold=0.99)
        
        assert "pii_findings" in result

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_with_timestamps(self, mock_load_model, mock_whisper_model_with_timestamps):
        """Test redaction with audio timestamps."""
        mock_load_model.return_value = mock_whisper_model_with_timestamps
        
        redactor = AudioRedactor()
        result = redactor.redact("test.wav", return_timestamps=True)
        
        assert "pii_findings" in result
        
        # Check that findings have timestamp information
        for finding in result["pii_findings"]:
            assert "entity_type" in finding
            assert "text_start" in finding
            assert "text_end" in finding
            assert "score" in finding
            # Should have audio timestamps for at least some findings
            if "audio_start" in finding:
                assert "audio_end" in finding
                assert isinstance(finding["audio_start"], float)
                assert isinstance(finding["audio_end"], float)

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_pii_findings_structure(self, mock_load_model, mock_whisper_model):
        """Test that PII findings have correct structure."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        result = redactor.redact("test.wav")
        
        for finding in result["pii_findings"]:
            assert "entity_type" in finding
            assert "text_start" in finding
            assert "text_end" in finding
            assert "score" in finding
            assert "text" in finding
            assert isinstance(finding["score"], float)
            assert 0 <= finding["score"] <= 1


class TestRedactAndSave:
    """Tests for redact_and_save method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_and_save_default_path(self, mock_load_model, mock_whisper_model, tmp_path):
        """Test saving redacted text to default path."""
        mock_load_model.return_value = mock_whisper_model
        
        # Create a fake audio file path
        audio_path = tmp_path / "recording.wav"
        audio_path.touch()
        
        redactor = AudioRedactor()
        output_path = redactor.redact_and_save(str(audio_path))
        
        assert output_path == str(tmp_path / "recording_redacted.txt")
        
        # Verify file was created and has content
        with open(output_path) as f:
            content = f.read()
        assert "John Smith" not in content

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_and_save_custom_path(self, mock_load_model, mock_whisper_model, tmp_path):
        """Test saving redacted text to custom path."""
        mock_load_model.return_value = mock_whisper_model
        
        audio_path = tmp_path / "recording.wav"
        audio_path.touch()
        output_path = tmp_path / "custom_output.txt"
        
        redactor = AudioRedactor()
        result_path = redactor.redact_and_save(
            str(audio_path),
            output_path=str(output_path),
        )
        
        assert result_path == str(output_path)
        assert output_path.exists()

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_redact_and_save_with_threshold(self, mock_load_model, mock_whisper_model, tmp_path):
        """Test saving with score threshold."""
        mock_load_model.return_value = mock_whisper_model
        
        audio_path = tmp_path / "recording.wav"
        audio_path.touch()
        
        redactor = AudioRedactor()
        output_path = redactor.redact_and_save(
            str(audio_path),
            score_threshold=0.5,
        )
        
        assert output_path.endswith("_redacted.txt")


class TestExtractWordTimestamps:
    """Tests for _extract_word_timestamps method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_extract_word_timestamps(
        self, mock_load_model, mock_whisper_model, sample_transcription_with_timestamps
    ):
        """Test extraction of word timestamps."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        words = redactor._extract_word_timestamps(sample_transcription_with_timestamps)
        
        assert len(words) > 0
        for word in words:
            assert "word" in word
            assert "start" in word
            assert "end" in word
            assert isinstance(word["start"], float)
            assert isinstance(word["end"], float)


class TestMapPiiToTimestamps:
    """Tests for _map_pii_to_timestamps method."""

    @patch("presidio_audio_redactor.audio_redactor.whisper.load_model")
    def test_map_pii_to_timestamps(
        self,
        mock_load_model,
        mock_whisper_model,
        sample_text,
        sample_pii_results,
        sample_transcription_with_timestamps,
    ):
        """Test mapping PII results to audio timestamps."""
        mock_load_model.return_value = mock_whisper_model
        
        redactor = AudioRedactor()
        word_timestamps = redactor._extract_word_timestamps(
            sample_transcription_with_timestamps
        )
        
        pii_with_timestamps = redactor._map_pii_to_timestamps(
            sample_text, sample_pii_results, word_timestamps
        )
        
        assert len(pii_with_timestamps) == len(sample_pii_results)
        
        for pii in pii_with_timestamps:
            assert "entity_type" in pii
            assert "text_start" in pii
            assert "text_end" in pii
            assert "score" in pii
            assert "text" in pii

