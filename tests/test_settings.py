import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TOKEN = 'rgn_coach_' + 'a' * 24 + '_' + 'b' * 43

class SettingsTests(unittest.TestCase):
    def test_private_profile_credential_and_safe_config(self):
        self.assertIsNotNone(importlib.util.find_spec('katafit'), 'native plugin package is missing')
        from katafit.settings import Settings
        with tempfile.TemporaryDirectory() as tmp:
            config = {'unrelated': 42}
            ctx = SimpleNamespace(set_config=lambda k, v: config.update({k: v}))
            settings = Settings(ctx, Path(tmp))
            self.assertIsNone(settings.token())
            settings.configure(TOKEN)
            self.assertEqual(settings.token(), TOKEN)
            self.assertEqual(config, {'unrelated': 42, 'configured': True})
            self.assertEqual(settings.directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual((settings.directory / 'credential').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                settings.configure(TOKEN + '\nINJECT')
            self.assertEqual(settings.token(), TOKEN)
