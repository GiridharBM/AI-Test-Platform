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

        container_name = f"exec_{project_id}"
        abs_tests = str(test_dest.resolve())

        start = time.monotonic()
        try:
            result = subprocess.run(
                [
                    "docker", "run",
                    "--rm",
                    "--name", container_name,
                    "--network", "none",
                    "--memory", memory_limit,
                    "--cpus", str(cpu_limit),
                    "--read-only",
                    "--tmpfs", "/tmp:size=64m",
                    "-v", f"{abs_tests}:/tests:ro",
                    "-w", "/tests",
                    image,
                    "-v", "--tb=short", "--no-header", "-q",
                ],
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

        if result.returncode == 0:
            overall = STATUS_PASSED
        elif result.returncode == 5:
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
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            summary=summary,
            file_results=file_results,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
