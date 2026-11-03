# wads.native_build

Native (compiled-extension) builds: which repos get one, for which targets.

A package built with [maturin](https://www.maturin.rs/) (a Rust/PyO3 extension) needs one
wheel per platform, built on that platform’s runner, where a pure-Python package needs one
`uv build`. The reusable workflow (`uv-ci.yml`) has a native path for it (issue #166),
and every job on that path is gated on the setup job’s `native` output, so pure-Python
repos run exactly what they ran before.

The path is on when `[build-system].build-backend = "maturin"` (auto-detected) or when
`[tool.wads.ci.build].native` says so. `native` takes a backend name, `false`, or a
table for the details:

```default
[tool.wads.ci.build]
native = "maturin"            # or false: no native path even with a maturin backend

[tool.wads.ci.build.native]   # the table form (instead of the line above)
targets = ["linux-x86_64", "macos-arm64"]     # names from NATIVE_TARGETS, or tables
maturin_args = ["--release", "--locked"]
smoke_import = "mypkg._core"                  # default: [tool.maturin].module-name
cargo_test_args = ["-p", "mypkg-core"]        # default: derived from cargo metadata
```

A target is a name from [`NATIVE_TARGETS`](#wads.native_build.NATIVE_TARGETS) or a table with the same keys (`name`,
`runner`, `target`, and optionally `manylinux`, `python_arch`, `smoke`), for a
platform the registry lacks (musllinux, Windows on ARM). Everything here is standard
library only: the setup job loads this file by path, without installing wads.

### Module Attributes

| [`NATIVE_BACKENDS`](#wads.native_build.NATIVE_BACKENDS)   | Build backends with a native path.   |
|--------------------------------------------------------------------|--------------------------------------|
| [`NATIVE_TARGETS`](#wads.native_build.NATIVE_TARGETS)    | the platforms the fleet's users run. |

### Functions

| [`cargo_test_args`](#wads.native_build.cargo_test_args)(metadata, \*, binding_manifest)   | `cargo test` arguments for every workspace crate except the binding one.                                       |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| [`native_build_config`](#wads.native_build.native_build_config)(pyproject)                    | The repo's [`NativeBuild`](#wads.native_build.NativeBuild), or `None` when it has no native path. |

### Classes

| [`NativeBuild`](#wads.native_build.NativeBuild)(backend[, targets, ...])      | The resolved native-build settings of one repo.                       |
|--------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`NativeTarget`](#wads.native_build.NativeTarget)(name, runner, target[, ...]) | One wheel to build: the runner it builds on and maturin's `--target`. |

### wads.native_build.NATIVE_BACKENDS *= {'maturin': 'maturin'}*

Build backends with a native path. The value is the backend’s `build-backend` string.

### wads.native_build.NATIVE_TARGETS *= {'linux-aarch64': NativeTarget(name='linux-aarch64', runner='ubuntu-24.04-arm', target='aarch64', manylinux='auto', python_arch='', smoke=True), 'linux-x86_64': NativeTarget(name='linux-x86_64', runner='ubuntu-latest', target='x86_64', manylinux='auto', python_arch='', smoke=True), 'macos-arm64': NativeTarget(name='macos-arm64', runner='macos-latest', target='aarch64', manylinux='', python_arch='', smoke=True), 'macos-x86_64': NativeTarget(name='macos-x86_64', runner='macos-latest', target='x86_64', manylinux='', python_arch='', smoke=False), 'windows-x64': NativeTarget(name='windows-x64', runner='windows-latest', target='x64', manylinux='', python_arch='x64', smoke=True)}*

the platforms the fleet’s users run. abi3 wheels, so one
build per platform covers every supported CPython.

* **Type:**
  The default wheel matrix

### *class* wads.native_build.NativeBuild(backend, targets=tuple(), maturin_args=('--release', '--locked'), smoke_import='', manifest_path='Cargo.toml', cargo_test_args=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The resolved native-build settings of one repo.

#### cargo_test_args *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)]* *= None*

derive from cargo metadata (every crate but the binding one).

* **Type:**
  `None`

#### manifest_path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Cargo.toml'*

The binding crate’s Cargo.toml (`[tool.maturin].manifest-path`); cargo finds the
workspace from it.

#### matrix()

The `native-wheels` job’s `matrix.include`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

#### options()

Everything but the matrix, as the setup job’s `native-options` output.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* wads.native_build.NativeTarget(name, runner, target, manylinux='', python_arch='', smoke=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One wheel to build: the runner it builds on and maturin’s `--target`.

`smoke` says whether the runner can import the wheel it built (a cross-compiled
wheel, macOS x86_64 on an arm64 runner, cannot).

### wads.native_build.cargo_test_args(metadata, , binding_manifest)

`cargo test` arguments for every workspace crate except the binding one.

The binding crate (the `cdylib` maturin builds, at `binding_manifest`) is tested
through Python: its own test binary needs libpython at link and load time. `metadata`
is `cargo metadata --no-deps --format-version 1`. An empty list means there is no
pure-Rust crate to test (a single-crate package).

```pycon
>>> meta = {"packages": [
...     {"name": "pkg-core", "manifest_path": "/r/rust/core/Cargo.toml"},
...     {"name": "pkg-py", "manifest_path": "/r/rust/py/Cargo.toml"},
... ]}
>>> cargo_test_args(meta, binding_manifest="/r/rust/py/Cargo.toml")
['--workspace', '--exclude', 'pkg-py']
>>> cargo_test_args({"packages": meta["packages"][1:]}, binding_manifest="/r/rust/py/Cargo.toml")
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.native_build.native_build_config(pyproject)

The repo’s [`NativeBuild`](#wads.native_build.NativeBuild), or `None` when it has no native path.

Raises `ValueError` on a setting that does not parse: only a repo that wrote native
settings can hit it, and a red setup job beats a release that silently builds
something else.

```pycon
>>> native_build_config({"build-system": {"build-backend": "hatchling.build"}}) is None
True
>>> nb = native_build_config({
...     "build-system": {"build-backend": "maturin"},
...     "tool": {"maturin": {"module-name": "pkg._core"}},
... })
>>> nb.backend, [t["name"] for t in nb.matrix()][:2], nb.smoke_import
('maturin', ['linux-x86_64', 'linux-aarch64'], 'pkg._core')
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`NativeBuild`](#wads.native_build.NativeBuild)]
