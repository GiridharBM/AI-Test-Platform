"""Bounded CPU / GPU benchmark of the sandboxed test-execution workload (M10).

Measures the established current-platform execution workload: running the
generated tests through the M6/Docker sandbox. Records per-run latency, warm-up
excluded from recorded stats, and reports min/mean/median. GPU availability is
probed honestly; when no supported GPU environment exists the GPU component is
simply marked unavailable and no GPU numbers are ever fabricated.

Benchmark results are inherently variable measurements; they are used only as
measurements (never as logical IDs) and are not claimed to be reproducible.
"""

import shutil
import statistics
import subprocess
from pathlib import Path

from app.core import config
from app.execution.runner import DockerUnavailable, run_sandboxed_command
from app.models.evaluation import (
    EVAL_BLOCKED,
    EVAL_COMPLETED,
    EVAL_UNAVAILABLE,
    BenchmarkResult,
)


def _pytest_args() -> list[str]:
    return ["-q", "--no-header", "-p", "no:cacheprovider"]


def compute_stats(measured: list[float]) -> tuple[float | None, float | None, float | None]:
    """Return (min, mean, median) of measured durations, rounded to ms."""
    if not measured:
        return None, None, None
    return (
        round(min(measured), 3),
        round(statistics.mean(measured), 3),
        round(statistics.median(measured), 3),
    )


def gpu_available() -> bool:
    """Honest GPU probe: true only when a supported GPU driver is present.

    NOTE: this host-side subprocess runs `nvidia-smi` for hardware discovery
    ONLY. It never executes uploaded/project code or tests; all executable
    project/test code runs inside the sandbox container. The probe decides
    only whether GPU numbers are reported or the GPU component is marked
    unavailable.
    """
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return False
    try:
        result = subprocess.run([nvidia], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_benchmark(
    source_root: Path,
    test_dir: Path,
    project_id: str = "",
    warm_up: int | None = None,
    measured_runs: int | None = None,
    timeout: int | None = None,
) -> BenchmarkResult:
    """Benchmark the sandboxed test-execution workload with bounded runs."""
    warm_up = warm_up if warm_up is not None else config.BENCHMARK_WARMUP_RUNS
    measured_runs = measured_runs if measured_runs is not None else config.BENCHMARK_MEASURED_RUNS
    timeout = timeout if timeout is not None else config.BENCHMARK_TIMEOUT_SECONDS

    if not test_dir.is_dir():
        return BenchmarkResult(
            status=EVAL_BLOCKED,
            warnings=["No generated tests to benchmark."],
        )

    gpu = gpu_available()
    durations: list[float] = []
    try:
        for _ in range(warm_up + measured_runs):
            outcome = run_sandboxed_command(
                project_id, source_root, test_dir,
                ["pytest"], _pytest_args(),
                timeout=timeout,
            )
            durations.append(outcome.duration_seconds)
    except DockerUnavailable as exc:
        return BenchmarkResult(
            status=EVAL_UNAVAILABLE,
            warnings=[str(exc)],
            gpu_available=gpu,
            gpu_status=EVAL_COMPLETED if gpu else EVAL_UNAVAILABLE,
        )

    recorded = durations[warm_up:]
    mn, mean, med = compute_stats(recorded)
    return BenchmarkResult(
        status=EVAL_COMPLETED,
        run_count=measured_runs,
        warm_up_count=warm_up,
        measured_runs=recorded,
        min_seconds=mn,
        mean_seconds=mean,
        median_seconds=med,
        cpu_available=True,
        gpu_available=gpu,
        gpu_status=EVAL_COMPLETED if gpu else EVAL_UNAVAILABLE,
    )
