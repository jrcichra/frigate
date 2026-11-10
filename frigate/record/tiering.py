"""Tier recordings and exports to S3 compatible storage.

Local disk stays the source of truth for new data. Finished files are copied to
S3 and the object key is saved on the row once the size is verified. When
local_max_gb is set, the oldest files that are already in S3 are removed from
local disk and played back from S3 over HTTP.
"""

import logging
import os
import threading
import time
import urllib.request
from collections.abc import Iterator
from multiprocessing.synchronize import Event as MpEvent
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from peewee import fn

from frigate.const import RECORD_DIR
from frigate.models import Export, Recordings

if TYPE_CHECKING:
    from frigate.config import FrigateConfig, TieringConfig

logger = logging.getLogger(__name__)

# seconds between passes
UPLOAD_INTERVAL = 60
# only upload segments that finished at least this long ago so that files
# still being read by the UI or by exports are left alone
MIN_AGE_SECONDS = 600
# rows handled per pass; a backlog drains over several passes
BATCH_SIZE = 500


def recording_key(path: str) -> str:
    """Object key of a recording segment, relative to the recordings directory."""
    return os.path.relpath(path, RECORD_DIR)


def export_key(path: str) -> str:
    """Object key of an export, the file name."""
    return os.path.basename(path)


def reads_from_s3(tiering: "TieringConfig") -> bool:
    """Whether files that are not on local disk can be read back from S3."""
    return bool(tiering.enabled and tiering.read_url)


def object_url(tiering: "TieringConfig", bucket: str, key: str) -> str:
    """HTTP URL that serves an object with range request support."""
    return f"{str(tiering.read_url).rstrip('/')}/{bucket}/{quote(key)}"


def recording_source(path: str, tiering: "TieringConfig") -> str:
    """Local path of a recording, or the URL of its S3 copy once it was evicted."""
    if reads_from_s3(tiering) and not os.path.exists(path):
        return object_url(tiering, tiering.recordings_bucket, recording_key(path))

    return path


def export_source(path: str, tiering: "TieringConfig") -> str:
    """Local path of an export, or the URL of its S3 copy once it was evicted."""
    if reads_from_s3(tiering) and not os.path.exists(path):
        return object_url(tiering, tiering.exports_bucket, export_key(path))

    return path


def vod_source(path: str, tiering: "TieringConfig") -> dict[str, str]:
    """Source fields for an nginx-vod clip.

    Once nginx has a remote upstream the clip source type defaults to http, so
    local files must be marked as files explicitly.
    """
    if not reads_from_s3(tiering):
        return {"path": path}

    if os.path.exists(path):
        return {"path": path, "sourceType": "file"}

    return {
        "path": f"/{tiering.recordings_bucket}/{quote(recording_key(path))}",
        "sourceType": "http",
    }


def stream_export(path: str, tiering: "TieringConfig") -> Iterator[bytes] | None:
    """Stream an export from local disk or S3, None when it is not available."""
    source = export_source(path, tiering)

    if source == path:
        if not os.path.exists(path):
            return None

        return _read_chunks(open(path, "rb"))

    try:
        return _read_chunks(urllib.request.urlopen(source, timeout=30))
    except OSError:
        logger.warning("Unable to read export %s from S3", os.path.basename(path))
        return None


def _read_chunks(stream: Any, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with stream:
        while chunk := stream.read(chunk_size):
            yield chunk


def create_client(tiering: "TieringConfig") -> Any:
    """Create an S3 client for the configured endpoint."""
    # imported here so boto3 is only loaded when tiering is enabled
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=tiering.endpoint,
        region_name=tiering.region,
        aws_access_key_id=tiering.access_key,
        aws_secret_access_key=tiering.secret_key,
        # SeaweedFS and most self hosted servers want path style buckets
        config=Config(s3={"addressing_style": "path"}),
    )


def delete_export_object(tiering: "TieringConfig", s3_key: str | None) -> None:
    """Delete the S3 copy of an export, called when the export is deleted."""
    if not tiering.enabled or not s3_key:
        return

    from botocore.exceptions import BotoCoreError, ClientError

    try:
        create_client(tiering).delete_object(Bucket=tiering.exports_bucket, Key=s3_key)
    except (BotoCoreError, ClientError):
        logger.warning("Unable to delete export %s from S3", s3_key)


