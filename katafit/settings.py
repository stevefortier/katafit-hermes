"""Profile-local secrets, never in model messages, argv or config.yaml."""
import os
import re
import stat
import secrets
from contextlib import contextmanager

TOKEN_PATTERN = re.compile(r'rgn_coach_[0-9a-f]{24}_[A-Za-z0-9_-]{43}\Z')


class Settings:
    def __init__(self, ctx, home):
        self.ctx = ctx
        self.directory = home / 'katafit-private'

    @contextmanager
    def private_dir(self):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise PermissionError('PRIVATE_DIRECTORY_REQUIRED')
            yield fd
        finally:
            os.close(fd)

    def token(self):
        if not self.directory.exists() and not self.directory.is_symlink():
            return None
        with self.private_dir() as directory:
            try:
                fd = os.open('credential', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                return None
            with os.fdopen(fd, 'r') as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise PermissionError('PRIVATE_CREDENTIAL_REQUIRED')
                value = handle.read(256)
                if not TOKEN_PATTERN.fullmatch(value):
                    raise ValueError('CREDENTIAL_FORMAT_INVALID')
                return value

    def configure(self, token):
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise ValueError('CREDENTIAL_FORMAT_INVALID')
        with self.private_dir() as directory:
            name = '.credential-' + secrets.token_hex(8)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'w') as handle:
                    handle.write(token)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(name, 'credential', src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
        self.ctx.set_config('configured', True)
