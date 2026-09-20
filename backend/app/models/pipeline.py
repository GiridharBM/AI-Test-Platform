"""Persistent pipeline state model for the sequential gated orchestrator.

The pipeline is a deterministic state machine that composes the existing
M1-M11 milestone services. State is persisted to ``.meta/pipeline.json``.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

PIPELINE_SCHEMA_VERSION = 1

# --- Overall pipeline status -------------------------------------------------
PIPELINE_RUNNING = "running"
PIPELINE_WAITING_USER = "waiting_for_user"
PIPELINE_WAITING_APPROVAL = "waiting_for_approval"
PIPELINE_COMPLETED = "completed"
PIPELINE_FAILED = "failed"
PIPELINE_BLOCKED = "blocked"
PIPELINE_UNAVAILABLE = "unavailable"
PIPELINE_REJECTED = "rejected"

# --- Per-stage status (history entries) --------------------------------------
STAGE_SUCCESS = "success"
STAGE_FAILED = "failed"
STAGE_BLOCKED = "blocked"
STAGE_UNAVAILABLE = "unavailable"
STAGE_SKIPPED = "skipped"
STAGE_APPROVED = "approved"
STAGE_REJECTED = "rejected"
STAGE_EXHAUSTED = "exhausted"
STAGE_IN_PROGRESS = "in_progress"

# --- Human decision gates ----------------------------------------------------
GATE_RETEST = "awaiting_retest_decision"
GATE_REPAIR = "awaiting_repair_decision"
GATE_APPROVAL = "awaiting_repair_approval"

GATE_RETEST_ACTIONS = ("retest", "skip_retest")
GATE_REPAIR_ACTIONS = ("repair", "skip_repair")
GATE_APPROVAL_ACTIONS = ("approve", "reject")


class StageRecord(BaseModel):
    """One persisted stage transition."""

    stage: str
    status: str
    start_time: datetime
    end_time: datetime
    result_id: str = ""
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)


class PipelineState(BaseModel):
    """Full persistent pipeline state for one project."""

    schema_version: int = PIPELINE_SCHEMA_VERSION
    project_id: str
    pipeline_id: str
    current_stage: str = ""
    overall_status: str = PIPELINE_RUNNING
    completed_stages: list[str] = Field(default_factory=list)
    stage_history: list[StageRecord] = Field(default_factory=list)
    current_improvement_round: int = 0
    maximum_improvement_rounds: int = 3
    user_decision_required: bool = False
    available_actions: list[str] = Field(default_factory=list)
    error: str = ""
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Set while a stage is actively executing (persisted at stage start), cleared
    # on completion. Used to detect an abandoned `running` pipeline (stuck).
    stage_started_at: Optional[datetime] = None