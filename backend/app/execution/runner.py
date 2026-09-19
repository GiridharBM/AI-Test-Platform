"""Docker-based sandbox execution for generated test scaffolds.

Runs pytest inside an isolated Docker container with:
- No network access (--network none)
- Bounded memory, CPU, and timeout
- Read-only root with tmpfs /tmp
- Automatic container cleanup
"""

import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.core import config
from app.models.execution import (
    ExecutionSummary,
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
    TestExecutionResult,
    TestFileResult,
    TestFunctionResult,
)


class DockerUnavailable(Exception):
    """Raised when Docker is not accessible."""


# Pytest -v emits each status line with a trailing progress column, e.g.
# "tests/test_a.py::test_b FAILED [ 66%]". Strip it so the parsers match the
# per-test status keyword that is the parser contract.
_PROGRESS_RE = re.compile(r"\s+\[\s*\d+%\]\s*$")


_docker_probe_detail = ""  # exact reason for the last probe failure (never hidden)


def _docker_probe() -> tuple[bool, str]:
    """Run one ``docker info`` probe. Returns (available, detail); never raises."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, ""
        stderr = result.stderr.decode(errors="replace").strip()
        return False, stderr or f"docker info exited {result.returncode}"
    except FileNotFoundError:
        return False, "docker command not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out after 10s"


def _docker_available(retries: int | None = None) -> bool:
    """Check if the Docker CLI/daemon is accessible.

    A single transient probe miss (Docker Desktop resuming, WSL engine
    settling right after an image build / container teardown) must not hard-fail
    an otherwise healthy host, so the probe is retried a bounded number of
    times; it still fails closed when the daemon stays unreachable.
    """
    global _docker_probe_detail
    retries = config.EXECUTION_DOCKER_PROBE_RETRIES if retries is None else retries
    for attempt in range(retries + 1):
        ok, detail = _docker_probe()
        if ok:
            _docker_probe_detail = ""
            return True
        _docker_probe_detail = detail
        if attempt < retries:
            time.sleep(config.EXECUTION_DOCKER_PROBE_RETRY_DELAY)
    return False


def _ensure_image(image: str) -> None:
    """Build the test-runner image if it doesn't exist."""
    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        timeout=30,
    )
    if check.returncode == 0:
        return
    # Resolve dockerfile path relative to project root
    from app.core.config import BACKEND_DIR
    dockerfile = BACKEND_DIR.parent / config.EXECUTION_DOCKERFILE
    if not dockerfile.is_file():
        raise DockerUnavailable(f"Dockerfile not found: {dockerfile}")
    build = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        capture_output=True,
        timeout=300,
    )
    if build.returncode != 0:
        raise DockerUnavailable(
            f"Docker build failed: {build.stderr.decode(errors='replace')}"
        )


@dataclass
class SandboxCommandResult:
    """Outcome of one sandboxed command run."""

    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool


def _docker_run(
    container_name: str,
    test_path: str,
    source_path: str | None,
    entrypoint: str | None,
    command: list[str],
    timeout: int,
    memory_limit: str,
    cpu_limit: float,
    image: str,
) -> tuple[int, str, str, float, bool]:
    """Run a command through the shared sandboxed Docker execution path.

    Returns (returncode, stdout, stderr, duration_seconds, timed_out).

    This is the single place that builds a ``docker run`` argv, so M6
    (execute_tests) and every M10 evaluation component execute untrusted code
    under exactly the same isolation: no network, bounded memory/CPU/timeout,
    read-only root with a small tmpfs /tmp, read-only test/source mounts, and
    ``--rm`` cleanup.
    """
    exec_args = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "--network", "none",
        "--memory", memory_limit,
        "--cpus", str(cpu_limit),
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "-v", f"{test_path}:/tests:ro",
        "-w", "/tests",
    ]
    if source_path:
        exec_args += [
            "-v", f"{source_path}:/source:ro",
            "-e", "PYTHONPATH=/source",
        ]
    if entrypoint:
        exec_args += ["--entrypoint", entrypoint]
    exec_args += [image, *command]

    start = time.monotonic()
    try:
        result = subprocess.run(
            exec_args,
            capture_output=True,
            timeout=timeout + 10,  # extra buffer for Docker overhead
        )
        duration = round(time.monotonic() - start, 3)
        timed_out = False
    except subprocess.TimeoutExpired:
        duration = round(time.monotonic() - start, 3)
        timed_out = True
        # Best-effort container cleanup — ignore kill failures
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
        result = subprocess.CompletedProcess(args=[], returncode=-1, stdout=b"", stderr=b"")

    stdout = result.stdout.decode(errors="replace")[:config.EXECUTION_MAX_OUTPUT_BYTES]
    stderr = result.stderr.decode(errors="replace")[:config.EXECUTION_MAX_OUTPUT_BYTES]
    return result.returncode, stdout, stderr, duration, timed_out


