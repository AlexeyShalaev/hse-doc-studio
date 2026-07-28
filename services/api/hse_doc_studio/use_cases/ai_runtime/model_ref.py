from __future__ import annotations

import re

# A plausible Ollama model reference: optional `namespace/`, name, optional
# `:tag`. The name reaches Ollama as JSON (no shell), so this is a sanity/UX
# bound applied uniformly to every model-name input (pull/delete/unload), not
# the sole security barrier.
MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9._-]+)?(:[a-zA-Z0-9._-]+)?$")
MAX_NAME_LEN = 128


def is_valid_model_ref(name: str) -> bool:
    return 0 < len(name) <= MAX_NAME_LEN and MODEL_NAME_RE.match(name) is not None