class RecordingTiering(threading.Thread):
    """Upload recordings and exports to S3 and evict old local copies.

    Local files are only removed after the S3 copy was verified, so S3 being
    down only delays uploads.
    """

    def __init__(
        self, config: "FrigateConfig", stop_event: MpEvent, client: Any = None
    ) -> None:
        super().__init__(name="recording_tiering")
        self.config = config.tiering
        self.stop_event = stop_event
        self.client = client

    def run(self) -> None:
        if self.client is None:
            self.client = create_client(self.config)

        while not self.stop_event.wait(UPLOAD_INTERVAL):
            # background task, a failed pass must not stop the next one
            try:
                self.upload_pending()
                self.upload_exports()
                self.evict_recordings()
                self.evict_exports()
            except Exception:
                logger.exception("Recording tiering pass failed")

        logger.info("Exiting recording tiering...")

    def _upload(self, bucket: str, path: str, key: str) -> bool:
        """Upload a file and verify the object size, False to skip this file.

        Raises the S3 error when S3 is unreachable so the caller can stop the pass.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            # expired by retention between the query and now
            return False

        try:
            self.client.upload_file(path, bucket, key)
            remote = self.client.head_object(Bucket=bucket, Key=key)
        except FileNotFoundError:
            return False
        except (BotoCoreError, ClientError):
            # S3 is unreachable or rejecting us, retry on the next pass
            logger.warning("Unable to upload to S3 bucket %s", bucket)
            raise

        if remote["ContentLength"] != size:
            logger.warning("Uploaded size mismatch for %s", key)
            return False

        return True

    def upload_pending(self) -> int:
        """Upload one batch of recording segments, returns the number uploaded."""
        from botocore.exceptions import BotoCoreError, ClientError

        now = time.time()
        conditions = [
            Recordings.s3_key.is_null(),
            Recordings.evicted == False,
            Recordings.end_time < now - MIN_AGE_SECONDS,
        ]

        if self.config.backfill_hours:
            conditions.append(
                Recordings.end_time > now - self.config.backfill_hours * 3600
            )

        pending = (
            Recordings.select(Recordings.id, Recordings.path)
            .where(*conditions)
            .order_by(Recordings.start_time)
            .limit(BATCH_SIZE)
            .namedtuples()
        )
        uploaded = 0

        for recording in pending:
            if self.stop_event.is_set():
                break

            key = recording_key(recording.path)

            try:
                if not self._upload(self.config.recordings_bucket, recording.path, key):
                    continue
            except (BotoCoreError, ClientError):
                break

            Recordings.update(s3_key=key).where(Recordings.id == recording.id).execute()
            uploaded += 1

        if uploaded:
            logger.debug("Uploaded %s recording segments to S3", uploaded)

        return uploaded

    def upload_exports(self) -> int:
        """Upload finished exports, returns the number uploaded."""
        from botocore.exceptions import BotoCoreError, ClientError

        pending = (
            Export.select(Export.id, Export.video_path)
            .where(Export.in_progress == False, Export.s3_key.is_null())
            .limit(BATCH_SIZE)
            .namedtuples()
        )
        uploaded = 0

        for export in pending:
            if self.stop_event.is_set():
                break

            key = export_key(export.video_path)

            try:
                if not self._upload(self.config.exports_bucket, export.video_path, key):
                    continue
            except (BotoCoreError, ClientError):
                break

            Export.update(s3_key=key).where(Export.id == export.id).execute()
            uploaded += 1

        if uploaded:
            logger.debug("Uploaded %s exports to S3", uploaded)

        return uploaded

    def evict_recordings(self) -> int:
        """Remove the oldest mirrored segments from local disk above the limit."""
        if not self.config.local_max_gb:
            return 0

        local_mb = (
            Recordings.select(fn.COALESCE(fn.SUM(Recordings.segment_size), 0))
            .where(Recordings.evicted == False)
            .scalar()
        )
        excess_mb = local_mb - self.config.local_max_gb * 1024
        evicted = 0

        while excess_mb > 0 and not self.stop_event.is_set():
            batch = list(
                Recordings.select(
                    Recordings.id, Recordings.path, Recordings.segment_size
                )
                .where(
                    Recordings.s3_key.is_null(False),
                    Recordings.evicted == False,
                )
                .order_by(Recordings.start_time)
                .limit(BATCH_SIZE)
                .namedtuples()
            )

            if not batch:
                logger.warning(
                    "Local recordings are over the limit but nothing is uploaded yet"
                )
                break

            for recording in batch:
                Path(recording.path).unlink(missing_ok=True)
                Recordings.update(evicted=True).where(
                    Recordings.id == recording.id
                ).execute()
                excess_mb -= recording.segment_size
                evicted += 1

                if excess_mb <= 0:
                    break

        if evicted:
            logger.debug("Evicted %s recording segments from local disk", evicted)

        return evicted

    def evict_exports(self) -> int:
        """Remove uploaded exports from local disk."""
        if not self.config.local_max_gb:
            return 0

        uploaded = list(
            Export.select(Export.id, Export.video_path)
            .where(Export.s3_key.is_null(False), Export.evicted == False)
            .namedtuples()
        )

        for export in uploaded:
            Path(export.video_path).unlink(missing_ok=True)
            Export.update(evicted=True).where(Export.id == export.id).execute()

        if uploaded:
            logger.debug("Evicted %s exports from local disk", len(uploaded))

        return len(uploaded)
