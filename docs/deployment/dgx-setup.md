# DGX B200 Setup Guide

Status: **PLANNED — NOT IMPLEMENTED**

## Overview

This document describes what must be validated on the DGX B200 environment before M17 implementation begins.

**Important:** Do not assume any DGX functionality works until validated. This document is a checklist of items to verify.

## Pre-Implementation Validation Checklist

### 1. Hardware & Drivers

- [ ] DGX B200 hardware accessible
- [ ] NVIDIA driver version documented
- [ ] CUDA toolkit version documented
- [ ] `nvidia-smi` returns GPU information
- [ ] GPU memory size documented

### 2. CUDA Compatibility

- [ ] CUDA version compatible with PyTorch
- [ ] CUDA version compatible with Hugging Face Transformers
- [ ] cuDNN installed and functional
- [ ] NCCL installed (for multi-GPU if applicable)

### 3. NVIDIA Container Toolkit

- [ ] NVIDIA Container Toolkit installed
- [ ] Docker configured with NVIDIA runtime
- [ ] `docker run --gpus all nvidia/cuda:12.0-base nvidia-smi` works
- [ ] GPU visible inside Docker containers

### 4. Docker/Container Runtime

- [ ] Docker Engine version documented
- [ ] Docker Compose version documented
- [ ] GPU resource limits work (`--gpus`, `--memory`)
- [ ] Container can allocate GPU memory

### 5. GPU Visibility

- [ ] `nvidia-smi` shows GPU inside container
- [ ] CUDA devices visible inside container
- [ ] GPU memory can be allocated
- [ ] GPU can be released after use

### 6. Networking

- [ ] Container networking functional
- [ ] Backend can reach Docker socket
- [ ] Frontend can reach backend
- [ ] No firewall blocking internal communication

### 7. Storage

- [ ] Workspace bind mount functional
- [ ] GPU model storage location identified
- [ ] Sufficient disk space for models
- [ ] Fast storage for model loading (NVMe preferred)

### 8. Permissions

- [ ] User has Docker group membership
- [ ] User can run `docker run --gpus`
- [ ] No root required for GPU access
- [ ] Container can run non-root with GPU

### 9. Scheduling/Allocation

- [ ] GPU allocation strategy defined (single vs shared)
- [ ] Concurrency limits documented
- [ ] Memory limits defined
- [ ] Cleanup on process exit verified

## Environment Variables

Once validated, these environment variables will be needed:

| Variable | Example | Description |
|---|---|---|
| `ATP_GPU_ENABLED` | `true` | Enable GPU acceleration |
| `ATP_GPU_DEVICE` | `0` | GPU device index |
| `ATP_GPU_MEMORY_LIMIT` | `8192` | Max GPU memory (MB) |
| `ATP_MODEL_PATH` | `/models` | Model storage location |

## Validation Commands

Run these commands on the DGX B200 environment:

```bash
# 1. Check GPU
nvidia-smi

# 2. Check CUDA
nvcc --version

# 3. Check Docker GPU support
docker run --gpus all nvidia/cuda:12.0-base nvidia-smi

# 4. Check Container Toolkit
docker info | grep -i nvidia

# 5. Check disk space
df -h /var/lib/ai-test-platform/workspace

# 6. Check Docker group
groups
stat -c '%g' /var/run/docker.sock
```

## Known Issues to Watch For

- **CUDA version mismatch** — PyTorch requires specific CUDA versions
- **GPU memory fragmentation** — allocate memory carefully
- **Container GPU passthrough** — verify `--gpus` flag works
- **Driver compatibility** — ensure driver supports CUDA version
- **Multi-process GPU access** — only one process can use GPU at a time (unless using MPS)

## Status

**PLANNED — NOT IMPLEMENTED**

This document is a checklist for validating the DGX B200 environment. No implementation has been done.
