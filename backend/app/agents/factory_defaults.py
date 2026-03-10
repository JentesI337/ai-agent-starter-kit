"""Factory default definitions for all built-in agents.

This module replaces ``agent_definition.py``.  It provides the canonical
default values that are written to disk on first startup and restored
on factory-reset.  The actual runtime state lives in JSON files managed
by :class:`~app.agents.agent_store.UnifiedAgentStore`.
"""
from __future__ import annotations

from app.agents.unified_agent_record import (
    BehaviorFlags,
    ConstraintSpec,
    DelegationSpec,
    PromptSpec,
    ToolPolicySpec,
    UnifiedAgentRecord,
)

# ---------------------------------------------------------------------------
# Shared deny lists
# ---------------------------------------------------------------------------

_WRITE_DENY = [
    "write_file", "apply_patch", "run_command",
    "code_execute", "start_background_command", "kill_background_process",
]

# ---------------------------------------------------------------------------
# Commonly-referenced agent IDs
# ---------------------------------------------------------------------------

PRIMARY_AGENT_ID: str = "head-agent"
CODER_AGENT_ID: str = "coder-agent"
REVIEW_AGENT_ID: str = "review-agent"

# ---------------------------------------------------------------------------
# Factory defaults — the canonical starting point for each built-in agent
# ---------------------------------------------------------------------------

