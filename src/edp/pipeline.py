"""Orchestration: run generate -> ingest -> transform -> quality as a DAG.

Two interchangeable backends:

  * Prefect (`flows`/`tasks`) -- used automatically IF it is importable AND a
    flow actually runs. Prefect is an optional extra, not a hard dependency.
  * A small dependency-free topological-sort runner -- the default fallback,
    used when Prefect is absent or if the Prefect backend fails at runtime.

Both backends execute the SAME task functions and produce the SAME
`PipelineResult`, so the pipeline is reliable offline with or without Prefect.
The chosen backend is recorded in the result and printed in the summary -- no
pretending. Detection and fallback are graceful: an import failure or a runtime
error in the Prefect path logs a warning and drops to the topological runner.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from edp.config import Config
from edp.generate import GenerateResult, generate
from edp.ingest import ingest
from edp.quality import QualityReport, run_quality
from edp.transform import build_plan, transform

logger = logging.getLogger("edp.pipeline")


@dataclass
class PipelineResult:
    orchestrator: str = "topological"
    generate_counts: dict[str, int] = field(default_factory=dict)
    ingest_counts: dict[str, int] = field(default_factory=dict)
    transform_counts: dict[str, int] = field(default_factory=dict)
    plan: list[str] = field(default_factory=list)
    quality: QualityReport | None = None
    duration_s: float = 0.0

    @property
    def quality_passed(self) -> bool:
        return self.quality is not None and self.quality.passed


# --------------------------------------------------------------------------- #
# Task functions -- pure, backend-agnostic. Each returns what the next needs.
# --------------------------------------------------------------------------- #
def task_generate(cfg: Config) -> GenerateResult:
    logger.info("generate: creating synthetic raw files")
    return generate(cfg)


def task_ingest(cfg: Config, gen: GenerateResult) -> dict[str, int]:
    logger.info("ingest: landing raw files into DuckDB `raw` schema")
    return ingest(gen, cfg)


def task_transform(cfg: Config) -> dict[str, int]:
    logger.info("transform: building staging + marts models in dependency order")
    return transform(cfg)


def task_quality(cfg: Config) -> QualityReport:
    logger.info("quality: running data-quality suite against the warehouse")
    return run_quality(cfg)


# --------------------------------------------------------------------------- #
# Backend detection
# --------------------------------------------------------------------------- #
def prefect_available() -> bool:
    """True only if Prefect imports AND is not disabled via env override.

    Set EDP_DISABLE_PREFECT=1 to force the topological runner (used in CI for a
    fast, quiet, fully deterministic run).
    """
    if os.environ.get("EDP_DISABLE_PREFECT") == "1":
        return False
    try:
        import prefect  # noqa: F401
    except Exception:  # pragma: no cover - environment dependent
        return False
    return True


# --------------------------------------------------------------------------- #
# Fallback backend: explicit DAG + topological sort
# --------------------------------------------------------------------------- #
def _run_topological(cfg: Config, result: PipelineResult) -> PipelineResult:
    """Execute the task DAG in dependency order without any orchestrator."""
    # DAG: node -> set of upstream nodes it depends on.
    dag = {
        "generate": set(),
        "ingest": {"generate"},
        "transform": {"ingest"},
        "quality": {"transform"},
    }
    order = _toposort(dag)
    logger.info("topological plan: %s", " -> ".join(order))

    ctx: dict[str, object] = {}
    for node in order:
        if node == "generate":
            gen = task_generate(cfg)
            ctx["gen"] = gen
            result.generate_counts = gen.counts
        elif node == "ingest":
            result.ingest_counts = task_ingest(cfg, ctx["gen"])  # type: ignore[arg-type]
        elif node == "transform":
            result.plan = build_plan(cfg)
            result.transform_counts = task_transform(cfg)
        elif node == "quality":
            result.quality = task_quality(cfg)
    return result


def _toposort(dag: dict[str, set[str]]) -> list[str]:
    """Kahn's algorithm with alphabetical tie-breaks (deterministic order)."""
    remaining = {k: set(v) for k, v in dag.items()}
    order: list[str] = []
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if deps <= set(order))
        if not ready:
            raise ValueError(f"Cycle in task DAG: {sorted(remaining)}")
        order.extend(ready)
        for n in ready:
            remaining.pop(n)
    return order


# --------------------------------------------------------------------------- #
# Prefect backend
# --------------------------------------------------------------------------- #
def _run_prefect(cfg: Config, result: PipelineResult) -> PipelineResult:
    """Run the same tasks inside a Prefect flow. Kept quiet and ephemeral."""
    # Reduce Prefect's noise and keep it fully local/offline before import.
    os.environ.setdefault("PREFECT_LOGGING_LEVEL", "WARNING")
    os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "False")
    from prefect import flow, task

    gen_t = task(name="generate")(task_generate)
    ing_t = task(name="ingest")(task_ingest)
    trn_t = task(name="transform")(task_transform)
    qal_t = task(name="quality")(task_quality)

    @flow(name="edp-elt", log_prints=False)
    def _flow() -> PipelineResult:
        gen = gen_t(cfg)
        result.generate_counts = gen.counts
        result.ingest_counts = ing_t(cfg, gen)
        result.plan = build_plan(cfg)
        result.transform_counts = trn_t(cfg)
        result.quality = qal_t(cfg)
        return result

    return _flow()


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def run_pipeline(cfg: Config | None = None, prefer_prefect: bool = True) -> PipelineResult:
    """Run the full ELT pipeline, choosing the best available backend."""
    cfg = cfg or Config()
    result = PipelineResult()
    start = time.perf_counter()

    if prefer_prefect and prefect_available():
        try:
            result.orchestrator = "prefect"
            result = _run_prefect(cfg, result)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Prefect backend failed (%s); falling back to topological", exc)
            result = PipelineResult(orchestrator="topological (prefect-fallback)")
            result = _run_topological(cfg, result)
    else:
        result.orchestrator = "topological"
        result = _run_topological(cfg, result)

    result.duration_s = time.perf_counter() - start
    return result
