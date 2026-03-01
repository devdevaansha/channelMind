"""Unit tests for GCSClient (mocked storage)."""
import json
import pathlib
import pytest


class TestGCSClient:
    def test_upload_file_returns_uri(self, mocker, tmp_path):
        mock_storage = mocker.patch("google.cloud.storage.Client")
        mock_bucket = mocker.MagicMock()
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_blob = mocker.MagicMock()
        mock_bucket.blob.return_value = mock_blob

        from services.gcs_client import GCSClient
        client = GCSClient("test-bucket")

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        uri = client.upload_file(test_file, "path/to/test.txt")

        assert uri == "gs://test-bucket/path/to/test.txt"
        mock_blob.upload_from_filename.assert_called_once()

    def test_upload_json_returns_uri(self, mocker):
        mock_storage = mocker.patch("google.cloud.storage.Client")
        mock_bucket = mocker.MagicMock()
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_blob = mocker.MagicMock()
        mock_bucket.blob.return_value = mock_blob

        from services.gcs_client import GCSClient
        client = GCSClient("test-bucket")

        uri = client.upload_json({"key": "value"}, "path/data.json")
        assert uri == "gs://test-bucket/path/data.json"

    def test_sha256_of_file(self, tmp_path):
        from services.gcs_client import GCSClient
        f = tmp_path / "f.txt"
        f.write_bytes(b"hello")
        sha = GCSClient.sha256_of_file(f)
        # Known SHA256 of b"hello"
        assert sha == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


class TestGeminiClient:
    def test_summarize_returns_text(self, mocker):
        mock_genai = mocker.patch("google.generativeai.configure")
        mock_model_cls = mocker.patch("google.generativeai.GenerativeModel")
        mock_instance = mocker.MagicMock()
        mock_instance.generate_content.return_value.text = "## Summary\nGreat video."
        mock_model_cls.return_value = mock_instance

        from services.gemini_client import GeminiClient
        mocker.patch("django.conf.settings.GEMINI_MODEL", "gemini-2.5-flash")
        client = GeminiClient()
        result = client.summarize("Long transcript text...", "My Video")
        assert "Summary" in result

    def test_classify_category_returns_tuple(self, mocker):
        mock_genai = mocker.patch("google.generativeai.configure")
        mock_model_cls = mocker.patch("google.generativeai.GenerativeModel")
        mock_instance = mocker.MagicMock()
        mock_instance.generate_content.return_value.text = '{"category": "Technology", "confidence": 0.9}'
        mock_model_cls.return_value = mock_instance

        from services.gemini_client import GeminiClient
        mocker.patch("django.conf.settings.GEMINI_MODEL", "gemini-2.5-flash-latest")
        client = GeminiClient()
        cat, conf = client.classify_category("some transcript", ["Technology", "Finance"])
        assert cat == "Technology"
        assert abs(conf - 0.9) < 0.01

    def test_classify_category_falls_back_on_json_error(self, mocker):
        mock_genai = mocker.patch("google.generativeai.configure")
        mock_model_cls = mocker.patch("google.generativeai.GenerativeModel")
        mock_instance = mocker.MagicMock()
        mock_instance.generate_content.return_value.text = "not json"
        mock_model_cls.return_value = mock_instance

        from services.gemini_client import GeminiClient
        mocker.patch("django.conf.settings.GEMINI_MODEL", "gemini-2.5-flash")
        client = GeminiClient()
        cat, conf = client.classify_category("transcript", ["Technology"])
        assert cat == "Other"
        assert conf == 0.0
