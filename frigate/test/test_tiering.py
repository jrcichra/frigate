import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from playhouse.sqlite_ext import SqliteExtDatabase

from frigate.models import Export, ExportCase, Recordings
from frigate.record.tiering import (
    RecordingTiering,
    export_source,
    recording_source,
    stream_export,
    vod_source,
)


class FakeS3:
    def __init__(self, fail=False, wrong_size=False):
        self.objects = {}
        self.fail = fail
        self.wrong_size = wrong_size

    def upload_file(self, path, bucket, key):
        if self.fail:
            raise EndpointConnectionError(endpoint_url="http://s3")

        self.objects[(bucket, key)] = os.path.getsize(path)

    def head_object(self, Bucket, Key):
        size = self.objects[(Bucket, Key)]
        return {"ContentLength": size + 1 if self.wrong_size else size}


class TestRecordingTiering(unittest.TestCase):
    def setUp(self):
        self.db = SqliteExtDatabase(":memory:")
        self.db.bind([Recordings, Export, ExportCase])
        self.db.create_tables([Recordings, Export, ExportCase])
        self.record_dir = tempfile.mkdtemp()
        patcher = patch("frigate.record.tiering.RECORD_DIR", self.record_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = SimpleNamespace(
            tiering=SimpleNamespace(
                enabled=True,
                recordings_bucket="recs",
                exports_bucket="exps",
                read_url="http://filer:8888/buckets",
                backfill_hours=None,
                local_max_gb=None,
            ),
        )

    def add_recording(self, name, age_seconds, size_mb=1.0):
        path = os.path.join(self.record_dir, "2026-01-01", "00", "cam", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * 100)

        end = time.time() - age_seconds
        Recordings.create(
            id=name,
            camera="cam",
            path=path,
            start_time=end - 10,
            end_time=end,
            duration=10,
            segment_size=size_mb,
        )
        return path

    def add_export(self, name, in_progress=False):
        path = os.path.join(self.record_dir, name)
        with open(path, "wb") as f:
            f.write(b"x" * 100)

        Export.create(
            id=name,
            camera="cam",
            name=name,
            date=time.time(),
            video_path=path,
            thumb_path=path + ".jpg",
            in_progress=in_progress,
        )
        return path

    def tiering(self, client):
        return RecordingTiering(self.config, threading.Event(), client)

    def test_uploads_old_segments_and_marks_key(self):
        path = self.add_recording("a.mp4", 3600)
        client = FakeS3()

        self.assertEqual(self.tiering(client).upload_pending(), 1)

        key = os.path.relpath(path, self.record_dir)
        self.assertEqual(Recordings.get_by_id("a.mp4").s3_key, key)
        self.assertIn(("recs", key), client.objects)
        self.assertTrue(os.path.exists(path))

    def test_skips_recent_and_already_uploaded_segments(self):
        self.add_recording("new.mp4", 10)
        self.add_recording("done.mp4", 3600)
        Recordings.update(s3_key="done").where(Recordings.id == "done.mp4").execute()
        client = FakeS3()

        self.assertEqual(self.tiering(client).upload_pending(), 0)
        self.assertEqual(client.objects, {})

    def test_backfill_hours_ignores_older_segments(self):
        self.add_recording("old.mp4", 5 * 3600)
        self.add_recording("recent.mp4", 3600)
        self.config.tiering.backfill_hours = 2
        client = FakeS3()

        self.assertEqual(self.tiering(client).upload_pending(), 1)
        self.assertIsNone(Recordings.get_by_id("old.mp4").s3_key)
        self.assertIsNotNone(Recordings.get_by_id("recent.mp4").s3_key)

    def test_s3_down_leaves_rows_untouched(self):
        self.add_recording("a.mp4", 3600)

        self.assertEqual(self.tiering(FakeS3(fail=True)).upload_pending(), 0)
        self.assertIsNone(Recordings.get_by_id("a.mp4").s3_key)

    def test_size_mismatch_is_not_marked(self):
        self.add_recording("a.mp4", 3600)

        self.assertEqual(self.tiering(FakeS3(wrong_size=True)).upload_pending(), 0)
        self.assertIsNone(Recordings.get_by_id("a.mp4").s3_key)

    def test_missing_local_file_is_skipped(self):
        path = self.add_recording("gone.mp4", 3600)
        self.add_recording("ok.mp4", 3500)
        os.remove(path)

        self.assertEqual(self.tiering(FakeS3()).upload_pending(), 1)
        self.assertIsNone(Recordings.get_by_id("gone.mp4").s3_key)
        self.assertIsNotNone(Recordings.get_by_id("ok.mp4").s3_key)

    def test_uploads_finished_exports_only(self):
        path = self.add_export("done.mp4")
        self.add_export("busy.mp4", in_progress=True)
        client = FakeS3()

        self.assertEqual(self.tiering(client).upload_exports(), 1)
        self.assertEqual(Export.get_by_id("done.mp4").s3_key, "done.mp4")
        self.assertIsNone(Export.get_by_id("busy.mp4").s3_key)
        self.assertIn(("exps", "done.mp4"), client.objects)
        self.assertTrue(os.path.exists(path))

    def test_no_eviction_without_local_max_gb(self):
        path = self.add_recording("a.mp4", 3600, size_mb=5000)
        Recordings.update(s3_key="a").execute()

        self.assertEqual(self.tiering(FakeS3()).evict_recordings(), 0)
        self.assertTrue(os.path.exists(path))

    def test_evicts_oldest_mirrored_segments_down_to_the_limit(self):
        old = self.add_recording("old.mp4", 7200, size_mb=600)
        mid = self.add_recording("mid.mp4", 3600, size_mb=600)
        new = self.add_recording("new.mp4", 1800, size_mb=600)
        Recordings.update(s3_key="k").execute()
        # 1800 MB local against a 1024 MB limit: dropping the oldest leaves 1200 MB,
        # still over, so the next one goes too and only the newest stays
        self.config.tiering.local_max_gb = 1

        self.assertEqual(self.tiering(FakeS3()).evict_recordings(), 2)
        self.assertFalse(os.path.exists(old))
        self.assertFalse(os.path.exists(mid))
        self.assertTrue(os.path.exists(new))
        self.assertTrue(Recordings.get_by_id("old.mp4").evicted)
        self.assertTrue(Recordings.get_by_id("mid.mp4").evicted)
        self.assertFalse(Recordings.get_by_id("new.mp4").evicted)

    def test_never_evicts_segments_that_are_not_in_s3(self):
        local = self.add_recording("local.mp4", 7200, size_mb=2000)
        self.config.tiering.local_max_gb = 1

        self.assertEqual(self.tiering(FakeS3()).evict_recordings(), 0)
        self.assertTrue(os.path.exists(local))
        self.assertFalse(Recordings.get_by_id("local.mp4").evicted)

    def test_evicted_segments_are_not_uploaded_again(self):
        self.add_recording("a.mp4", 3600)
        Recordings.update(evicted=True).execute()

        self.assertEqual(self.tiering(FakeS3()).upload_pending(), 0)

    def test_evicts_uploaded_exports(self):
        done = self.add_export("done.mp4")
        pending = self.add_export("pending.mp4")
        Export.update(s3_key="done.mp4").where(Export.id == "done.mp4").execute()
        self.config.tiering.local_max_gb = 1

        self.assertEqual(self.tiering(FakeS3()).evict_exports(), 1)
        self.assertFalse(os.path.exists(done))
        self.assertTrue(os.path.exists(pending))
        self.assertTrue(Export.get_by_id("done.mp4").evicted)

    def test_sources_prefer_local_files_and_fall_back_to_s3(self):
        local = self.add_recording("here.mp4", 3600)
        gone = os.path.join(self.record_dir, "2026-01-01", "00", "cam", "gone.mp4")
        tiering = self.config.tiering

        self.assertEqual(recording_source(local, tiering), local)
        self.assertEqual(
            recording_source(gone, tiering),
            "http://filer:8888/buckets/recs/2026-01-01/00/cam/gone.mp4",
        )
        self.assertEqual(
            export_source("/media/frigate/exports/x.mp4", tiering),
            "http://filer:8888/buckets/exps/x.mp4",
        )
        self.assertEqual(
            vod_source(local, tiering), {"path": local, "sourceType": "file"}
        )
        self.assertEqual(
            vod_source(gone, tiering),
            {"path": "/recs/2026-01-01/00/cam/gone.mp4", "sourceType": "http"},
        )

    def test_sources_are_plain_paths_when_not_reading_from_s3(self):
        gone = os.path.join(self.record_dir, "gone.mp4")
        tiering = self.config.tiering
        tiering.read_url = None

        self.assertEqual(recording_source(gone, tiering), gone)
        self.assertEqual(vod_source(gone, tiering), {"path": gone})

    def test_stream_export_reads_local_files_and_reports_missing_ones(self):
        path = self.add_export("here.mp4")
        tiering = self.config.tiering
        tiering.read_url = None

        self.assertEqual(b"".join(stream_export(path, tiering)), b"x" * 100)
        self.assertIsNone(stream_export(path + ".missing", tiering))


if __name__ == "__main__":
    unittest.main()
