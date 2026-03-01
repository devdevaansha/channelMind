import logging
import pathlib
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _parse_upload_date(upload_date: Optional[str]) -> Optional[datetime]:
    """Parse yt-dlp's YYYYMMDD string into a UTC datetime."""
    if not upload_date:
        return None
    try:
        dt = datetime.strptime(upload_date, "%Y%m%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class YtDlpClient:
    """Thin wrapper around yt-dlp for downloading audio and listing channel videos."""

    def download(
        self,
        video_id: str,
        output_dir: pathlib.Path,
        progress_hook: Optional[Callable] = None,
    ) -> pathlib.Path:
        """
        Download best audio for a YouTube video.
        Returns the path to the downloaded file.
        """
        import yt_dlp

        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / "audio.%(ext)s")

        opts: dict = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
        }
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Downloading audio for video=%s", video_id)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        ext = info.get("ext", "m4a")
        audio_path = output_dir / f"audio.{ext}"
        if not audio_path.exists():
            # yt-dlp may rename; find whatever it wrote
            candidates = list(output_dir.glob("audio.*"))
            if not candidates:
                raise FileNotFoundError(f"No audio file found in {output_dir}")
            audio_path = candidates[0]

        logger.info("Downloaded audio to %s", audio_path)
        return audio_path

    def list_channel_videos(self, channel_id: str, after: str = "") -> list[dict]:
        """
        List videos for a YouTube channel using flat playlist extraction.
        Returns newest-first list of dicts: {id, title, published_at, duration}.
        Stops collecting when it encounters `after` (the video ID cursor).
        No YouTube Data API key required.
        """
        import yt_dlp

        url = f"https://www.youtube.com/channel/{channel_id}/videos"

        opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "playlistend": 500,
        }

        logger.info("Listing videos for channel=%s after=%s", channel_id, after or "beginning")

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = info.get("entries") or []
        results = []

        for entry in entries:
            vid_id = entry.get("id", "")
            if after and vid_id == after:
                break  # reached the cursor — stop collecting
            results.append({
                "id": vid_id,
                "title": entry.get("title", ""),
                "published_at": _parse_upload_date(entry.get("upload_date")),
                "duration": entry.get("duration"),
            })

        logger.info("Found %d new videos for channel=%s", len(results), channel_id)
        return results

    def get_channel_info(self, channel_url: str) -> dict:
        """
        Resolve a channel URL / handle to its canonical channel ID and title.
        Accepts URLs like: https://www.youtube.com/@handle, /channel/UC..., etc.
        """
        import yt_dlp

        opts = {
            "extract_flat": True,
            "playlist_items": "0",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        return {
            "channel_id": info.get("channel_id") or info.get("id", ""),
            "title": info.get("channel") or info.get("title", ""),
        }
