import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
from katafit.worker import Worker, WorkerError
from test_settings import TOKEN

class SafetyTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, context_patch=None, instruction='# Kata.fit external Coach agent v1\nGuide',
                idle=False, respond_error=False, status=200):
        self.calls, self.prompts = [], []
        request = dict(id='request', requester_id='member', scope='dojo', lease_generation=2, attachment_count=0,
                       lease_expires_at=(datetime.now(timezone.utc)+timedelta(seconds=100)).isoformat(),
                       timeout_at=(datetime.now(timezone.utc)+timedelta(seconds=100)).isoformat())
        context = {'request': dict(request), 'conversation': []}
        if context_patch:
            context_patch(context)
        async def transport(req):
            if status != 200:
                return httpx.Response(status, text=TOKEN)
            if req.url.path.endswith('.md'):
                return httpx.Response(200, text=instruction)
            p = json.loads(req.content)
            if p['method'] == 'notifications/initialized':
                return httpx.Response(202)
            if p['method'] == 'initialize':
                result = {'protocolVersion':'2025-03-26'}
            else:
                name = p['params']['name']
                self.calls.append(name)
                if name == 'coach_respond' and respond_error:
                    raise httpx.ReadTimeout(TOKEN)
                values = {'coach_list_requests':{'requests':[] if idle else [request]},
                          'coach_claim_request': {'request':request}, 'coach_start_request':{'request':request},
                          'coach_read_context':context, 'coach_fail_request':{}, 'coach_respond':{}}
                result = {'structuredContent':values[name]}
            return httpx.Response(200, json={'jsonrpc':'2.0','id':p['id'],'result':result})
        async def complete(**kw):
            self.prompts.append(kw)
            return SimpleNamespace(text='Safe response')
        client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        return Worker(TOKEN, complete, client=client), client

    async def test_no_idle_inference_or_instruction_fetch(self):
        worker, client = self.fixture(idle=True)
        async with client:
            await worker.poll_once()
        self.assertEqual(self.calls, ['coach_list_requests'])
        self.assertEqual(self.prompts, [])

    async def test_reject_wrong_requester_before_inference(self):
        worker, client = self.fixture(context_patch=lambda c:c['request'].update(requester_id='other'))
        async with client:
            with self.assertRaisesRegex(WorkerError, 'CONTEXT_REJECTED'):
                await worker.poll_once()
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.calls[-1], 'coach_fail_request')

    async def test_leading_version_only(self):
        for instruction in ('malicious preface\n# Kata.fit external Coach agent v1', '# Kata.fit external Coach agent v10\n'):
            worker, client = self.fixture(instruction=instruction)
            async with client:
                with self.assertRaisesRegex(WorkerError, 'CONTRACT_UNSUPPORTED'):
                    await worker.poll_once()
            self.assertNotIn('coach_claim_request', self.calls)

    async def test_ambiguous_delivery_never_fails_request(self):
        worker, client = self.fixture(respond_error=True)
        async with client:
            with self.assertRaises(WorkerError) as error:
                await worker.poll_once()
        self.assertNotIn(TOKEN, str(error.exception))
        self.assertNotIn('coach_fail_request', self.calls)

    async def test_auth_rejection_is_fixed_code(self):
        worker, client = self.fixture(status=401)
        async with client:
            with self.assertRaisesRegex(WorkerError, '^CREDENTIAL_REJECTED$'):
                await worker.poll_once()
        self.assertEqual(self.prompts, [])

    async def test_credential_in_context_is_rejected_before_model(self):
        worker, client = self.fixture(context_patch=lambda c:c.update(untrusted_text=TOKEN))
        async with client:
            with self.assertRaisesRegex(WorkerError, 'CONTEXT_REJECTED'):
                await worker.poll_once()
        self.assertEqual(self.prompts, [])

    async def test_model_ignoring_cancel_cannot_publish_after_budget(self):
        worker, client = self.fixture()
        worker.model_timeout = 0.01
        async def stubborn(**kw):
            try:
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                await asyncio.sleep(0.03)
            return SimpleNamespace(text='Too late')
        worker.complete = stubborn
        async with client:
            with self.assertRaises(WorkerError):
                await worker.poll_once()
            await asyncio.sleep(0.1)
        self.assertNotIn('coach_respond', self.calls)

    async def test_stale_generation_scope_and_attachments_are_rejected(self):
        for patch in ({'lease_generation': 1}, {'scope': 'personal'}, {'attachment_count': 1}):
            worker, client = self.fixture(context_patch=lambda c:c['request'].update(patch))
            async with client:
                with self.assertRaisesRegex(WorkerError, 'CONTEXT_REJECTED'):
                    await worker.poll_once()
            self.assertEqual(self.prompts, [])

    async def test_empty_oversize_and_credential_outputs_are_rejected(self):
        for text in ('', ' ', 'x' * 8001, TOKEN):
            worker, client = self.fixture()
            async def complete(**kw):
                return SimpleNamespace(text=text)
            worker.complete = complete
            async with client:
                with self.assertRaisesRegex(WorkerError, 'OUTPUT_REJECTED'):
                    await worker.poll_once()
            self.assertNotIn('coach_respond', self.calls)

    async def test_cancellation_never_publishes_or_fails(self):
        worker, client = self.fixture()
        entered = asyncio.Event()
        async def blocked(**kw):
            entered.set()
            await asyncio.sleep(60)
        worker.complete = blocked
        async with client:
            task = asyncio.create_task(worker.poll_once())
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertNotIn('coach_respond', self.calls)
        self.assertNotIn('coach_fail_request', self.calls)
