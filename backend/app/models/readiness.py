"""Readiness report model for GET /ready."""

from typing import Literal

from pydantic import BaseModel


class ReadinessChecks(BaseModel):
    workspace: bool = False
    runtime: bool = False


class ReadinessReport(BaseModel):
    status: Literal["ready", "not_ready"] = "not_ready"
    checks: ReadinessChecks = ReadinessChecks()