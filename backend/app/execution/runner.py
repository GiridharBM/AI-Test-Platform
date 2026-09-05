"""Docker-based sandbox execution for generated test scaffolds.

Runs pytest inside an isolated Docker container with:
- No network access (--network none)
- Bounded memory, CPU, and timeout
- Read-only root with tmpfs /tmp
- Automatic container cleanup
"""

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
)


class DockerUnavailable(Exception):
    """Raised when Docker is not accessible."""


def _docker_available() -> bool:
    """Check if Docker CLI is accessible."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
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
        raise DockerUnavailable("Docker is not available. Install and start Docker to evaluate.")
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


def _parse_pytest_output(stdout: str) -> tuple[int, int, int, int, int]:
    """Parse pytest -v output for passed/failed/error/skipped counts.

    Returns (passed, failed, errors, skipped, total_tests).
    """
    passed = failed = errors = skipped = 0
    # Match lines like: tests/test_foo.py::test_bar PASSED
    for line in stdout.splitlines():
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


def execute_tests(
    generated_test_dir: Path,
    project_id: str,
    timeout: int | None = None,
    memory_limit: str | None = None,
    cpu_limit: float | None = None,
    image: str | None = None,
) -> TestExecutionResult:
    """Execute generated tests inside a Docker sandbox.

    Args:
        generated_test_dir: Directory containing the generated test files.
        project_id: The project identifier.
        timeout: Override EXECUTION_TIMEOUT_SECONDS.
        memory_limit: Override Docker memory limit string (e.g. "512m").
        cpu_limit: Override EXECUTION_CPU_LIMIT.
        image: Override Docker image name.

    Returns:
        TestExecutionResult with structured execution information.
    """
    timeout = timeout or config.EXECUTION_TIMEOUT_SECONDS
    memory_limit = memory_limit or f"{config.EXECUTION_MEMORY_LIMIT_MB}m"
    cpu_limit = cpu_limit or config.EXECUTION_CPU_LIMIT
    image = image or config.EXECUTION_IMAGE_NAME

    if not _docker_available():
        return TestExecutionResult(
            project_id=project_id,
            overall_status=STATUS_UNAVAILABLE,
            warnings=["Docker is not available. Install and start Docker to execute tests."],
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
        source_root = Path(config.WORKSPACE_DIR) / project_id / "source"
        have_source = source_root.is_dir()
        if have_source:
            shutil.copytree(source_root, source_dest, symlinks=False)

        returncode, stdout, stderr, duration, timed_out = _docker_run(
            container_name=f"exec_{project_id}",
            test_path=str(test_dest.resolve()),
            source_path=str(source_dest.resolve()) if have_source else None,
            entrypoint=None,
            command=["-v", "--tb=short", "--no-header", "-q"],
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

        file_results = []
        for fpath in sorted(file_statuses.keys()):
            file_results.append(TestFileResult(
                file_path=fpath,
                status=file_statuses[fpath],
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
