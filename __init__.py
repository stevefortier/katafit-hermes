"""Kata.fit official native Hermes plugin entrypoint."""
from pathlib import Path
from .katafit.cli import App, setup_parser


def register(ctx):
    # Resolve the active home at command execution, not at module import.
    app = None

    def dispatch(args):
        nonlocal app
        from hermes_constants import get_hermes_home
        app = App(ctx, Path(get_hermes_home()))
        app.dispatch(args)

    def unload():
        if app is not None:
            app.unload()

    ctx.register_cli_command(name='katafit', help='Configure and run the Kata.fit Coach worker',
                             setup_fn=setup_parser, handler_fn=dispatch)
    ctx.on_unload(unload)

    def adapter_factory(config):
        from hermes_constants import get_hermes_home
        from .katafit.adapter import KatafitAdapter
        return KatafitAdapter(config, ctx, Path(get_hermes_home()))

    ctx.register_platform(name='katafit', label='Kata.fit Coach',
                          adapter_factory=adapter_factory, check_fn=lambda: True,
                          allow_update_command=False)
