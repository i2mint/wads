//! Python bindings of the fixture, built by maturin as `wads_native_fixture._core`.

use pyo3::prelude::*;

/// The `wads_native_fixture._core` extension module.
#[pymodule]
mod _core {
    use pyo3::prelude::*;

    /// The sum of `a` and `b`, computed in Rust.
    #[pyfunction]
    fn add(a: i64, b: i64) -> i64 {
        wads_native_fixture_core::add(a, b)
    }
}
