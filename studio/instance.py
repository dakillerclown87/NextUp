"""Hold an OS lock before opening or recovering application databases."""

import os


class InstanceLock:
    def __init__(self, home):
        self.home = home
        self.file = None

    def __enter__(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.file = (self.home / "instance.lock").open("a+b")
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError(
                "NextUp is already running. Use its existing window or stop it first."
            ) from None
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()
