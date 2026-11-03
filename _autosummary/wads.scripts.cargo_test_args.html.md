# wads.scripts.cargo_test_args

Print the `cargo test` arguments for a maturin package (issue #166).

Usage (as the rust-checks action runs it):

```default
cargo metadata --manifest-path M --no-deps --format-version 1 \
    | python3 -I cargo_test_args.py M
```

`M` is the binding crate’s `Cargo.toml` (`[tool.maturin].manifest-path`, resolved
by the setup job). Prints the arguments on one line, or nothing when there is no
pure-Rust crate to test. Standard library only: it runs from the action’s checkout
without installing wads.

### Functions

| `main`([argv])   |    |
|------------------|----|
