"""TEST ONLY: real installed worker + host ctx.llm, synthetic model boundary.

Reads a synthetic local-backend credential on stdin; refuses non-loopback URLs.
Not a production CLI and not a substitute for Kata.fit Test connection.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit


def main():
    data = json.load(sys.stdin)
    url = urlsplit(data['origin'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.query or url.fragment or url.username:
        raise ValueError('Loopback synthetic backend required')
    with tempfile.TemporaryDirectory(prefix='katafit-hermes-seam-') as tmp:
        os.environ['HERMES_HOME'] = tmp
        os.environ['HOME'] = tmp
        sys.path.insert(0, str(Path(data['hermes_source']).resolve()))
        sys.path.insert(0, str(Path(data['plugin_root']).resolve()))
        from hermes_cli.plugins import PluginContext, PluginManager
        from hermes_cli.plugins_manifest import PluginManifest
        from katafit.worker import Worker
        ctx = PluginContext(PluginManifest(name='katafit', source='user'), PluginManager())
        captured = []
        async def caller(**kwargs):
            captured.append(kwargs)
            assert kwargs['provider_override'] is None and kwargs['model_override'] is None
            assert kwargs['profile_override'] is None and kwargs['task'] is None
            assert 'tools' not in kwargs
            return ('synthetic', 'synthetic-model', SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='I coach strength with recovery in mind.'))]))
        # The actual host facade/trust gate/result builder execute. Only provider I/O is synthetic.
        ctx.llm._async_caller = caller
        # Execute the installed native register/CLI handlers, not a stand-in CLI.
        import argparse
        import importlib.util
        import io
        from contextlib import redirect_stdout
        root = Path(data['plugin_root']).resolve()
        spec = importlib.util.spec_from_file_location('installed_katafit', root / '__init__.py',
                                                     submodule_search_locations=[str(root)])
        plugin = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = plugin
        spec.loader.exec_module(plugin)
        plugin.register(ctx)
        cli_module = sys.modules['installed_katafit.katafit.cli']
        BaseWorker = cli_module.Worker
        class LocalWorker(BaseWorker):
            def __init__(self, *args, **kwargs):
                kwargs['origin'] = data['origin']
                callback = kwargs['on_state']
                def state(value):
                    callback(value)
                    if value == 'reply-submitted':
                        running = cli_module.App(ctx, Path(tmp)).status()
                        assert running['worker'] == 'running' and running['connectivity'] == 'connected'
                        asyncio.current_task().cancel()
                kwargs['on_state'] = state
                super().__init__(*args, **kwargs)
        cli_module.Worker = LocalWorker
        handler = ctx._manager._cli_commands['katafit']['handler_fn']
        original_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(data['token'] + '\n')
            with redirect_stdout(io.StringIO()):
                handler(argparse.Namespace(katafit_action='configure', token_stdin=True))
                handler(argparse.Namespace(katafit_action='run'))
            assert cli_module.App(ctx, Path(tmp)).status()['worker'] == 'stopped'
        finally:
            sys.stdin = original_stdin
        assert len(captured) == 1
        assert data['token'] not in json.dumps(captured)
        print(json.dumps(captured[0]))


if __name__ == '__main__':
    main()
