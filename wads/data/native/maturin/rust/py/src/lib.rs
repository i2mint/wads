//! Python bindings for `tmpl_pkg`: a thin layer over `tmpl_pkg_core`.
//!
//! The Python facade (`tmpl_pkg/__init__.py`) owns the public signatures,
//! defaults and docstrings; functions here take every argument explicitly.

use pyo3::prelude::*;

/// The `tmpl_pkg._core` extension module.
#[pymodule]
mod _core {
    use pyo3::exceptions::{PyRuntimeError, PyValueError};
    use pyo3::prelude::*;

    use tmpl_pkg_core::CoreError;

    /// Maps each core error to the exception the pure-Python version raised.
    ///
    /// A function, not `impl From<CoreError> for PyErr`: both types are
    /// foreign to this crate, so that impl breaks the orphan rule (E0117).
    fn to_pyerr(err: CoreError) -> PyErr {
        match err {
            e @ CoreError::LengthMismatch { .. } => PyValueError::new_err(e.to_string()),
            // CoreError is #[non_exhaustive]: a variant added later must still map somewhere.
            e => PyRuntimeError::new_err(e.to_string()),
        }
    }

    /// Count the positions at which `a` and `b` hold different characters.
    #[pyfunction]
    #[pyo3(signature = (a, b, /))]
    fn hamming(a: &str, b: &str) -> PyResult<usize> {
        tmpl_pkg_core::hamming(a, b).map_err(to_pyerr)
    }
}
