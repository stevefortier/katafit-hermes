import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

class RegistrationTests(unittest.TestCase):
    def test_register_only_native_cli_and_unload_no_tools_or_threads(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / '__init__.py').exists(), 'native entrypoint missing')
        spec = importlib.util.spec_from_file_location('katafit_plugin_under_test', root / '__init__.py',
                                                     submodule_search_locations=[str(root)])
        plugin = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = plugin
        spec.loader.exec_module(plugin)
        calls = []
        ctx = SimpleNamespace(register_cli_command=lambda **kw:calls.append(kw),
                              on_unload=lambda fn:calls.append(fn),
                              register_platform=lambda **kw:calls.append(kw))
        plugin.register(ctx)
        self.assertEqual(calls[0]['name'], 'katafit')
        self.assertTrue(callable(calls[0]['handler_fn']))
        platforms = [c for c in calls if isinstance(c, dict) and 'adapter_factory' in c]
        self.assertEqual(len(platforms), 1)
        self.assertEqual(platforms[0]['name'], 'katafit')
        self.assertTrue(platforms[0]['check_fn']())