def run_sandboxed_command(
    project_id: str,
    source_root: Path,
    test_dir: Path,
    entrypoint: list[str],
    args: list[str],
    timeout: int | None = None,
    memory_limit: str | None = None,
    cpu_limit: float | None = None,
    image: str | None = None,
) -> SandboxCommandResult:
    """Run a caller-supplied command inside the shared M6-security sandbox.

    `source_root` is mounted read-only at /source (PYTHONPATH=/source) and
    `test_dir` is mounted read-only at /tests. The caller supplies the container
    entrypoint and arguments; coverage, mutation, and benchmark all execute
    through this single path rather than re-implementing Docker lifecycle.

    Raises DockerUnavailable when Docker is unavailable or the image cannot be
    built.
    """
    timeout = timeout or config.EXECUTION_TIMEOUT_SECONDS
    memory_limit = memory_limit or f"{config.EXECUTION_MEMORY_LIMIT_MB}m"
    cpu_limit = cpu_limit if cpu_limit is not None else config.EXECUTION_CPU_LIMIT
    image = image or config.EXECUTION_IMAGE_NAME

    if not _docker_available():
        detail = f" Last probe: {_docker_probe_detail}" if _docker_probe_detail else ""
        raise DockerUnavailable(
            f"Docker is not available. Install and start Docker to evaluate.{detail}"
        )
    try:
        _ensure_image(image)
    except DockerUnavailable:
        raise
    except Exception as exc:  # defensive: never crash evaluation on infra
        raise DockerUnavailable(str(exc)) from exc

    if not test_dir.is_dir():
        raise DockerUnavailable("Test directory does not exist for measurement.")

    work_dir = Path(tempfile.mkdtemp(prefix="eval_"))
    try:
        test_dest = work_dir / "tests"
        shutil.copytree(test_dir, test_dest)

        source_dest = work_dir / "source"
        have_source = source_root is not None and source_root.is_dir()
        if have_source:
            shutil.copytree(source_root, source_dest, symlinks=False)
            _mirror_module_names(source_dest)

        returncode, stdout, stderr, duration, timed_out = _docker_run(
            container_name=f"eval_{project_id}",
            test_path=str(test_dest.resolve()),
            source_path=str(source_dest.resolve()) if have_source else None,
            entrypoint=entrypoint[0],
            command=[*entrypoint[1:], *args],
            timeout=timeout,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            image=image,
        )
        return SandboxCommandResult(returncode, stdout, stderr, duration, timed_out)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _mirror_module_names(src: Path) -> None:
    """Add importable qualname aliases (in place) under `src`.

    Improvement derives module names via ``improvement._module_from_path``,
    which sanitises every path component (``m11-demo/calc.py`` ->
    ``m11_demo.calc``). CPython's import machinery does NOT translate
    directory/file names, so the verbatim source copy can't satisfy those
    imports. This helper walks a snapshot of `src` and writes a twin tree in
    which every component is replaced by its module-safe spelling, mirroring
    exactly the rule used to build generated-test imports. Only aliases whose
    sanitised name differs are created; existing paths are never overwritten.
    """
    original = sorted(src.rglob("*")) if src.is_dir() else []
    for path in original:
        raw_parts = list(path.relative_to(src).parts)
        if path.is_file() and raw_parts[-1].endswith(".py"):
            raw_parts = raw_parts[:-1] + [raw_parts[-1][:-3]]
        sanitized = tuple(
            ("_" + p if p[0].isdigit() else p)
            for p in (re.sub(r"[^A-Za-z0-9_]", "_", p) for p in raw_parts)
            if p
        )
        if path.is_file() and sanitized:
            sanitized = sanitized[:-1] + (sanitized[-1] + ".py",)
        target = Path(src, *sanitized)
        if target == path or target.exists():
            continue
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _parse_pytest_output(stdout: str) -> tuple[int, int, int, int, int]:
    """Parse pytest -v output for passed/failed/error/skipped counts.

    Returns (passed, failed, errors, skipped, total_tests).
    """
    passed = failed = errors = skipped = 0
    # Match lines like: tests/test_foo.py::test_bar PASSED
    for line in stdout.splitlines():
        line = _PROGRESS_RE.sub("", line.rstrip()).rstrip()
        line = line.rstrip()
        if line.endswith(" PASSED"):
            passed += 1
        elif line.endswith(" FAILED"):
            failed += 1
        elif line.endswith(" ERROR"):
            errors += 1
        elif line.endswith(" SKIPPED"):
            skipped += 1
    return passed, failed, errors, skipped, passed + failed + errors + skipped


