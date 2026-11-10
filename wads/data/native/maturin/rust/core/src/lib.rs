//! Pure-Rust core of `tmpl_pkg`: no Python types, tested with `cargo test`.
//!
//! Replace the example with the hot path being moved to Rust. Keep this crate
//! free of `PyO3` so its tests never link libpython and it can serve another
//! surface (a CLI, another binding) later.
//!
//! ```
//! assert_eq!(tmpl_pkg_core::hamming("karolin", "kathrin"), Ok(3));
//! ```

/// Errors of the core, mapped to Python exceptions in the binding crate.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[non_exhaustive]
pub enum CoreError {
    /// The two inputs do not have the same number of characters.
    #[error("sequences differ in length: {left} != {right}")]
    LengthMismatch {
        /// Characters in the first input.
        left: usize,
        /// Characters in the second input.
        right: usize,
    },
}

/// Counts the positions at which `a` and `b` hold different characters.
///
/// Characters are Unicode scalar values, which is what Python's `str`
/// indexes, so the result matches the pure-Python reference.
///
/// # Errors
///
/// [`CoreError::LengthMismatch`] when the inputs differ in length.
pub fn hamming(a: &str, b: &str) -> Result<usize, CoreError> {
    let (left, right) = (a.chars().count(), b.chars().count());
    if left != right {
        return Err(CoreError::LengthMismatch { left, right });
    }
    Ok(a.chars().zip(b.chars()).filter(|(x, y)| x != y).count())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts_differences() {
        assert_eq!(hamming("karolin", "kathrin"), Ok(3));
        assert_eq!(hamming("", ""), Ok(0));
    }

    #[test]
    fn counts_characters_not_bytes() {
        assert_eq!(hamming("é", "e"), Ok(1));
    }

    #[test]
    fn rejects_unequal_lengths() {
        assert_eq!(
            hamming("ab", "a"),
            Err(CoreError::LengthMismatch { left: 2, right: 1 })
        );
    }
}
