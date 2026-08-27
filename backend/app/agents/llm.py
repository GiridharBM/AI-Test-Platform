"""Optional local/private AI analysis interface (Milestone 7 boundary).

This is a thin abstraction for a FUTURE local/private AI diagnosis layer. It
performs NO work by default (DIAGNOSIS_AI_ENABLED=False) and NEVER sends data
to any external service. No AI infrastructure (PyTorch, Transformers, Ollama,
Qdrant, GPU, model serving) is implemented here — that belongs to a future
milestone. The abstraction only documents the expected shape so that milestone
can integrate without changing the deterministic diagnosis contract.

Engagement contract:
    bug = llm.analyze(context)   # -> PotentialBug | None

When DIAGNOSIS_AI_ENABLED is False, analyze() returns None immediately and
never attempts a backend, import or network call. When enabled but no local
backend is configured, it raises to be caught by the caller so deterministic
diagnosis still completes.
"""

from app.core import config

# Reserved for a future local inference backend. None = not configured in M7.
_LOCAL_BACKEND = None


def analyze(context: dict) -> "object | None":
    """Analyse a diagnosis context and return a PotentialBug or None.

    Returns None without any call when DIAGNOSIS_AI_ENABLED is False (default).
    When enabled but no local backend is configured, raises RuntimeError so the
    caller can fail safe; no external data is ever transmitted.
    """
    if not config.DIAGNOSIS_AI_ENABLED:
        return None
    if _LOCAL_BACKEND is None:
        raise RuntimeError(
            "DIAGNOSIS_AI_ENABLED is true but no local/private AI backend is "
            "configured. No external analysis was performed."
        )
    # Future milestone: invoke the local/private backend here and return a
    # PotentialBug. M7 deliberately leaves this unimplemented (no AI infra).
    return _LOCAL_BACKEND(context)
