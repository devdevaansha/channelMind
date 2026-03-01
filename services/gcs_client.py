import hashlib
import json
import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


class GCSClient:
    """Wrapper around google-cloud-storage for idempotent artifact uploads."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage

        self._storage_client = storage.Client()
        self._bucket = self._storage_client.bucket(bucket_name)
        self._bucket_name = bucket_name

    def upload_file(self, local_path: pathlib.Path, gcs_path: str) -> str:
        """
        Upload a local file to GCS.
        Returns the gs:// URI.
        """
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_filename(str(local_path))
        uri = f"gs://{self._bucket_name}/{gcs_path}"
        logger.info("Uploaded %s → %s", local_path, uri)
        return uri

    def upload_json(self, data: dict, gcs_path: str) -> str:
        """
        Upload a Python dict as JSON to GCS.
        Returns the gs:// URI.
        """
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        uri = f"gs://{self._bucket_name}/{gcs_path}"
        logger.info("Uploaded JSON → %s", uri)
        return uri

    def upload_text(self, text: str, gcs_path: str, content_type: str = "text/plain") -> str:
        """Upload a plain text string to GCS."""
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(text, content_type=content_type)
        uri = f"gs://{self._bucket_name}/{gcs_path}"
        logger.info("Uploaded text → %s", uri)
        return uri

    def download_as_text(self, gcs_path: str, encoding: str = "utf-8") -> Optional[str]:
        """Download a GCS object and return its contents as a string, or None if missing."""
        blob = self._bucket.blob(gcs_path)
        if not blob.exists():
            return None
        return blob.download_as_text(encoding=encoding)

    def exists(self, gcs_path: str) -> bool:
        return self._bucket.blob(gcs_path).exists()

    @staticmethod
    def sha256_of_file(path: pathlib.Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()


def get_gcs_client() -> GCSClient:
    from django.conf import settings
    return GCSClient(settings.GCS_BUCKET)