FACTORY_DEFAULTS: dict[str, UnifiedAgentRecord] = {
    # ── Core ──────────────────────────────────────────────
    "head-agent": UnifiedAgentRecord(
        agent_id="head-agent",
        origin="builtin",
        display_name="Head Agent",
        description="Coordinator that distributes work to specialists. Prefers delegation over doing work itself.",
        category="core",
        role="coordinator",
        reasoning_strategy="plan_execute",
        specialization="orchestration",
        capabilities=[
            "general_reasoning", "coordination", "fallback",
            "delegation", "planning", "synthesis",
        ],
        constraints=ConstraintSpec(temperature=0.3, reflection_passes=0, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=["spawn_subrun", "web_search", "web_fetch"],
        ),
        prompts=PromptSpec(
            fallback_system_key="head_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="head_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=8,
            confidence_threshold=0.6,
            delegation_preference="eager",
            max_concurrent_tasks=3,
            supports_parallel=True,
            supports_delegation=True,
        ),
        cost_tier="standard",
        latency_tier="standard",
        quality_tier="high",
    ),
    "coder-agent": UnifiedAgentRecord(
        agent_id="coder-agent",
        origin="builtin",
        display_name="Coder Agent",
        description="Deep coding specialist. Reads, writes, and executes code. Does not delegate.",
        category="core",
        role="specialist",
        reasoning_strategy="depth_first",
        specialization="software engineering",
        capabilities=[
            "code_reasoning", "code_modification", "command_execution",
            "tooling", "debugging", "testing", "refactoring",
        ],
        constraints=ConstraintSpec(temperature=0.3, reflection_passes=0, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "write_file", "apply_patch", "run_command",
                "code_execute", "grep_search", "file_search", "list_code_usages",
            ],
            forbidden_tools=["spawn_subrun"],
        ),
        prompts=PromptSpec(
            fallback_system_key="coder_agent_system_prompt",
            fallback_plan_key="coder_agent_plan_prompt",
            fallback_tool_selector_key="coder_agent_tool_selector_prompt",
            fallback_tool_repair_key="coder_agent_tool_repair_prompt",
            fallback_final_key="coder_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=7,
            confidence_threshold=0.7,
            delegation_preference="reluctant",
        ),
    ),
    "review-agent": UnifiedAgentRecord(
        agent_id="review-agent",
        origin="builtin",
        display_name="Review Agent",
        description="Read-only reviewer. Analyzes code for quality, security, performance. Never modifies files.",
        category="core",
        role="reviewer",
        reasoning_strategy="verify_first",
        specialization="code review & security analysis",
        capabilities=[
            "review_analysis", "security_review", "quality_review",
            "read_only", "code_reasoning",
        ],
        constraints=ConstraintSpec(temperature=0.2, reflection_passes=1, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_code_usages", "list_dir",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command", "spawn_subrun",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="head_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="head_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=5,
            confidence_threshold=0.8,
            delegation_preference="reluctant",
        ),
        behavior=BehaviorFlags(require_review_evidence=True),
        cost_tier="cheap",
    ),

    # ── Specialists ───────────────────────────────────────
    "researcher-agent": UnifiedAgentRecord(
        agent_id="researcher-agent",
        origin="builtin",
        display_name="Research Agent",
        description="Research specialist. Searches web, reads files, synthesizes findings with source citations. Read-only.",
        category="specialist",
        role="researcher",
        reasoning_strategy="breadth_first",
        specialization="information retrieval & synthesis",
        capabilities=[
            "deep_research", "web_research", "analysis", "synthesis",
            "fact_checking", "web_retrieval", "knowledge_retrieval",
            "research", "information_synthesis",
        ],
        constraints=ConstraintSpec(
            temperature=0.25, reflection_passes=1, reasoning_depth=3, max_context=16384,
        ),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "web_search", "web_fetch", "http_request",
                "read_file", "grep_search", "file_search", "list_dir",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="researcher_agent_system_prompt",
            fallback_plan_key="researcher_agent_plan_prompt",
            fallback_tool_selector_key="researcher_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="researcher_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.6,
            delegation_preference="reluctant",
            max_concurrent_tasks=2,
            supports_parallel=True,
        ),
        cost_tier="cheap",
        latency_tier="fast",
        quality_tier="standard",
    ),
    "architect-agent": UnifiedAgentRecord(
        agent_id="architect-agent",
        origin="builtin",
        display_name="Architect Agent",
        description="Architecture specialist. Analyzes structures, identifies trade-offs, delivers ADRs. Read-only, delegates code changes.",
        category="specialist",
        role="specialist",
        reasoning_strategy="plan_execute",
        specialization="software architecture & design",
        capabilities=[
            "architecture_analysis", "system_design", "trade_off_analysis",
            "adr_creation", "refactoring_planning", "read_only",
        ],
        constraints=ConstraintSpec(
            temperature=0.35, reflection_passes=2, reasoning_depth=4, max_context=12288,
        ),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "list_code_usages",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="architect_agent_system_prompt",
            fallback_plan_key="architect_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="architect_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=7,
            confidence_threshold=0.75,
            delegation_preference="selective",
            supports_delegation=True,
        ),
    ),
    "test-agent": UnifiedAgentRecord(
        agent_id="test-agent",
        origin="builtin",
        display_name="Test Agent",
        description="Test specialist. Writes tests, runs them, analyzes coverage, finds edge cases. Test-runner whitelisted.",
        category="specialist",
        role="specialist",
        reasoning_strategy="verify_first",
        specialization="testing & quality assurance",
        capabilities=[
            "test_generation", "test_execution", "coverage_analysis",
            "edge_case_discovery", "regression_testing",
        ],
        constraints=ConstraintSpec(temperature=0.15, reflection_passes=1, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            mandatory_deny=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "code_execute", "run_command",
            ],
            forbidden_tools=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="test_agent_system_prompt",
            fallback_plan_key="test_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="test_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.8,
            delegation_preference="reluctant",
        ),
        behavior=BehaviorFlags(
            command_allowlist_regex=r"^\s*(pytest|python\s+-m\s+pytest|npm\s+test|npx\s+jest|cargo\s+test|go\s+test|dotnet\s+test)",
            custom_deny_override=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
        ),
    ),
    "security-agent": UnifiedAgentRecord(
        agent_id="security-agent",
        origin="builtin",
        display_name="Security Agent",
        description="Security reviewer. Scans for vulnerabilities, audits dependencies, detects secrets. Read-only.",
        category="specialist",
        role="reviewer",
        reasoning_strategy="depth_first",
        specialization="security analysis & auditing",
        capabilities=[
            "security_review", "vulnerability_analysis", "dependency_audit",
            "secret_detection", "owasp_analysis", "read_only",
        ],
        constraints=ConstraintSpec(temperature=0.1, reflection_passes=2, reasoning_depth=3),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=[
                "write_file", "apply_patch", "code_execute",
                "start_background_command", "kill_background_process",
            ],
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "list_code_usages",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "code_execute",
                "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="security_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="security_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=5,
            confidence_threshold=0.85,
            delegation_preference="reluctant",
        ),
        behavior=BehaviorFlags(relaxed_deny=["run_command"]),
    ),
    "doc-agent": UnifiedAgentRecord(
        agent_id="doc-agent",
        origin="builtin",
        display_name="Doc Agent",
        description="Documentation specialist. Generates API docs, READMEs, changelogs, architecture diagrams.",
        category="specialist",
        role="specialist",
        reasoning_strategy="breadth_first",
        specialization="technical documentation",
        capabilities=[
            "documentation", "api_docs", "readme_generation",
            "changelog", "architecture_diagrams", "comment_quality",
        ],
        constraints=ConstraintSpec(temperature=0.4, reflection_passes=1, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            mandatory_deny=[
                "apply_patch", "run_command", "code_execute",
                "start_background_command", "kill_background_process",
            ],
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "write_file",
            ],
            forbidden_tools=[
                "apply_patch", "run_command", "code_execute",
                "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="doc_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="doc_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.65,
            delegation_preference="reluctant",
        ),
        behavior=BehaviorFlags(
            custom_deny_override=[
                "apply_patch", "run_command", "code_execute",
                "start_background_command", "kill_background_process",
            ],
        ),
    ),
    "refactor-agent": UnifiedAgentRecord(
        agent_id="refactor-agent",
        origin="builtin",
        display_name="Refactor Agent",
        description="Refactoring specialist. Detects code smells, plans safe refactorings, validates with tests.",
        category="specialist",
        role="specialist",
        reasoning_strategy="plan_execute",
        specialization="code refactoring & improvement",
        capabilities=[
            "refactoring", "code_smell_detection", "pattern_application",
            "safe_transformation", "test_validation",
        ],
        constraints=ConstraintSpec(temperature=0.2, reflection_passes=2, reasoning_depth=3),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "write_file", "apply_patch", "run_command",
                "code_execute", "list_code_usages",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="refactor_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="refactor_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.8,
            delegation_preference="selective",
            supports_delegation=True,
        ),
    ),
    "devops-agent": UnifiedAgentRecord(
        agent_id="devops-agent",
        origin="builtin",
        display_name="DevOps Agent",
        description="DevOps specialist. CI/CD pipelines, containerization, infrastructure-as-code, deployment strategies.",
        category="specialist",
        role="specialist",
        reasoning_strategy="plan_execute",
        specialization="devops & infrastructure",
        capabilities=[
            "ci_cd", "containerization", "infrastructure",
            "deployment", "performance_profiling", "monitoring_setup",
        ],
        constraints=ConstraintSpec(temperature=0.2, reflection_passes=1, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "write_file", "run_command",
            ],
            forbidden_tools=["code_execute", "start_background_command"],
        ),
        prompts=PromptSpec(
            fallback_system_key="devops_agent_system_prompt",
            fallback_plan_key="head_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="devops_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.7,
            delegation_preference="reluctant",
        ),
        quality_tier="standard",
    ),

    # ── Industry ──────────────────────────────────────────
    "fintech-agent": UnifiedAgentRecord(
        agent_id="fintech-agent",
        origin="builtin",
        display_name="FinTech Agent",
        description="FinTech domain expert. Analyzes payment flows, ledger designs, compliance with PCI-DSS/PSD2/MiFID II. Read-only.",
        category="industry",
        role="specialist",
        reasoning_strategy="analytical",
        specialization="financial technology & compliance",
        capabilities=[
            "fintech_compliance", "payment_flow_analysis", "audit_trail_review",
            "fraud_detection", "ledger_design", "pci_dss", "psd2", "read_only",
        ],
        constraints=ConstraintSpec(
            temperature=0.15, reflection_passes=2, reasoning_depth=4, max_context=16384,
        ),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "list_code_usages",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="fintech_agent_system_prompt",
            fallback_plan_key="fintech_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="fintech_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=5,
            confidence_threshold=0.85,
            delegation_preference="reluctant",
        ),
    ),
    "healthtech-agent": UnifiedAgentRecord(
        agent_id="healthtech-agent",
        origin="builtin",
        display_name="HealthTech Agent",
        description="HealthTech domain expert. Analyzes PHI/PII flows, HIPAA/GDPR compliance, HL7 FHIR interfaces. Strictly read-only.",
        category="industry",
        role="specialist",
        reasoning_strategy="depth_first",
        specialization="health technology & regulatory compliance",
        capabilities=[
            "healthtech_compliance", "phi_protection", "hipaa", "gdpr_health",
            "hl7_fhir", "dicom", "clinical_workflow", "anonymization", "read_only",
        ],
        constraints=ConstraintSpec(
            temperature=0.1, reflection_passes=2, reasoning_depth=4, max_context=16384,
        ),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "list_code_usages",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="healthtech_agent_system_prompt",
            fallback_plan_key="healthtech_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="healthtech_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=4,
            confidence_threshold=0.9,
            delegation_preference="reluctant",
        ),
    ),
    "legaltech-agent": UnifiedAgentRecord(
        agent_id="legaltech-agent",
        origin="builtin",
        display_name="LegalTech Agent",
        description="LegalTech domain expert. Analyzes GDPR/CCPA/AI-Act compliance, scans OSS licenses, performs DPIAs. Read-only.",
        category="industry",
        role="specialist",
        reasoning_strategy="analytical",
        specialization="legal technology & compliance",
        capabilities=[
            "legal_compliance", "gdpr", "ccpa", "ai_act", "license_scanning",
            "dpia", "data_transfer_assessment", "cookie_consent", "read_only",
        ],
        constraints=ConstraintSpec(
            temperature=0.15, reflection_passes=2, reasoning_depth=3, max_context=12288,
        ),
        tool_policy=ToolPolicySpec(
            read_only=True,
            mandatory_deny=_WRITE_DENY,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "list_code_usages",
            ],
            forbidden_tools=[
                "write_file", "apply_patch", "run_command",
                "code_execute", "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="legaltech_agent_system_prompt",
            fallback_plan_key="legaltech_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="legaltech_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=5,
            confidence_threshold=0.85,
            delegation_preference="reluctant",
        ),
    ),
    "ecommerce-agent": UnifiedAgentRecord(
        agent_id="ecommerce-agent",
        origin="builtin",
        display_name="E-Commerce Agent",
        description="E-Commerce domain expert. Designs catalogs, checkout flows, order processing, SEO. Read + write access.",
        category="industry",
        role="specialist",
        reasoning_strategy="breadth_first",
        specialization="e-commerce & retail technology",
        capabilities=[
            "ecommerce_design", "catalog_modeling", "checkout_flow",
            "order_processing", "seo_optimization", "pricing_engine",
            "inventory_management", "structured_data",
        ],
        constraints=ConstraintSpec(temperature=0.25, reflection_passes=1, reasoning_depth=3),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "write_file", "run_command",
            ],
            forbidden_tools=["code_execute", "start_background_command"],
        ),
        prompts=PromptSpec(
            fallback_system_key="ecommerce_agent_system_prompt",
            fallback_plan_key="ecommerce_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="ecommerce_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=6,
            confidence_threshold=0.7,
            delegation_preference="reluctant",
        ),
        quality_tier="standard",
    ),
    "industrytech-agent": UnifiedAgentRecord(
        agent_id="industrytech-agent",
        origin="builtin",
        display_name="IndustryTech Agent",
        description="IndustryTech domain expert. Analyzes IoT protocols, sensor pipelines, predictive maintenance, IEC 62443 safety. Read + restricted commands.",
        category="industry",
        role="specialist",
        reasoning_strategy="analytical",
        specialization="industrial IoT & manufacturing",
        capabilities=[
            "iot_analysis", "mqtt", "opcua", "predictive_maintenance",
            "digital_twin", "edge_computing", "iec_62443", "time_series",
        ],
        constraints=ConstraintSpec(
            temperature=0.2, reflection_passes=1, reasoning_depth=3, max_context=16384,
        ),
        tool_policy=ToolPolicySpec(
            read_only=False,
            mandatory_deny=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "run_command", "code_execute",
            ],
            forbidden_tools=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
        ),
        prompts=PromptSpec(
            fallback_system_key="industrytech_agent_system_prompt",
            fallback_plan_key="industrytech_agent_plan_prompt",
            fallback_tool_selector_key="head_agent_tool_selector_prompt",
            fallback_tool_repair_key="head_agent_tool_repair_prompt",
            fallback_final_key="industrytech_agent_final_prompt",
        ),
        delegation=DelegationSpec(
            autonomy_level=5,
            confidence_threshold=0.8,
            delegation_preference="reluctant",
        ),
        behavior=BehaviorFlags(
            custom_deny_override=[
                "write_file", "apply_patch",
                "start_background_command", "kill_background_process",
            ],
        ),
    ),
}


def get_factory_default(agent_id: str) -> UnifiedAgentRecord | None:
    """Look up a factory default by agent ID."""
    return FACTORY_DEFAULTS.get((agent_id or "").strip().lower())


def get_all_factory_agent_ids() -> list[str]:
    """Return all factory-default agent IDs in sorted order."""
    return sorted(FACTORY_DEFAULTS.keys())
