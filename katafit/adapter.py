"""Gateway-owned polling only; never enters Hermes' conversational message pipeline."""
from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, SendResult
from .cli import App


class KatafitAdapter(BasePlatformAdapter):
    def __init__(self, config, ctx, home):
        super().__init__(config, Platform('katafit'))
        self.app = App(ctx, home)
        self._stopping = False
        ctx.on_unload(self.app.unload)

    async def connect(self, *, is_reconnect=False):
        if self.app.task is not None:
            return True
        self._stopping = False
        try:
            if not self.app.start(mode='gateway'):
                self._set_fatal_error('KATAFIT_SETUP_REQUIRED',
                                      'Run hermes katafit configure, then restart this profile gateway.',
                                      retryable=False)
                return False
        except Exception:
            # Host logs adapter errors; never let credentials/private exception payloads escape.
            self._set_fatal_error('KATAFIT_WORKER_UNAVAILABLE',
                                  'Stop any existing Kata.fit worker and check private configuration.',
                                  retryable=False)
            return False
        self._mark_connected()  # Lifecycle readiness, not backend connectivity or reply verification.
        def finished(task):
            if not self._stopping:
                self._set_fatal_error('KATAFIT_WORKER_STOPPED',
                                      'Kata.fit worker stopped. Restart this profile gateway.', retryable=False)
        self.app.task.add_done_callback(finished)
        return True

    async def disconnect(self):
        self._stopping = True
        await self.app.stop()
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        # No cron, send_message, notifications, normal AIAgent outputs, or arbitrary outbound chat.
        return SendResult(success=False, error='Kata.fit accepts only scoped claimed Coach replies.')

    async def get_chat_info(self, chat_id):
        return {'name': 'Kata.fit scoped worker (not a messaging channel)', 'type': 'worker'}
