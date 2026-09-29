"""A snapshot keeps files' bytes under a tag for seven days, is found by its id or by its newest tag in the
project, and says which files a restore would replace."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard.lib import snapshots

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
PROJECT = Path("C:/project")
A, B = PROJECT / "a.txt", PROJECT / "B.txt"


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-snapshots-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def taken(self, tag: str = "pass", when: datetime = NOW, project: Path = PROJECT):
        return snapshots.take(self.home, tag, project, [(A, b"one\r\n"), (B, b"\xef\xbb\xbftwo\n")], when)


class ASnapshotKeepsBytes(SnapshotTest):
    def test_each_file_comes_back_byte_for_byte(self):
        kept = self.taken()
        found = snapshots.find(self.home, kept.id, PROJECT, NOW)
        self.assertEqual([found.blob(each) for each in found.files], [b"one\r\n", b"\xef\xbb\xbftwo\n"],
                         "the blobs hold the files' bytes, CRLF and BOM included")
        self.assertEqual(found.expires - found.created, timedelta(days=7), "a snapshot lasts seven days")

    def test_a_tag_finds_the_newest_snapshot_in_the_same_project(self):
        self.taken(when=NOW)
        newer = self.taken(when=NOW + timedelta(minutes=5))
        self.taken(when=NOW + timedelta(minutes=9), project=Path("C:/other"))
        self.assertEqual(snapshots.find(self.home, "pass", PROJECT, NOW + timedelta(hours=1)).id, newer.id,
                         "a tag names the newest live snapshot with it in this project, never another's")

    def test_an_expired_snapshot_is_not_found_and_sweep_deletes_it(self):
        kept = self.taken()
        later = NOW + timedelta(days=7, seconds=1)
        self.assertIsNone(snapshots.find(self.home, kept.id, PROJECT, later), "past seven days it is gone")
        self.assertEqual((snapshots.sweep(self.home, later), kept.folder.exists()), (1, False),
                         "sweep deletes the expired snapshot's folder")

    def test_sweep_deletes_a_snapshot_cut_short_once_it_is_a_day_old(self):
        old, new = self.taken(), self.taken()
        for kept in (old, new):
            (kept.folder / snapshots.MANIFEST).unlink()
        stamp = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
        for path in (old.folder, *old.folder.iterdir()):
            os.utime(path, (stamp, stamp))
        snapshots.sweep(self.home, datetime.now(timezone.utc))
        self.assertEqual((old.folder.exists(), new.folder.exists()), (False, True),
                         "a folder with no manifest is a crash's leftover, gone after a day, and a fresh one "
                         "may still be being written")

    def test_a_snapshot_with_no_manifest_is_never_found(self):
        kept = self.taken()
        (kept.folder / snapshots.MANIFEST).unlink()
        self.assertIsNone(snapshots.find(self.home, kept.id, PROJECT, NOW),
                          "a snapshot cut short before its manifest was written does not exist")


class APendingRestoreNamesWhatItReplaces(SnapshotTest):
    def test_changed_same_and_unknown_files_are_told_apart(self):
        kept = self.taken()
        now = {A: b"one\r\nmore\r\n", B: b"\xef\xbb\xbftwo\n"}
        plan = snapshots.pending(kept, [A, B, PROJECT / "c.txt"], now.get, case_insensitive=False)
        self.assertEqual(([each.path for each in plan.changed], [each.path for each in plan.same],
                          list(plan.unknown)), ([A], [B], [PROJECT / "c.txt"]),
                         "only a file whose bytes differ is replaced, and a path it never kept is named")

    def test_a_file_that_is_gone_counts_as_changed(self):
        plan = snapshots.pending(self.taken(), None, {B: b"\xef\xbb\xbftwo\n"}.get, case_insensitive=False)
        self.assertEqual([each.path for each in plan.changed], [A], "a deleted file is written back too")

    def test_paths_compare_without_case_where_the_file_system_ignores_it(self):
        kept = self.taken()
        plan = snapshots.pending(kept, [PROJECT / "b.TXT"], {}.get, case_insensitive=True)
        self.assertEqual(([each.path for each in plan.changed], plan.unknown), ([B], ()),
                         "on Windows b.TXT and B.txt are one file")

    def test_the_key_names_the_snapshot_and_the_files_it_would_replace(self):
        kept = self.taken()
        first = snapshots.pending(kept, None, {}.get, case_insensitive=False).key()
        only_a = snapshots.pending(kept, [A], {}.get, case_insensitive=False).key()
        self.assertTrue(first.startswith(kept.id) and first != only_a,
                        "a restore of other files is another question for the user")


if __name__ == "__main__":
    unittest.main()
