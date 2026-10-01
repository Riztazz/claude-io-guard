"""One simple command's writes are read on their own, in the folder it runs in."""
import unittest
from pathlib import Path

from ioguard.lib import shell, writes
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform

WINDOWS = Platform("win32", True)
CWD = Path("C:/project")
HOST = writes.Host(WINDOWS, {}, FakeFs({}))


def first(command: str) -> shell.SimpleCommand:
    return shell.commands(command)[0]


class OneCommandsWrites(unittest.TestCase):
    def test_each_shape_of_a_write_is_read_from_one_command(self):
        cases = {"sed -i s/a/b/ f.txt": [writes.Write("f.txt", "sed -i", CWD)],
                 "find src -exec sed -i s/a/b/ {} ;": [writes.Write("src", "sed -i under find -exec", CWD)],
                 "tee a.log b.log": [writes.Write("a.log", "tee", CWD), writes.Write("b.log", "tee", CWD)],
                 "echo x > out.txt": [writes.Write("out.txt", "a > redirect", CWD)],
                 "bash -c 'echo x > inner.txt'": [writes.Write("inner.txt", "a > redirect", CWD)],
                 "ls -la": []}
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(writes.command_writes(first(command), CWD, CWD, HOST, 0), expected,
                                 "a simple command's writes need no other command around it")


class AWholeCommandsWrites(unittest.TestCase):
    def test_a_python_c_body_names_each_target_once(self):
        found = writes.bash_writes("""python -c "open('a.txt', 'w').write('x')\"""", CWD, HOST, scripts=[])
        self.assertEqual(found, [writes.Write("a.txt", "a script body", CWD)],
                         "the body is read by its program and by the scan, and its target is one write")


if __name__ == "__main__":
    unittest.main()
