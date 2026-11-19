import unittest

from playhouse.sqlite_ext import SqliteExtDatabase

from frigate.jobs.debug_replay import query_recordings
from frigate.models import Recordings


class TestRecordingRangeQuery(unittest.TestCase):
    def setUp(self):
        self.db = SqliteExtDatabase(":memory:")
        self.db.bind([Recordings])
        self.db.create_tables([Recordings])

    def add(self, name, start, end, camera="cam"):
        Recordings.create(
            id=name,
            camera=camera,
            path=f"/{name}.mp4",
            start_time=start,
            end_time=end,
            duration=end - start,
            segment_size=1,
        )

    def test_finds_every_overlapping_segment_and_nothing_else(self):
        self.add("long_ago", 100, 110)
        self.add("just_before", 980, 990)
        self.add("spans_start", 995, 1005)
        self.add("inside", 1005, 1015)
        self.add("spans_end", 1025, 1035)
        self.add("after", 1040, 1050)
        self.add("other_camera", 1005, 1015, camera="other")
        # longest segment the maintainer keeps, starting just inside the bound
        self.add("longest", 1000 - 599, 1001)

        found = [r.path for r in query_recordings("cam", 1000, 1030)]

        self.assertEqual(
            found,
            ["/longest.mp4", "/spans_start.mp4", "/inside.mp4", "/spans_end.mp4"],
        )


if __name__ == "__main__":
    unittest.main()
