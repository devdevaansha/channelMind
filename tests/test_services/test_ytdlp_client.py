"""Tests for YtDlpClient (mocked yt-dlp)."""
import pytest


class TestYtDlpClientParsing:
    def test_parse_upload_date_valid(self):
        from services.ytdlp_client import _parse_upload_date
        dt = _parse_upload_date("20240115")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_upload_date_none(self):
        from services.ytdlp_client import _parse_upload_date
        assert _parse_upload_date(None) is None

    def test_parse_upload_date_invalid(self):
        from services.ytdlp_client import _parse_upload_date
        assert _parse_upload_date("notadate") is None


class TestListChannelVideos:
    def test_list_stops_at_cursor(self, mocker):
        from services.ytdlp_client import YtDlpClient

        mock_ydl = mocker.MagicMock()
        mock_ydl.__enter__ = mocker.MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = mocker.MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "vid3", "title": "Video 3", "upload_date": "20240301", "duration": 100},
                {"id": "vid2", "title": "Video 2", "upload_date": "20240201", "duration": 200},
                {"id": "vid1", "title": "Video 1", "upload_date": "20240101", "duration": 300},
            ]
        }
        mocker.patch("yt_dlp.YoutubeDL", return_value=mock_ydl)

        client = YtDlpClient()
        results = client.list_channel_videos("UCtest", after="vid2")
        # Should only return vid3 (stops at cursor vid2)
        assert len(results) == 1
        assert results[0]["id"] == "vid3"

    def test_list_all_when_no_cursor(self, mocker):
        from services.ytdlp_client import YtDlpClient

        mock_ydl = mocker.MagicMock()
        mock_ydl.__enter__ = mocker.MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = mocker.MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "vid1", "title": "V1", "upload_date": "20240101", "duration": 60},
                {"id": "vid2", "title": "V2", "upload_date": "20240102", "duration": 60},
            ]
        }
        mocker.patch("yt_dlp.YoutubeDL", return_value=mock_ydl)

        client = YtDlpClient()
        results = client.list_channel_videos("UCtest", after="")
        assert len(results) == 2
