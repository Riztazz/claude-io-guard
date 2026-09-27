"""A temporary project folder for a test: files written as bytes, and git when the test asks for it."""
import shutil
import subprocess
import tempfile
from pathlib import Path


class TemporaryProject:
    """A folder under the system temp directory, removed when the with-block ends.

    Files are given as {relative path: bytes}. With git=True the folder is a repository whose files are
    committed, with autocrlf off so the committed bytes are the given bytes.
    """

    def __init__(self, files: dict[str, bytes] | None = None, git: bool = False) -> None:
        self.files = files or {}
        self.git = git
        self.root: Path | None = None

    def __enter__(self) -> Path:
        self.root = Path(tempfile.mkdtemp(prefix="ioguard-test-")).resolve()
        for rel, data in self.files.items():
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if self.git:
            self.run_git("init", "-q", "-b", "main")
            self.run_git("config", "core.autocrlf", "false")
            self.run_git("add", "-A")
            self.run_git("-c", "user.name=io-guard test", "-c", "user.email=test@localhost",
                         "commit", "-q", "--allow-empty", "-m", "fixture")
        return self.root

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def run_git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=self.root, check=True,
                       capture_output=True, timeout=60)
