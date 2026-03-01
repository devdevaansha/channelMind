import io
import logging
import os
from datetime import datetime

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

logger = logging.getLogger(__name__)

_FONTS_REGISTERED = False
_FONT_NAME = "Helvetica"
_FONT_NAME_BOLD = "Helvetica-Bold"

_TTF_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/freefont",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/truetype",
    # macOS
    "/System/Library/Fonts",
    "/Library/Fonts",
    # Windows
    "C:/Windows/Fonts",
]

_TTF_CANDIDATES = [
    ("FreeSans.ttf", "FreeSansBold.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
]


def _register_unicode_fonts():
    """Find and register a TTF font with broad Unicode support."""
    global _FONTS_REGISTERED, _FONT_NAME, _FONT_NAME_BOLD
    if _FONTS_REGISTERED:
        return

    for font_dir in _TTF_SEARCH_PATHS:
        if not os.path.isdir(font_dir):
            continue
        for regular_name, bold_name in _TTF_CANDIDATES:
            regular_path = os.path.join(font_dir, regular_name)
            bold_path = os.path.join(font_dir, bold_name)
            if os.path.isfile(regular_path):
                try:
                    pdfmetrics.registerFont(TTFont("UniFont", regular_path))
                    _FONT_NAME = "UniFont"
                    if os.path.isfile(bold_path):
                        pdfmetrics.registerFont(TTFont("UniFontBold", bold_path))
                        _FONT_NAME_BOLD = "UniFontBold"
                    else:
                        _FONT_NAME_BOLD = "UniFont"
                    _FONTS_REGISTERED = True
                    logger.info("Registered TTF font: %s", regular_path)
                    return
                except Exception:
                    logger.warning("Failed to register font %s", regular_path)

    logger.warning("No Unicode TTF font found; PDF may not render non-Latin text")
    _FONTS_REGISTERED = True


def _format_timestamp(seconds):
    """Convert float seconds to MM:SS string."""
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _safe(text):
    """Escape XML special chars for reportlab Paragraph markup."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_channel_pdf(channel, content_type, videos_with_data):
    """
    Build a PDF containing all transcripts or summaries for a channel.

    Args:
        channel: Channel model instance.
        content_type: "transcript" or "summary".
        videos_with_data: list of (video, data) tuples where data is
            a transcript dict (with "segments") or a summary string.

    Returns:
        A BytesIO buffer containing the generated PDF.
    """
    _register_unicode_fonts()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName=_FONT_NAME_BOLD,
        fontSize=24,
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor="#666666",
    )
    heading_style = ParagraphStyle(
        "VideoHeading",
        parent=styles["Heading2"],
        fontName=_FONT_NAME_BOLD,
        fontSize=14,
        spaceAfter=4,
        spaceBefore=0,
    )
    meta_style = ParagraphStyle(
        "VideoMeta",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=9,
        textColor="#888888",
        spaceAfter=12,
    )
    segment_style = ParagraphStyle(
        "Segment",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    timestamp_style = ParagraphStyle(
        "Timestamp",
        parent=styles["Normal"],
        fontName=_FONT_NAME_BOLD,
        fontSize=9,
        textColor="#0066CC",
        spaceAfter=2,
    )
    summary_style = ParagraphStyle(
        "SummaryBody",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=10,
        leading=15,
        spaceAfter=6,
    )

    story = []

    # --- Cover page ---
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(_safe(channel.title or channel.youtube_channel_id), title_style))
    story.append(Spacer(1, 0.5 * cm))

    label = "Transcripts" if content_type == "transcript" else "Summaries"
    story.append(Paragraph(f"All {label}", subtitle_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        f"{len(videos_with_data)} video(s) &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        subtitle_style,
    ))
    story.append(PageBreak())

    # --- Per-video content ---
    for idx, (video, data) in enumerate(videos_with_data):
        video_title = video.title or video.youtube_video_id
        story.append(Paragraph(_safe(video_title), heading_style))

        meta_parts = []
        if video.published_at:
            meta_parts.append(f"Published: {video.published_at.strftime('%Y-%m-%d')}")
        if video.duration_sec:
            meta_parts.append(f"Duration: {_format_timestamp(video.duration_sec)}")
        if meta_parts:
            story.append(Paragraph(" &middot; ".join(meta_parts), meta_style))

        if content_type == "transcript":
            segments = data.get("segments", []) if isinstance(data, dict) else []
            for seg in segments:
                ts = _format_timestamp(seg.get("start", 0))
                story.append(Paragraph(f"[{ts}]", timestamp_style))
                story.append(Paragraph(_safe(seg.get("text", "")), segment_style))
            if not segments:
                story.append(Paragraph("<i>No transcript segments found.</i>", segment_style))
        else:
            for line in str(data).split("\n"):
                line = line.strip()
                if line:
                    story.append(Paragraph(_safe(line), summary_style))
                else:
                    story.append(Spacer(1, 0.3 * cm))

        if idx < len(videos_with_data) - 1:
            story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return buf
