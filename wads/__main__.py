"""The ``wads`` console script (also ``python -m wads``).

``wads ci-local`` does locally what the wads CI would have done, from the same
``[tool.wads.ci]`` config; see :mod:`wads.ci_local`.
"""

from wads.ci_local import ci_local

_dispatch_funcs = [ci_local]


def main():
    """Entry point of the ``wads`` console script."""
    import cw

    raise SystemExit(cw.dispatch(_dispatch_funcs, prog="wads"))


if __name__ == "__main__":
    main()
