"""Real host discovery/config/start/shutdown, synthetic MCP and provider I/O only.

Run under verify_host's empty HOME, using the installed GitHub artifact.
Never run against a user's active profile.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timedelta, timezone


async def verify():
    import httpx
    from hermes_cli.plugins import discover_plugins
    from gateway.config import load_gateway_config, Platform
    from gateway.run import GatewayRunner
    discover_plugins()
    cfg = load_gateway_config()
    platform = Platform('katafit')
    assert cfg.platforms[platform].enabled
    runner = GatewayRunner(cfg)
    calls, prompts = [], []
    done, entered, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    phase = 'reply'
    request = dict(id='synthetic-setup-history', requester_id='synthetic-requester', scope='personal',
                   attachment_count=0, lease_generation=1, message='Continue earlier coaching',
                   lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat(),
                   timeout_at=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat())
    context = dict(request=request, conversation=[{'role': 'user', 'text': 'Prior question'},
                                                  {'role': 'coach', 'text': 'Prior answer'}])
    token = (Path(os.environ['HERMES_HOME']) / 'katafit-private/credential').read_text()
    async def transport(req):
        assert req.url.host == 'kata.fit'
        if req.url.path.endswith('.md'):
            return httpx.Response(200, text='# Kata.fit external Coach agent v1\nSynthetic contract.')
        assert req.headers['authorization'] == 'Bearer ' + token
        payload = json.loads(req.content)
        if payload['method'] == 'initialize':
            value = {'protocolVersion': '2025-03-26'}
        elif payload['method'] == 'notifications/initialized':
            return httpx.Response(202)
        else:
            name, args = payload['params']['name'], payload['params']['arguments']
            calls.append((name, args))
            values = {'coach_list_requests': {'requests': [] if phase == 'idle' else [request]},
                      'coach_claim_request': {'request': request}, 'coach_start_request': {'request': request},
                      'coach_read_context': context, 'coach_respond': {'request': {'status': 'completed'}}}
            value = {'structuredContent': values[name]}
            if name == 'coach_respond':
                assert args == {'request_id': request['id'], 'lease_generation': 1, 'text': 'Synthetic scoped reply'}
                done.set()
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': payload['id'], 'result': value})
    async def provider(self, kw):
        prompts.append(kw)
        assert kw['provider_override'] is None and kw['model_override'] is None
        assert kw['profile_override'] is None and kw['task'] is None and 'tools' not in kw
        assert json.loads(kw['messages'][1]['content']) == context
        assert len(kw['messages']) == 2 and token not in json.dumps(kw)
        if phase == 'cancel':
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        return ('synthetic', 'synthetic-model', SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='Synthetic scoped reply'))]))
    real_client = httpx.AsyncClient
    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(transport), **kwargs)
    # No host background model refresh/warm-up, cron/kanban or other services in this seam.
    # Adapter creation, config selection, connect aggregation and shutdown stay real.
    with patch('socket.socket.connect', side_effect=AssertionError('Real network forbidden')), \
         patch('socket.socket.connect_ex', side_effect=AssertionError('Real network forbidden')), \
         patch('httpx.AsyncClient', client), patch('agent.plugin_llm.PluginLlm._invoke_async', provider), \
         patch.object(runner, '_start_startup_warmup'), \
         patch.object(runner, '_start_spawn_background_watchers'), \
         patch.object(runner, '_start_finish_wiring'), \
         patch.object(runner, '_handle_message', side_effect=AssertionError('Normal agent routing forbidden')):
        try:
            assert await runner.start()
            assert platform in runner.adapters, 'Gateway did not create the installed adapter'
            adapter = runner.adapters[platform]
            await asyncio.wait_for(done.wait(), 10)
            assert len(prompts) == 1
            assert adapter.app.status()['mode'] == 'gateway'
            # Fresh CLI processes see the same profile lock/state, not an in-memory stub.
            import subprocess
            command = [sys.executable, str(Path(sys.argv[1]) / 'hermes'), 'katafit']
            status = subprocess.run(command + ['status'], capture_output=True, text=True, timeout=20)
            assert status.returncode == 0
            live = json.loads(status.stdout)
            assert live['worker'] == 'running' and live['mode'] == 'gateway'
            for arguments, input_value in [(['run'], None), (['configure', '--token-stdin'], token + '\n')]:
                refused = subprocess.run(command + arguments, input=input_value,
                                         capture_output=True, text=True, timeout=20)
                assert refused.returncode == 1
                assert token not in refused.stdout + refused.stderr
            phase = 'idle'
            before = len(calls)
            await asyncio.sleep(5.2)
            assert len(calls) > before and len(prompts) == 1, 'Idle poll must not infer'
            phase = 'cancel'
            await asyncio.wait_for(entered.wait(), 10)
        finally:
            await runner.stop()
        await asyncio.wait_for(cancelled.wait(), 2)
        assert adapter.app.status()['worker'] == 'stopped'
        assert sum(name == 'coach_respond' for name, _ in calls) == 1
        assert adapter.app.task is None
        # No credentials: supported connect returns false, no network/task/inference.
        credential = adapter.app.settings.directory / 'credential'
        credential.unlink()
        assert not await adapter.connect()
        assert adapter.app.status()['configuration'] == 'setup-required'
        assert len(prompts) == 2
        assert not (await adapter.send('anything', 'not a gateway chat')).success
        await adapter.disconnect()
    print('VERIFIED: actual GatewayRunner.start/config/registry/adapter, scoped ctx.llm history reply, idle zero inference, shutdown cancellation, missing credential safe, outbound denied')


if __name__ == '__main__':
    home = Path(os.environ['HOME']).resolve()
    assert home.name.startswith('katafit-hermes-host-'), 'Isolated test HOME required'
    assert Path(os.environ['HERMES_HOME']).resolve().is_relative_to(home)
    sys.path.insert(0, sys.argv[1])
    asyncio.run(verify())
