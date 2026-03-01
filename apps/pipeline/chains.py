from celery import chain


def build_minimal_transcribe_summarize_pipeline(job_id: str, video_id: str) -> chain:
    """
    Minimal pipeline for single-video testing:
      download → transcribe → summarize → embed → upsert to Pinecone.

    Covers the full transcript-to-vector path for production smoke tests.
    The upsert task marks the job as succeeded when it completes.
    """
    from apps.pipeline.tasks.download import download_audio
    from apps.pipeline.tasks.transcribe import transcribe_audio
    from apps.pipeline.tasks.summarize import summarize_video
    from apps.pipeline.tasks.embed import embed_chunks
    from apps.pipeline.tasks.upsert import upsert_to_pinecone

    return chain(
        download_audio.si(job_id, video_id),
        transcribe_audio.si(job_id, video_id),
        summarize_video.si(job_id, video_id),
        embed_chunks.si(job_id, video_id),
        upsert_to_pinecone.si(job_id, video_id),
    )


def build_summarize_only_pipeline(job_id: str, video_id: str) -> chain:
    """
    Pipeline for summarizing already-transcribed videos whose local data
    was cleaned up after the original pipeline run:
      restore transcript from GCS → summarize → embed → upsert.
    """
    from apps.pipeline.tasks.restore_transcript import restore_transcript
    from apps.pipeline.tasks.summarize import summarize_video
    from apps.pipeline.tasks.embed import embed_chunks
    from apps.pipeline.tasks.upsert import upsert_to_pinecone

    return chain(
        restore_transcript.si(job_id, video_id),
        summarize_video.si(job_id, video_id),
        embed_chunks.si(job_id, video_id),
        upsert_to_pinecone.si(job_id, video_id),
    )


def build_video_pipeline(job_id: str, video_id: str, summarize: bool = False) -> chain:
    """
    Assemble a Celery chain for the full video processing pipeline.

    Uses si() (immutable signatures) throughout — tasks do NOT pass return
    values to each other. All inter-task communication is via the DB and
    /data filesystem.

    summarize=True conditionally inserts Stage F (Gemini summary).
    """
    from apps.pipeline.tasks.download import download_audio
    from apps.pipeline.tasks.transcribe import transcribe_audio
    from apps.pipeline.tasks.upload import upload_artifacts
    from apps.pipeline.tasks.categorize import auto_categorize
    from apps.pipeline.tasks.summarize import summarize_video
    from apps.pipeline.tasks.embed import embed_chunks
    from apps.pipeline.tasks.upsert import upsert_to_pinecone

    tasks = [
        download_audio.si(job_id, video_id),
        transcribe_audio.si(job_id, video_id),
        upload_artifacts.si(job_id, video_id),
        auto_categorize.si(job_id, video_id),
    ]

    if summarize:
        tasks.append(summarize_video.si(job_id, video_id))

    tasks.extend([
        embed_chunks.si(job_id, video_id),
        upsert_to_pinecone.si(job_id, video_id),
    ])

    return chain(*tasks)
