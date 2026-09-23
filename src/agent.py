"""Product adapter: use the team's pipeline when present, otherwise local rules."""

from importlib import import_module, util
from pathlib import Path


def run(before: list[Path], after: list[Path], use_llm: bool = False, log=None) -> dict:
    # Do not mask import/runtime failures in an installed pipeline as a successful demo.
    if util.find_spec("src.pipeline") is not None:
        result = import_module("src.pipeline").run(before, after, use_llm=use_llm, log=log)
        if not isinstance(result, dict) or not all(
            key in result for key in ("units", "function_map", "findings", "conclusion")
        ):
            raise ValueError("Pipeline contract is incomplete")
        return result
    from app.local_analysis import run as local_run

    return local_run(before, after, log=log)
