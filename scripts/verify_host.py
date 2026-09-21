"""Exercise the real native installer and registered CLI in an empty profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hermes-source', required=True, type=Path)
    parser.add_argument('--python', required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='katafit-hermes-host-') as tmp:
        home = Path(tmp)
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': tmp, 'HERMES_HOME': str(home / 'profile'),
               'LANG': 'C.UTF-8', 'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1'}
        command = [args.python, str(args.hermes_source / 'hermes')]
        def run(*arguments, input=None):
            result = subprocess.run(command + list(arguments), cwd=tmp, env=env, input=input,
                                    text=True, capture_output=True, timeout=90)
            print('$ hermes', ' '.join(arguments))
            print(result.stdout)
            if result.returncode:
                print(result.stderr)
                raise RuntimeError('Native host command failed')
            return result.stdout
        run('plugins', 'install', 'stevefortier/katafit-hermes', '--ref', args.revision, '--enable')
        run('plugins', 'list', '--user', '--plain')
        run('katafit', '--help')
        before = run('katafit', 'status')
        assert 'setup-required' in before
        run('katafit', 'run')
        run('config', 'set', 'display.skin', 'default')
        token = 'rgn_coach_' + 'a' * 24 + '_' + 'b' * 43
        run('katafit', 'configure', '--token-stdin', input=token + '\n')
        # Real hidden prompt through a PTY: do not print entered data on failure.
        import pty
        import select
        import time
        master, slave = pty.openpty()
        child = subprocess.Popen(command + ['katafit', 'configure'], cwd=tmp, env=env,
                                 stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        transcript = bytearray()
        sent = False
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        transcript.extend(os.read(master, 8192))
                    except OSError:
                        break
                if not sent and b'(hidden): ' in transcript:
                    os.write(master, (token + '\n').encode())
                    sent = True
                if child.poll() is not None:
                    break
            assert child.wait(timeout=5) == 0 and sent
            assert token.encode() not in transcript, 'Hidden prompt echoed credential'
            assert b'Credential saved privately' in transcript
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(master)
        print('VERIFIED: actual PTY hidden prompt did not echo credential')
        after = run('katafit', 'status')
        assert 'configured' in after and 'stopped' in after and 'unknown' in after
        config = (home / 'profile' / 'config.yaml').read_text()
        assert token not in config
        assert 'skin: default' in config and 'katafit' in config
        assert (home / 'profile' / 'katafit-private' / 'credential').stat().st_mode & 0o777 == 0o600
        print('VERIFIED: pinned GitHub native install, load, CLI, setup-required, configure, private credential, status')


if __name__ == '__main__':
    main()
