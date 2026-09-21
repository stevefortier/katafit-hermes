import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from katafit.cli import App
from test_settings import TOKEN


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_worker_fences_foreground_and_configure_until_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {}
            ctx = SimpleNamespace(set_config=lambda *a: None,
                                  state=SimpleNamespace(get=state.get, set=lambda k,v: state.update({k:v})),
                                  spawn_task=lambda coro, **kw: asyncio.create_task(coro, **kw),
                                  llm=SimpleNamespace(acomplete=None))
            app = App(ctx, Path(tmp))
            app.settings.configure(TOKEN)
            entered, cancelled = asyncio.Event(), asyncio.Event()
            async def run(worker):
                entered.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()
            with patch('katafit.cli.Worker.run', run):
                self.assertTrue(app.start(mode='gateway'))
                await entered.wait()
                other = App(ctx, Path(tmp))
                self.assertEqual(other.status()['mode'], 'gateway')
                self.assertEqual(other.status()['profile_home'], str(Path(tmp).resolve()))
                with self.assertRaises(RuntimeError):
                    other.start(mode='foreground')
                with self.assertRaises(RuntimeError):
                    other.configure(io.StringIO(TOKEN))
                await app.stop()
                self.assertTrue(cancelled.is_set())
                self.assertEqual(other.status()['worker'], 'stopped')
                self.assertEqual(other.status()['connectivity'], 'unknown')
                with other.worker_lock():
                    pass

    async def test_missing_credential_never_spawns(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {}
            ctx = SimpleNamespace(state=SimpleNamespace(get=state.get, set=lambda k,v: state.update({k:v})))
            app = App(ctx, Path(tmp))
            self.assertFalse(app.start(mode='gateway'))
            self.assertEqual(app.status()['configuration'], 'setup-required')
            with app.worker_lock():
                pass