def _parse_file_results(stdout: str) -> dict[str, str]:
    """Parse pytest -v output into file → overall status mapping."""
    files: dict[str, str] = {}
    for line in stdout.splitlines():
        line = _PROGRESS_RE.sub("", line.rstrip()).rstrip()
        line = line.rstrip()
        if "::" not in line:
            continue
        part = line.split("::", 1)[0].strip()
        if line.endswith(" PASSED"):
            val = "passed"
        elif line.endswith(" FAILED"):
            val = "failed"
        elif line.endswith(" ERROR"):
            val = "error"
        elif line.endswith(" SKIPPED"):
            val = "skipped"
        else:
            continue
        # Worst status per file
        prev = files.get(part, "passed")
        priority = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}
        if priority.get(val, 0) > priority.get(prev, 0):
            files[part] = val
        else:
            files.setdefault(part, val)
    return files


# Per-test status line in pytest -v output (after stripping the trailing
# " [ 33%]" progress column): "<file>::<func> STATUS".
_TEST_STATUS_RE = re.compile(
    r"^(?P<file>\S+)::(?P<func>[^\s]+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED)$"
)


def _parse_test_functions(stdout: str) -> dict[str, list[TestFunctionResult]]:
    """Parse pytest -v output into file → ordered list of per-test results.

    Parses actual status tokens from pytest output; passed tests are included
    as real rows, never derived from aggregate counts. pytest -v reports no
    per-test duration, so `duration_seconds` stays None rather than inventing
    one. Returns {} when the output has no parseable per-test lines.
    """
    results: dict[str, list[TestFunctionResult]] = {}
    for line in stdout.splitlines():
        clean = _PROGRESS_RE.sub("", line.rstrip()).rstrip()
        match = _TEST_STATUS_RE.match(clean)
        if not match:
            continue
        file_path = match.group("file")
        func = match.group("func")
        status = match.group("status").lower()
        results.setdefault(file_path, []).append(
            TestFunctionResult(test_function=func, status=status)
        )
    return results


