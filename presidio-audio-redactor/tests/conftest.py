"""Pytest fixtures for presidio-audio-redactor tests."""

import os
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine


SCRIPT_DIR = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def mock_whisper_model():
    """Create a mock Whisper model for testing without loading real model."""
    mock_model = MagicMock()
    
    # Default transcription result
    mock_model.transcribe.return_value = {
        "text": " Hello, my name is John Smith and I live in New York.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.5,
                "text": " Hello, my name is John Smith and I live in New York.",
            }
        ],
    }
    
    return mock_model


@pytest.fixture(scope="module")
def mock_whisper_model_with_timestamps():
    """Create a mock Whisper model that returns word-level timestamps."""
    mock_model = MagicMock()
    
    mock_model.transcribe.return_value = {
        "text": " Hello, my name is John Smith and I live in New York.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.5,
                "text": " Hello, my name is John Smith and I live in New York.",
                "words": [
                    {"word": " Hello,", "start": 0.0, "end": 0.4},
                    {"word": " my", "start": 0.4, "end": 0.6},
                    {"word": " name", "start": 0.6, "end": 0.8},
                    {"word": " is", "start": 0.8, "end": 1.0},
                    {"word": " John", "start": 1.0, "end": 1.3},
                    {"word": " Smith", "start": 1.3, "end": 1.6},
                    {"word": " and", "start": 1.6, "end": 1.8},
                    {"word": " I", "start": 1.8, "end": 1.9},
                    {"word": " live", "start": 1.9, "end": 2.1},
                    {"word": " in", "start": 2.1, "end": 2.3},
                    {"word": " New", "start": 2.3, "end": 2.6},
                    {"word": " York.", "start": 2.6, "end": 3.0},
                ],
            }
        ],
    }
    
    return mock_model


@pytest.fixture(scope="function")
def analyzer_engine():
    """Create a real AnalyzerEngine for integration tests."""
    return AnalyzerEngine()


@pytest.fixture(scope="function")
def anonymizer_engine():
    """Create a real AnonymizerEngine for integration tests."""
    return AnonymizerEngine()


@pytest.fixture(scope="function")
def sample_pii_results() -> List[RecognizerResult]:
    """Sample PII analysis results."""
    return [
        RecognizerResult(entity_type="PERSON", start=19, end=29, score=0.85),
        RecognizerResult(entity_type="LOCATION", start=44, end=52, score=0.85),
    ]


@pytest.fixture(scope="function")
def sample_text() -> str:
    """Sample text with PII."""
    return " Hello, my name is John Smith and I live in New York."


@pytest.fixture(scope="function")
def sample_transcription() -> Dict:
    """Sample Whisper transcription result."""
    return {
        "text": " Hello, my name is John Smith and I live in New York.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.5,
                "text": " Hello, my name is John Smith and I live in New York.",
            }
        ],
    }


@pytest.fixture(scope="function")
def sample_transcription_with_timestamps() -> Dict:
    """Sample Whisper transcription with word-level timestamps."""
    return {
        "text": " Hello, my name is John Smith and I live in New York.",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.5,
                "text": " Hello, my name is John Smith and I live in New York.",
                "words": [
                    {"word": " Hello,", "start": 0.0, "end": 0.4},
                    {"word": " my", "start": 0.4, "end": 0.6},
                    {"word": " name", "start": 0.6, "end": 0.8},
                    {"word": " is", "start": 0.8, "end": 1.0},
                    {"word": " John", "start": 1.0, "end": 1.3},
                    {"word": " Smith", "start": 1.3, "end": 1.6},
                    {"word": " and", "start": 1.6, "end": 1.8},
                    {"word": " I", "start": 1.8, "end": 1.9},
                    {"word": " live", "start": 1.9, "end": 2.1},
                    {"word": " in", "start": 2.1, "end": 2.3},
                    {"word": " New", "start": 2.3, "end": 2.6},
                    {"word": " York.", "start": 2.6, "end": 3.0},
                ],
            }
        ],
    }

