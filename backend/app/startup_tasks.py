from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def resolve_persist_dir(path_value: str, *, workspace_root: str) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = (Path(workspace_root) / candidate).resolve()
    return candidate


def run_security_checks(*, settings, logger) -> None:
    """SEC: Startup security hardening checks."""
    # CRYPTO-03: Warn if 'cryptography' package is missing (XOR fallback is weak)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        logger.error(
            "SEC: 'cryptography' package not installed — encryption uses WEAK XOR fallback. "
            "Install with: pip install cryptography"
        )

    # CFG-06: Validate configuration at startup
    try:
        from app.config import validate_environment_config

        validation = validate_environment_config(settings)
        status = str(validation.get("validation_status", "ok"))
        if status != "ok":
            unknown_keys = list(validation.get("unknown_keys") or [])
            logger.warning(
                "SEC: Config validation status=%s unknown_keys=%s",
                status,
                unknown_keys,
            )
    except Exception:
        logger.debug("startup_config_validation_error", exc_info=True)

    # CFG-04: Warn about deprecated OLLAMA_API_KEY
    if os.getenv("OLLAMA_API_KEY") and not os.getenv("LLM_API_KEY"):
        logger.warning("SEC: OLLAMA_API_KEY is deprecated. Use LLM_API_KEY instead.")

    # CFG-02: Check .env file permissions on Linux
    env_file = Path(".env")
    if env_file.exists() and os.name != "nt":
        import stat

        mode = env_file.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            logger.warning("SEC: .env file is readable by group/others. Run: chmod 600 .env")


def clear_startup_persistence(*, settings, logger) -> None:
    if settings.memory_reset_on_startup:
        memory_dir = resolve_persist_dir(settings.memory_persist_dir, workspace_root=settings.workspace_root)
        memory_dir.mkdir(parents=True, exist_ok=True)
        removed_files = 0
        for file_path in memory_dir.glob("*.jsonl"):
            try:
                file_path.unlink(missing_ok=True)
                removed_files += 1
            except Exception:
                logger.debug("memory_file_cleanup_failed file=%s", file_path, exc_info=True)
        logger.info("startup_memory_reset enabled=%s removed_files=%s", settings.memory_reset_on_startup, removed_files)

    if settings.orchestrator_state_reset_on_startup:
        state_dir = resolve_persist_dir(settings.orchestrator_state_dir, workspace_root=settings.workspace_root)
        runs_dir = state_dir / "runs"
        snapshots_dir = state_dir / "snapshots"
        runs_dir.mkdir(parents=True, exist_ok=True)
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        removed_runs = 0
        removed_snapshots = 0
        for file_path in runs_dir.glob("*.json"):
            try:
                file_path.unlink(missing_ok=True)
                removed_runs += 1
            except Exception:
                logger.debug("state_run_cleanup_failed file=%s", file_path, exc_info=True)
        for file_path in snapshots_dir.glob("*.json"):
            try:
                file_path.unlink(missing_ok=True)
                removed_snapshots += 1
            except Exception:
                logger.debug("state_snapshot_cleanup_failed file=%s", file_path, exc_info=True)
        logger.info(
            "startup_state_reset enabled=%s removed_runs=%s removed_snapshots=%s",
            settings.orchestrator_state_reset_on_startup,
            removed_runs,
            removed_snapshots,
        )


def log_startup_paths(*, settings, logger) -> None:
    runtime_file = Path(settings.runtime_state_file)
    if not runtime_file.is_absolute():
        runtime_file = (Path(settings.workspace_root) / runtime_file).resolve()

    logger.info(
        "startup_paths workspace_root=%s memory_dir=%s orchestrator_state_dir=%s runtime_state_file=%s",
        Path(settings.workspace_root).resolve(),
        resolve_persist_dir(settings.memory_persist_dir, workspace_root=settings.workspace_root),
        resolve_persist_dir(settings.orchestrator_state_dir, workspace_root=settings.workspace_root),
        runtime_file,
    )


def run_startup_sequence(*, settings, logger, ensure_runtime_components_initialized: Callable[[], object]) -> None:
    run_security_checks(settings=settings, logger=logger)
    log_startup_paths(settings=settings, logger=logger)
    clear_startup_persistence(settings=settings, logger=logger)
    ensure_runtime_components_initialized()


def run_shutdown_sequence(*, active_run_tasks: dict, logger) -> None:
    cancelled = 0
    for _, task in list(active_run_tasks.items()):
        if task.done():
            continue
        task.cancel()
        cancelled += 1
    active_run_tasks.clear()
    logger.info("shutdown_cleanup cancelled_active_runs=%s", cancelled)
