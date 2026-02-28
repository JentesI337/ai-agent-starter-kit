# 🛠 Backend Refactoring — Instructions & Outcome Guide

## 📌 Project Context

The current backend contains a functional coding agent but suffers from:
- Poor scalability under increased load or task complexity
- Reliability failures in multi-step pipelines
- No structured model tier routing
- State management leaking into prompts and model memory

This refactoring does **not** replace the existing agent logic.
It rebuilds the **architecture around it**.

---

## 🎯 Refactoring Goal

> Build a constraint-first, model-agnostic orchestration system
> that scales from cheap 7B models to GPT-4-class models
> **without requiring architectural redesign at any stage.**

---

## 🔑 Core Principles

- Design for constraint first — scale is an upgrade, not a rebuild
- Logic lives in code — models are reasoning engines only
- External state is the single source of truth
- Every agent has a strict, explicit contract
- Flows are linear and deterministic until proven stable

---

## 🏗 Architecture Overview

### Agent Contracts

Every agent in the system **must** define:

| Field           | Description                          |
|-----------------|--------------------------------------|
| `role`          | Single clear responsibility          |
| `input_schema`  | Typed, validated input definition    |
| `output_schema` | Typed, structured output (JSON only) |
| `constraints`   | Context limit, temp, reflection cap  |

**No cross-agent implicit knowledge.**
**No shared memory between agents.**

---

### External State Manager

The orchestrator owns all state. Models never do.

Required components:

- **State Store** — Redis / DB / JSON file (environment-dependent)
- **Task Graph** — directed graph of pending, active, completed tasks
- **Context Reducer** — trims and prioritizes context per token budget
- **Summary Snapshots** — compressed state checkpoints for rehydration

> Models receive **slices** of state only.
> They never read or write to the full state directly.

---

### Model Capability Profiles

Each model is registered with a capability profile:

```json
{
  "model_id": "model-identifier",
  "max_context": 8000,
  "reasoning_depth": 2,
  "reflection_passes": 0,
  "combine_steps": false,
  "temperature": 0.3
}
