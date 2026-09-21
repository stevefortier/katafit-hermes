import asyncio
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_settings import TOKEN

class CliTests(unittest.TestCase):
    def test_native_configuration_and_status_do_not_start_or_call_model(self):
        self.assertIsNotNone(importlib.util.find_spec('katafit.cli'), 'native CLI is missing')
        from katafit.cli import App
        with tempfile.TemporaryDirectory() as tmp:
            config, state = {}, {}
            ctx = SimpleNamespace(set_config=lambda k,v: config.update({k:v}),
                                  state=SimpleNamespace(get=state.get, set=lambda k,v:state.update({k:v})))
            app = App(ctx, Path(tmp))
            self.assertEqual(app.status()['configuration'], 'setup-required')
            output = io.StringIO()
            with redirect_stdout(output), patch('subprocess.run') as host_config:
                app.configure(io.StringIO(TOKEN + '\n'))
            host_config.assert_called_once()
            self.assertEqual(host_config.call_args.args[0][-4:],
                             ['config', 'set', 'platforms.katafit.enabled', 'true'])
            self.assertEqual(host_config.call_args.kwargs['env']['HERMES_HOME'], tmp)
            self.assertIn('hermes gateway restart', output.getvalue())
            self.assertNotIn(TOKEN, output.getvalue())
            status = app.status()
            self.assertEqual(status['configuration'], 'configured')
            self.assertEqual(status['worker'], 'stopped')
            self.assertEqual(status['connectivity'], 'unknown')
            self.assertFalse(status['reply_verified'])
            with app.worker_lock():
                self.assertEqual(app.status()['worker'], 'running')
                with self.assertRaises(RuntimeError):
                    with app.worker_lock():
                        pass
                with self.assertRaises(RuntimeError):
                    app.configure(io.StringIO(TOKEN))
