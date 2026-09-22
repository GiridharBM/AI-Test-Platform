# AI Inference Architecture

Status: **PLANNED — NOT IMPLEMENTED**

## Overview

This document describes the planned AI inference layer for the AI Test Platform.

## Current State (No AI Inference)

The platform currently uses deterministic algorithms for all pipeline stages:

- **M7 (Diagnose):** Rule-based failure classification and source mapping
- **M8 (Improve):** Template-based test scaffold regeneration
- **M10 (Evaluate):** AST-based mutation testing

No LLM inference, no model serving, no GPU acceleration.

## Planned AI Inference Layer

### Architecture

```
┌─────────────────────────────────────────┐
│ Application Layer                       │
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │ Diagnose │  │ Improve  │  │ Future ││
│  │ (M7)     │  │ (M8)     │  │        ││
│  └────┬─────┘  └────┬─────┘  └───┬────┘│
│       │              │            │      │
│  ┌────▼──────────────▼────────────▼────┐│
│  │ AI Inference API                    ││
│  │  - analyze(context) -> findings     ││
│  │  - suggest_fix(context) -> patches  ││
│  └─────────────────┬──────────────────┘│
│                    │                    │
│  ┌─────────────────▼──────────────────┐│
│  │ Model Server (local)               ││
│  │  - PyTorch + HF Transformers       ││
│  │  - GPU acceleration (CUDA)         ││
│  │  - Batch inference                 ││
│  └────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

### Interface

The AI inference layer exposes a simple interface:

```python
class AIInference:
    def analyze(self, context: str) -> PotentialBug | None:
        """Analyze test failure context and suggest potential bugs."""
        ...

    def suggest_fix(self, context: str, findings: list[Finding]) -> list[Patch]:
        """Suggest code fixes based on failure analysis."""
        ...
```

### Implementation Strategy

1. **Deterministic core first** — existing M7/M8 deterministic logic remains
2. **AI supplementation** — AI findings are added alongside deterministic findings
3. **Fallback** — if AI inference fails, deterministic results are returned
4. **Opt-in** — AI inference is controlled by `DIAGNOSIS_AI_ENABLED` / `IMPROVE_AI_ENABLED` flags (default: False)

## Privacy Model

- **Local inference only** — no external API calls
- **No data logging** — inference inputs/outputs are not persisted beyond the request
- **Model isolation** — each inference request is independent
- **Audit trail** — inference usage is logged for monitoring

## Model Selection

Planned models for coding tasks:

- **CodeLlama** — Meta's code-specific LLM
- **StarCoder** — BigCode's open-source coding model
- **DeepSeek-Coder** — DeepSeek's coding model
- **Qwen2.5-Coder** — Alibaba's coding model

Selection criteria:

1. Must run locally (no API dependency)
2. Must support the target languages (Python, Java, JS/TS)
3. Must fit in available GPU memory
4. Must produce structured output

## Status

**PLANNED — NOT IMPLEMENTED**

No AI inference code exists in the codebase. This document describes the intended architecture for M17.
