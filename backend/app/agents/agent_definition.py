"""Single source of truth for all built-in agent definitions.

Every duplicated agent constant (constraints, capabilities, tool policies,
prompt mappings, identity metadata) is consolidated here. Other modules
derive their data from ``BUILTIN_AGENT_DEFINITIONS`` instead of maintaining
their own copies.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ToolPolicySpec(BaseModel):
    """Declarative tool access rules for an agent."""
    read_only: bool = False
    mandatory_deny: list[str] = []
    preferred_tools: list[str] = []
    forbidden_tools: list[str] = []


class ConstraintDefaults(BaseModel):
    """Default runtime constraint values for an agent."""
    temperature: float = 0.3
    reflection_passes: int = 0
    reasoning_depth: int = 2
    max_context: int | None = None


class PromptMapping(BaseModel):
    """Maps an agent to its prompt settings keys in ``app.config.settings``."""
    system_prompt_key: str
    plan_prompt_key: str
    tool_selector_prompt_key: str
    tool_repair_prompt_key: str
    final_prompt_key: str


class AgentDefinition(BaseModel):
    """Complete, canonical definition of a built-in agent."""
    agent_id: str
    display_name: str
    description: str
    category: Literal["core", "specialist", "industry"]
    role: str
    reasoning_strategy: str
    specialization: str = ""
    capabilities: list[str]
    constraints: ConstraintDefaults
    tool_policy: ToolPolicySpec
    prompt_mapping: PromptMapping
    autonomy_level: int = 5
    confidence_threshold: float = 0.7
    delegation_preference: str = "selective"


# ---------------------------------------------------------------------------
# Canonical definitions — the ONLY place these values live
# ---------------------------------------------------------------------------

_WRITE_DENY = [
    "write_file", "apply_patch", "run_command",
    "code_execute", "start_background_command", "kill_background_process",
]

BUILTIN_AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    # ── Core ──────────────────────────────────────────────
    "head-agent": AgentDefinition(
        agent_id="head-agent",
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
        constraints=ConstraintDefaults(temperature=0.3, reflection_passes=0, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=["spawn_subrun", "web_search", "web_fetch"],
        ),
        prompt_mapping=PromptMapping(
            system_prompt_key="head_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="head_agent_final_prompt",
        ),
        autonomy_level=8,
        confidence_threshold=0.6,
        delegation_preference="eager",
    ),
    "coder-agent": AgentDefinition(
        agent_id="coder-agent",
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
        constraints=ConstraintDefaults(temperature=0.3, reflection_passes=0, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "write_file", "apply_patch", "run_command",
                "code_execute", "grep_search", "file_search", "list_code_usages",
            ],
            forbidden_tools=["spawn_subrun"],
        ),
        prompt_mapping=PromptMapping(
            system_prompt_key="coder_agent_system_prompt",
            plan_prompt_key="coder_agent_plan_prompt",
            tool_selector_prompt_key="coder_agent_tool_selector_prompt",
            tool_repair_prompt_key="coder_agent_tool_repair_prompt",
            final_prompt_key="coder_agent_final_prompt",
        ),
        autonomy_level=7,
        confidence_threshold=0.7,
        delegation_preference="reluctant",
    ),
    "review-agent": AgentDefinition(
        agent_id="review-agent",
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
        constraints=ConstraintDefaults(temperature=0.2, reflection_passes=1, reasoning_depth=2),
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
        # review-agent intentionally uses head-agent prompts
        prompt_mapping=PromptMapping(
            system_prompt_key="head_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="head_agent_final_prompt",
        ),
        autonomy_level=5,
        confidence_threshold=0.8,
        delegation_preference="reluctant",
    ),

    # ── Specialists ───────────────────────────────────────
    "researcher-agent": AgentDefinition(
        agent_id="researcher-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="researcher_agent_system_prompt",
            plan_prompt_key="researcher_agent_plan_prompt",
            tool_selector_prompt_key="researcher_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="researcher_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.6,
        delegation_preference="reluctant",
    ),
    "architect-agent": AgentDefinition(
        agent_id="architect-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="architect_agent_system_prompt",
            plan_prompt_key="architect_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="architect_agent_final_prompt",
        ),
        autonomy_level=7,
        confidence_threshold=0.75,
        delegation_preference="selective",
    ),
    "test-agent": AgentDefinition(
        agent_id="test-agent",
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
        constraints=ConstraintDefaults(temperature=0.15, reflection_passes=1, reasoning_depth=2),
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
        prompt_mapping=PromptMapping(
            system_prompt_key="test_agent_system_prompt",
            plan_prompt_key="test_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="test_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.8,
        delegation_preference="reluctant",
    ),
    "security-agent": AgentDefinition(
        agent_id="security-agent",
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
        constraints=ConstraintDefaults(temperature=0.1, reflection_passes=2, reasoning_depth=3),
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
        prompt_mapping=PromptMapping(
            system_prompt_key="security_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="security_agent_final_prompt",
        ),
        autonomy_level=5,
        confidence_threshold=0.85,
        delegation_preference="reluctant",
    ),
    "doc-agent": AgentDefinition(
        agent_id="doc-agent",
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
        constraints=ConstraintDefaults(temperature=0.4, reflection_passes=1, reasoning_depth=2),
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
        prompt_mapping=PromptMapping(
            system_prompt_key="doc_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="doc_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.65,
        delegation_preference="reluctant",
    ),
    "refactor-agent": AgentDefinition(
        agent_id="refactor-agent",
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
        constraints=ConstraintDefaults(temperature=0.2, reflection_passes=2, reasoning_depth=3),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "write_file", "apply_patch", "run_command",
                "code_execute", "list_code_usages",
            ],
        ),
        prompt_mapping=PromptMapping(
            system_prompt_key="refactor_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="refactor_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.8,
        delegation_preference="selective",
    ),
    "devops-agent": AgentDefinition(
        agent_id="devops-agent",
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
        constraints=ConstraintDefaults(temperature=0.2, reflection_passes=1, reasoning_depth=2),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "write_file", "run_command",
            ],
            forbidden_tools=["code_execute", "start_background_command"],
        ),
        prompt_mapping=PromptMapping(
            system_prompt_key="devops_agent_system_prompt",
            plan_prompt_key="head_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="devops_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.7,
        delegation_preference="reluctant",
    ),

    # ── Industry ──────────────────────────────────────────
    "fintech-agent": AgentDefinition(
        agent_id="fintech-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="fintech_agent_system_prompt",
            plan_prompt_key="fintech_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="fintech_agent_final_prompt",
        ),
        autonomy_level=5,
        confidence_threshold=0.85,
        delegation_preference="reluctant",
    ),
    "healthtech-agent": AgentDefinition(
        agent_id="healthtech-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="healthtech_agent_system_prompt",
            plan_prompt_key="healthtech_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="healthtech_agent_final_prompt",
        ),
        autonomy_level=4,
        confidence_threshold=0.9,
        delegation_preference="reluctant",
    ),
    "legaltech-agent": AgentDefinition(
        agent_id="legaltech-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="legaltech_agent_system_prompt",
            plan_prompt_key="legaltech_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="legaltech_agent_final_prompt",
        ),
        autonomy_level=5,
        confidence_threshold=0.85,
        delegation_preference="reluctant",
    ),
    "ecommerce-agent": AgentDefinition(
        agent_id="ecommerce-agent",
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
        constraints=ConstraintDefaults(temperature=0.25, reflection_passes=1, reasoning_depth=3),
        tool_policy=ToolPolicySpec(
            read_only=False,
            preferred_tools=[
                "read_file", "grep_search", "file_search",
                "list_dir", "write_file", "run_command",
            ],
            forbidden_tools=["code_execute", "start_background_command"],
        ),
        prompt_mapping=PromptMapping(
            system_prompt_key="ecommerce_agent_system_prompt",
            plan_prompt_key="ecommerce_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="ecommerce_agent_final_prompt",
        ),
        autonomy_level=6,
        confidence_threshold=0.7,
        delegation_preference="reluctant",
    ),
    "industrytech-agent": AgentDefinition(
        agent_id="industrytech-agent",
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
        constraints=ConstraintDefaults(
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
        prompt_mapping=PromptMapping(
            system_prompt_key="industrytech_agent_system_prompt",
            plan_prompt_key="industrytech_agent_plan_prompt",
            tool_selector_prompt_key="head_agent_tool_selector_prompt",
            tool_repair_prompt_key="head_agent_tool_repair_prompt",
            final_prompt_key="industrytech_agent_final_prompt",
        ),
        autonomy_level=5,
        confidence_threshold=0.8,
        delegation_preference="reluctant",
    ),
}


def get_definition(agent_id: str) -> AgentDefinition | None:
    """Look up a built-in agent definition by ID."""
    return BUILTIN_AGENT_DEFINITIONS.get((agent_id or "").strip().lower())


def get_all_agent_ids() -> list[str]:
    """Return all built-in agent IDs in sorted order."""
    return sorted(BUILTIN_AGENT_DEFINITIONS.keys())
