"""Shared gateway/diagnostic worker ownership; no polling during discovery or setup."""
import asyncio
import fcntl
import getpass
import json
import os
import signal
import stat
import sys
import time
import warnings
from contextlib import contextmanager

from .settings import Settings
from .worker import Worker


class App:
    def __init__(self, ctx, home):
        self.ctx = ctx
        self.settings = Settings(ctx, home)
        self.task = None

    @contextmanager
    def worker_lock(self):
        with self.settings.private_dir() as directory:
            fd = os.open('worker.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                    raise PermissionError('PRIVATE_LOCK_REQUIRED')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('WORKER_ALREADY_RUNNING_STOP_BEFORE_CONFIGURE') from None
                yield
            finally:
                os.close(fd)

    def configure(self, stream=None):
        # Check ownership before prompting; never silently rotate a running worker's token.
        with self.worker_lock():
            if stream is not None:
                value = stream.read(256)
                if value.endswith('\n'):
                    value = value[:-1]
                    if value.endswith('\r'):
                        value = value[:-1]
            else:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', getpass.GetPassWarning)
                    value = getpass.getpass('Kata.fit one-time Coach credential (hidden): ')
            self.settings.configure(value)
            # Use the supported host CLI, including managed-key policy and atomic persistence.
            # Pin the child to this App's profile, not a later process-global HOME change.
            import subprocess
            subprocess.run([sys.executable, '-m', 'hermes_cli.main', 'config', 'set',
                            'platforms.katafit.enabled', 'true'],
                           env={**os.environ, 'HERMES_HOME': str(self.settings.directory.parent)},
                           check=True, capture_output=True, timeout=30)
            self.ctx.state.set('worker', {})
        print('Credential saved privately for this Hermes profile. Connectivity is not yet verified.\n'
              'Gateway adapter enabled. Existing gateway: hermes gateway restart\n'
              'No gateway service yet: hermes gateway install, then hermes gateway start\n'
              'Use the same Hermes profile for every command. Configure never restarts it automatically.\n'
              'Then use Test connection in Kata.fit to verify an attributed reply.')

    def status(self):
        configured = self.settings.token() is not None
        running = False
        if self.settings.directory.exists():
            try:
                with self.worker_lock():
                    pass
            except RuntimeError:
                running = True
        latest = self.ctx.state.get('worker', {}) if configured else {}
        fresh = running and 0 <= time.time() - latest.get('updated_at', 0) < 90
        return {'profile_home': str(self.settings.directory.parent.resolve()),
                'mode': latest.get('mode', 'unknown') if fresh else 'unknown',
                'configuration': 'configured' if configured else 'setup-required',
                'worker': 'running' if running else 'stopped',
                'connectivity': latest.get('connectivity', 'unknown') if fresh else 'unknown',
                'activity': latest.get('activity', 'unknown') if fresh else 'unknown',
                'reply_verified': False,
                'verification': 'Use Kata.fit Test connection: exact completed attributed request required.'}

    def start(self, *, mode):
        """Acquire ownership synchronously before reporting a live worker."""
        if self.task is not None:
            raise RuntimeError('WORKER_ALREADY_RUNNING_STOP_BEFORE_CONFIGURE')
        lock = self.worker_lock()
        lock.__enter__()
        try:
            token = self.settings.token()
            if token is None:
                lock.__exit__(None, None, None)
                return False
            state = {'connectivity': 'unknown', 'activity': 'starting', 'mode': mode}
            def on_state(value):
                if value in ('connected', 'idle', 'working', 'reply-submitted'):
                    state['connectivity'] = 'connected'
                elif value == 'auth-rejected':
                    state['connectivity'] = 'auth-rejected'
                elif value == 'backoff':
                    state['connectivity'] = 'unknown'
                state.update(activity=value, updated_at=time.time())
                self.ctx.state.set('worker', dict(state))
            on_state('starting')
            worker = Worker(token, self.ctx.llm.acomplete, on_state=on_state)
            self.task = self.ctx.spawn_task(worker.run(), name='katafit-coach-worker')
        except BaseException:
            lock.__exit__(None, None, None)
            raise
        def finished(task):
            try:
                if not task.cancelled():
                    task.exception()  # Consume without exposing private exception text.
                self.ctx.state.set('worker', {'activity': 'stopped', 'connectivity': 'unknown',
                                             'updated_at': time.time()})
            finally:
                self.task = None
                lock.__exit__(None, None, None)
        self.task.add_done_callback(finished)
        return True

    async def stop(self):
        task = self.task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def run(self):
        if not self.start(mode='foreground'):
            print('Setup required. Run: hermes katafit configure')
            return
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self.task.cancel)
        print('Kata.fit diagnostic worker running. Ctrl-C stops it; do not also start the gateway.', flush=True)
        try:
            await self.task
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
            await self.stop()

    def unload(self):
        if self.task is not None:
            self.task.cancel()

    def dispatch(self, args):
        try:
            if args.katafit_action == 'configure':
                self.configure(sys.stdin if args.token_stdin else None)
            elif args.katafit_action == 'status':
                print(json.dumps(self.status(), indent=2))
            elif args.katafit_action == 'run':
                try:
                    asyncio.run(self.run())
                except (KeyboardInterrupt, asyncio.CancelledError):
                    print('Kata.fit worker stopped.')
        except Exception:
            # Never print exception text: libraries can embed headers, tokens or private payloads.
            print('Kata.fit command could not complete. Check private file permissions, credential format, '
                  'and stop any running Kata.fit worker before configuring.', file=sys.stderr)
            raise SystemExit(1) from None


def setup_parser(parser):
    commands = parser.add_subparsers(dest='katafit_action', required=True)
    configure = commands.add_parser('configure', help='Save your one-time credential with a hidden prompt')
    configure.add_argument('--token-stdin', action='store_true', help='Read credential from stdin, never argv')
    commands.add_parser('status', help='Report configuration and worker state; does not probe or call a model')
    commands.add_parser('run', help='Foreground diagnostic; stop the gateway worker first; Ctrl-C stops it')