def execute_tests(
    generated_test_dir: Path,
    project_id: str,
    timeout: int | None = None,
    memory_limit: str | None = None,
    cpu_limit: float | None = None,
    image: str | None = None,
    source_root: Path | None = None,
) -> TestExecutionResult:
    """Execute generated tests inside a Docker sandbox.

    Args:
        generated_test_dir: Directory containing the generated test files.
        project_id: The project identifier.
        timeout: Override EXECUTION_TIMEOUT_SECONDS.
        memory_limit: Override Docker memory limit string (e.g. "512m").
        cpu_limit: Override EXECUTION_CPU_LIMIT.
        image: Override Docker image name.
        source_root: Override the default source directory mounted read-only at
            /source (PYTHONPATH=/source). M11 uses this to validate a repair
            candidate in an isolated workspace while reusing this single M6
            Docker execution path. Defaults to
            workspace/{project_id}/source.

    Returns:
        TestExecutionResult with structured execution information.
    """
    timeout = timeout or config.EXECUTION_TIMEOUT_SECONDS
    memory_limit = memory_limit or f"{config.EXECUTION_MEMORY_LIMIT_MB}m"
    cpu_limit = cpu_limit or config.EXECUTION_CPU_LIMIT
    image = image or config.EXECUTION_IMAGE_NAME

    if not _docker_available():
        detail = f" Last probe: {_docker_probe_detail}" if _docker_probe_detail else ""
        return TestExecutionResult(
            project_id=project_id,
            overall_status=STATUS_UNAVAILABLE,
            warnings=[
                "Docker is not available. Install and start Docker to execute tests."
                + detail
            ],
        )

    try:
        _ensure_image(image)
    except DockerUnavailable as exc:
        return TestExecutionResult(
            project_id=project_id,
            overall_status=STATUS_UNAVAILABLE,
            warnings=[str(exc)],
        )

    if not generated_test_dir.is_dir():
        return TestExecutionResult(
            project_id=project_id,
            overall_status=STATUS_ERROR,
            warnings=["Generated test directory does not exist."],
        )

    # Copy tests to a temp dir (Docker volume mount needs a real path).
    work_dir = Path(tempfile.mkdtemp(prefix="exec_"))
    try:
        test_dest = work_dir / "tests"
        shutil.copytree(generated_test_dir, test_dest)

        # Mount a READ-ONLY copy of the project source alongside the tests so
        # improved generated tests (e.g. `from app import add`) can import the
        # scanned code inside the sandbox. The copy lives in the same temp exec
        # dir and is mounted `:ro`; the host's real source is never mounted
        # directly and cannot be modified by the (read-only) container.
        source_dest = work_dir / "source"
        source_root = source_root or (Path(config.WORKSPACE_DIR) / project_id / "source")
        have_source = source_root.is_dir()
        if have_source:
            shutil.copytree(source_root, source_dest, symlinks=False)
            _mirror_module_names(source_dest)

        returncode, stdout, stderr, duration, timed_out = _docker_run(
            container_name=f"exec_{project_id}",
            test_path=str(test_dest.resolve()),
            source_path=str(source_dest.resolve()) if have_source else None,
            entrypoint=None,
            command=["-v", "--tb=short", "--no-header"],
            timeout=timeout,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            image=image,
        )

        if timed_out:
            return TestExecutionResult(
                project_id=project_id,
                overall_status=STATUS_TIMEOUT,
                exit_code=-1,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                warnings=[f"Execution timed out after {timeout}s."],
            )

        passed, failed, errors_count, skipped, total = _parse_pytest_output(stdout)
        file_statuses = _parse_file_results(stdout)
        per_test = _parse_test_functions(stdout)

        file_results = []
        for fpath in sorted(file_statuses.keys()):
            file_results.append(TestFileResult(
                file_path=fpath,
                status=file_statuses[fpath],
                test_functions=per_test.get(fpath, []),
            ))

        if returncode == 0:
            overall = STATUS_PASSED
        elif returncode == 5:
            overall = STATUS_PASSED  # pytest exit 5 = no tests collected
        else:
            overall = STATUS_FAILED if failed > 0 else STATUS_ERROR

        summary = ExecutionSummary(
            total_files=len(file_results),
            total_test_functions=total,
            passed=passed,
            failed=failed,
            errors=errors_count,
            skipped=skipped,
        )

        return TestExecutionResult(
            project_id=project_id,
            overall_status=overall,
            exit_code=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            summary=summary,
            file_results=file_results,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
