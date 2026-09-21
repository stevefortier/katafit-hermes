# Kata.fit for Hermes

The official Kata.fit native Hermes plugin connects your Hermes model to Kata.fit's main Coach text chat. It works for personal owners and dojo chiefs, with requester-scoped conversation history. It does not take over activity reviews, workout threads, attachments, notifications, or shared plans.

## Install and configure

Requires Python 3.11–3.13 on Linux or macOS and a Hermes build with `PluginContext.register_platform`, `register_cli_command`, `set_config`, `state`, `spawn_task`, `on_unload`, and `llm.acomplete`. The verified compatibility target is NousResearch/hermes-agent commit **`ee5b5ec21e576ccf9b941f9ff71330418415a5cb`**, using host `httpx 0.28.1`. Windows is not supported in this first version (private permissions and process locking are POSIX).

```sh
hermes plugins install stevefortier/katafit-hermes --enable
hermes katafit configure
hermes gateway restart  # existing gateway service
# No service yet: hermes gateway install, then hermes gateway start
```

**Before this gateway follow-up is merged**, default-branch installation contains only the foreground worker from PR1. Reviewers must append `--ref <full-feature-commit-SHA>` to the install command. Hermes supports immutable full commit pins, not branch names or abbreviated hashes. There is no PyPI package, Hermes registry listing, or release publication.

In Kata.fit's AI Coach settings (or Dojo settings, for the chief), create a scoped credential and paste it into the **hidden** configure prompt. No JSON editing, token argument, or absolute path is needed. For a secret manager, pipe the token to `hermes katafit configure --token-stdin`; do not place the token literally in shell history. The plugin validates the actual `rgn_coach_…` credential format and stores it in an owner-only file beneath the active Hermes profile. Non-secret settings use Hermes' atomic `ctx.set_config` API and preserve unrelated configuration.

Configure enables the actual host setting `platforms.katafit.enabled` using `hermes config set`; it does not silently restart a running gateway or disrupt other messaging platforms. Start/restart the **same profile's gateway** as shown above. The supported `ctx.register_platform` adapter starts polling in async `connect()` and cancels it in `disconnect()`. No dedicated Kata.fit terminal or conversational session is needed while the gateway service runs. Gateway stop/restart affects that profile's other messaging platforms too. Service installation depends on Hermes' normal OS supervisor support; without one, `hermes gateway run` is the host foreground alternative.

**Credential replacement:** `hermes gateway stop` (or stop the diagnostic worker) → `hermes katafit configure` → `hermes gateway start`. Configure refuses rotation while either worker mode owns the lock. For diagnosis only, `hermes katafit run` runs in the foreground with Ctrl-C/SIGTERM cleanup; first stop the gateway worker. Installation without a credential succeeds. Gateway connect without one reports setup required and starts no polling/inference.

Discovery, install, configure and status never start polling. The manifest stays `kind: standalone` so native CLI commands load eagerly; the platform adapter imports lazily and starts only when the gateway connects it. Arbitrary gateway `send_message`/cron delivery is rejected: Kata.fit is not a normal Hermes messaging channel.

```sh
hermes katafit status
```

Status never performs inference or contacts Kata.fit. It includes resolved profile home and fresh gateway/foreground mode. It distinguishes setup required, configured, worker running/stopped, fresh connectivity, idle, working, backoff, auth rejection, and unknown/stale state. A profile-local OS lock prevents duplicate workers across gateway and foreground modes. Gateway adapter readiness means the poller started, not backend connectivity; only fresh plugin status can report the latter. A running worker or accepted credential is **not proof of a working Coach reply**: use **Test connection in Kata.fit**, which checks the exact persisted request, completion state, external attribution, and nonempty reply. The local status deliberately never claims that app-level verification.

Use Hermes' normal `--profile`/`-p` selection consistently if you use named profiles. The plugin resolves `get_hermes_home()` at command execution and never reads other profiles.

## Security and protocol

- Production endpoint is fixed to `https://kata.fit/api/agents/coach/mcp`; no inbound port or webhook is required. HTTPS redirects and proxy environment inheritance are disabled. The token is sent only in the MCP Authorization header, not to the public instructions fetch.
- Uses the backend's **stateless Streamable HTTP JSON-RPC** contract, including initialize/initialized and bounded JSON or SSE responses. Fetches `https://kata.fit/api/agents/coach.md` only when work exists; the first line must match external Coach **v1**, not a later occurrence or `v10`.
- List → claim → start → scoped context → respond/fail. Request ID, requester, scope and lease generation are fenced; lease expiry and request timeout both constrain work. No lease extension. Cancellation prevents late publication. An ambiguous response is never followed by fail or a blind reply retry; the backend owns durable idempotency and lease recovery.
- Uses **`ctx.llm.acomplete`**, the real host-owned one-shot inference surface, with no provider/model/profile/agent overrides. Sends only the versioned coaching instructions and the current backend-scoped JSON context. No `AIAgent`, tools, workspace, host memory, skills, session history, global prompt edits, or access to model-provider credentials. The bounded backend history is preserved, not replaced with a local cache.
- Idle polling performs zero inference. Network/model deadlines, bounded exponential backoff, fixed error codes, private credential storage and no raw exception logging limit exposure. A provider may finish an already-dispatched network call after cancellation; its late result cannot publish. Provider billing/cancellation behavior remains host-owned.
- Setup probes use the same text request lifecycle; the backend isolates their history and persistence. No synthetic success in production, proposals, direct mutations, OAuth claims, or silent hosted fallback.

Enabling a native Python plugin trusts it as local code; this is not an OS sandbox. Review the source and pin an immutable commit. Host-owned model calls use your configured provider and may incur provider charges when real requests arrive.

## Development and verification

```sh
python -m venv .venv
.venv/bin/pip install 'httpx==0.28.1'
.venv/bin/python -m unittest discover -s tests -v
```

Tests use synthetic credentials/context and never need production credentials. Native installation and backend seam verification receipts are documented in `docs/verification.md`. The real backend seam substitutes only model completion; it is not evidence of a paid/live provider response.

SDK sources: [platform adapters](https://hermes-agent.nousresearch.com/docs/developer-guide/adding-platform-adapters), [plugins guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [plugin LLM access](https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access), [native plugin installer](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins). MIT licensed.
