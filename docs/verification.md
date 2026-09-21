# Verification receipts and limits

## Verified interfaces

Host: official NousResearch/hermes-agent `ee5b5ec21e576ccf9b941f9ff71330418415a5cb`, project version `0.21.0`, Python 3.11.15; inspected SDK files were unmodified. Public GitHub confirms that exact commit. Host transport dependency: `httpx 0.28.1`.

Supported source install: `hermes plugins install stevefortier/katafit-hermes --ref <40-character-commit> --enable`.
Native registered commands: `hermes katafit configure`, `hermes katafit configure --token-stdin`, `hermes katafit status`, `hermes katafit run`.

`PluginContext` provides `register_cli_command`, `get_config`/`set_config`, `state`, `on_unload`, `spawn_task`, and `llm.acomplete`. `spawn_task` needs a running asyncio loop and is cancelled on unload. Synchronous discovery is not a background-worker lifecycle: no threads or pollers start at registration. The native `run` handler owns the event loop and supervised worker. There is no invented gateway service/auto-start API.

**Installer compatibility finding:** this source's loader parses manifest v2, but its native GitHub installer rejects `manifest_version: 2`. The shipped artifact uses v1, verified by actual installation rather than assuming the loader proves installer support. The host also prints a generic gateway-restart hint after enabling; this plugin's dedicated `run` command needs no gateway restart.

## Native installed artifact

Executed `scripts/verify_host.py` against the actual GitHub-installed artifact `5dde892653d43975ec23c2a8b2ad8b59104b84ce` in a disposable HOME/HERMES_HOME with a minimal environment. The script is now also a pinned-host CI job and accepts the exact PR head.

Verified:
- native GitHub cloning, immutable checkout and enabled discovery;
- registered CLI help and status;
- missing token is `setup-required`, not failed installation; `run` prints setup instructions and exits;
- stdin configuration and actual PTY hidden configuration, with no token echo;
- automatic profile-local 0700 directory / 0600 credential;
- no token in config.yaml, unrelated `display.skin` preserved;
- configured but stopped status correctly reports unknown connectivity, not success.

No live profile, gateway, provider credentials, or other profiles were read or changed. Disposable host-test profiles are removed in `finally`/temporary-directory cleanup.

## Real backend MCP + native lifecycle + host model seam

Read-only backend main contract at `366157f4011da9c5d91db862140536792759f71a`; reference OpenClaw plugin main at `5d58e9b7e23180b9630bf745e81bb981fcbff429`. Backend source and its private tests are **not included in this public repository**.

Four real-backend tests passed using a fresh local MongoDB replica set, real Express/MCP SDK HTTP routing, synthetic scoped credentials, and the actual GitHub-installed Hermes plugin. `scripts/seam_worker.py` exercises its native registered configure/run handlers, real `ctx.spawn_task` lifecycle, running/connected status and stopped cleanup. Only the model provider boundary (`ctx.llm` async caller) returns a fixed synthetic reply; the real host trust gate, message shaping and result handling still execute. The harness injects a loopback endpoint and refuses non-loopback URLs. It is a test utility, not an installed command.

Passing scenarios:
1. Mixed hosted/external dojo history survives routing changes.
2. Bounded recent history excludes future, wrong-scope and setup-probe records.
3. Two-turn external follow-up receives persisted prior question/reply, excludes private pre-dojo/other-member history, and clears after canonical conversation clear.
4. Setup probe returns exact request completion, `verified: true`, `source: external_agent`, matching request ID and nonempty persisted reply; real canonical chat is unchanged. Backend setup context contains only its synthetic question, not user history.

Backend warnings were pre-existing optional-email-disabled / AWS SDK maintenance / old browser-baseline data notices. No paid provider inference or authenticated production setup test was performed. The synthetic model seam is not a claim that an arbitrary user's subscription/provider works.

## Automated suite

`python -m unittest discover -s tests -v`: 15 tests passing (12 at the first native-artifact verification, plus additional permission/output/fencing regressions). Covers registration without tools/background side effects, private storage/configuration/locking/status, real worker sequencing and canonical context preservation, idle-no-inference, requester fencing, leading version rejection, token-in-context rejection, auth errors, ambiguous delivery, cancellation and a model that ignores cancellation beyond its budget.

CI runs unit tests on Python 3.11/3.12/3.13 and checks the real native GitHub installer/CLI against the pinned SDK with a frozen host lockfile. Private backend tests cannot run in this public repository's CI without separately authorized backend access.

## Limits

- Linux/macOS POSIX permissions and locking only; no Windows support claimed.
- Persistent worker requires keeping `hermes katafit run` alive or an existing supervisor; no automatic gateway background startup or service installation is claimed.
- One-shot host inference cannot execute tools or use workspace/memory. Provider-side in-flight work may finish/bill after cancellation; late results cannot publish a reply.
- Plugin status reports local operational state. Only the Kata.fit setup-test result can establish a verified attributed reply.
- No registry listing, OAuth integration, release, automatic merge or hosted fallback was published.
