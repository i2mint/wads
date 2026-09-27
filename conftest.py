"""Repository-level pytest configuration.

``wads/data`` holds project *templates* (for example ``test_smoke_tpl.py``,
which is not valid Python until rendered), so pytest must never import it,
whatever directory pytest is run from.
"""

collect_ignore = ["wads/data"]
