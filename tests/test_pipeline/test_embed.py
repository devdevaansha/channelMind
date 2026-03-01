"""Tests for chunking logic in embed task."""
import pytest


class TestChunkSegments:
    def test_empty_segments(self):
        from apps.pipeline.tasks.embed import _chunk_segments
        assert _chunk_segments([], 30, 5) == []

    def test_single_segment(self):
        from apps.pipeline.tasks.embed import _chunk_segments
        segs = [{"start": 0.0, "end": 10.0, "text": "Hello world"}]
        chunks = _chunk_segments(segs, 30, 5)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Hello world"

    def test_multiple_segments_produce_overlap(self):
        from apps.pipeline.tasks.embed import _chunk_segments
        segs = [
            {"start": i * 5.0, "end": (i + 1) * 5.0, "text": f"seg{i}"}
            for i in range(20)
        ]
        chunks = _chunk_segments(segs, 30, 5)
        # Should produce multiple overlapping chunks
        assert len(chunks) > 1

    def test_no_empty_chunks(self):
        from apps.pipeline.tasks.embed import _chunk_segments
        segs = [{"start": i * 5.0, "end": (i + 1) * 5.0, "text": f"t{i}"} for i in range(10)]
        chunks = _chunk_segments(segs, 30, 5)
        for c in chunks:
            assert c["text"].strip() != ""
