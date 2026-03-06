from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass

from app.custom_agents import CustomAgentAdapter
from app.interfaces import OrchestratorApi


@dataclass(frozen=True)
class AgentCapabilityMatch:
    agent_id: str
    matched_capabilities: tuple[str, ...]
    score: int


DEFAULT_AGENT_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "head-agent": ("general_reasoning", "coordination", "fallback"),
    "coder-agent": ("code_reasoning", "code_modification", "command_execution", "tooling"),
    "review-agent": ("review_analysis", "security_review", "quality_review", "read_only"),
    "researcher-agent": (
        "deep_research", "web_research", "analysis", "synthesis", "fact_checking",
    ),
    "architect-agent": (
        "architecture_analysis", "system_design", "trade_off_analysis",
        "adr_creation", "refactoring_planning", "read_only",
    ),
    "test-agent": (
        "test_generation", "test_execution", "coverage_analysis",
        "edge_case_discovery", "regression_testing",
    ),
    "security-agent": (
        "security_review", "vulnerability_analysis", "dependency_audit",
        "secret_detection", "owasp_analysis", "read_only",
    ),
    "doc-agent": (
        "documentation", "api_docs", "readme_generation",
        "changelog", "architecture_diagrams", "comment_quality",
    ),
    "refactor-agent": (
        "refactoring", "code_smell_detection", "pattern_application",
        "safe_transformation", "test_validation",
    ),
    "devops-agent": (
        "ci_cd", "containerization", "infrastructure",
        "deployment", "performance_profiling", "monitoring_setup",
    ),
    "fintech-agent": (
        "fintech_compliance", "payment_flow_analysis", "audit_trail_review",
        "fraud_detection", "ledger_design", "pci_dss", "psd2", "read_only",
    ),
    "healthtech-agent": (
        "healthtech_compliance", "phi_protection", "hipaa", "gdpr_health",
        "hl7_fhir", "dicom", "clinical_workflow", "anonymization", "read_only",
    ),
    "legaltech-agent": (
        "legal_compliance", "gdpr", "ccpa", "ai_act", "license_scanning",
        "dpia", "data_transfer_assessment", "cookie_consent", "read_only",
    ),
    "ecommerce-agent": (
        "ecommerce_design", "catalog_modeling", "checkout_flow",
        "order_processing", "seo_optimization", "pricing_engine",
        "inventory_management", "structured_data",
    ),
    "industrytech-agent": (
        "iot_analysis", "mqtt", "opcua", "predictive_maintenance",
        "digital_twin", "edge_computing", "iec_62443", "time_series",
    ),
}


def normalize_agent_id(
    agent_id: str | None,
    *,
    primary_agent_id: str,
    legacy_agent_aliases: Mapping[str, str],
) -> str:
    raw = (agent_id or primary_agent_id).strip().lower()
    return legacy_agent_aliases.get(raw, raw)


def effective_orchestrator_agent_ids(
    *,
    configured_agent_ids: list[str] | None,
    primary_agent_id: str,
    custom_orchestrator_agent_ids: set[str] | None,
) -> set[str]:
    configured = {
        str(item).strip().lower()
        for item in (configured_agent_ids or [primary_agent_id])
        if isinstance(item, str) and str(item).strip()
    }
    configured.add(primary_agent_id)
    configured |= {
        str(item).strip().lower()
        for item in (custom_orchestrator_agent_ids or set())
        if isinstance(item, str) and str(item).strip()
    }
    return configured


def sync_custom_agents(
    *,
    components,
    normalize_agent_id_fn,
    primary_agent_id: str,
    coder_agent_id: str,
    review_agent_id: str,
    effective_orchestrator_agent_ids_fn,
) -> None:
    for custom_id in list(components.custom_agent_ids):
        components.agent_registry.pop(custom_id, None)
        components.orchestrator_registry.pop(custom_id, None)

    components.custom_agent_ids = set()
    components.custom_orchestrator_agent_ids = set()

    definitions = components.custom_agent_store.list()
    for definition in definitions:
        custom_id = normalize_agent_id_fn(definition.id)
        if not custom_id or custom_id in {primary_agent_id, coder_agent_id, review_agent_id}:
            continue

        base_id = normalize_agent_id_fn(definition.base_agent_id)
        base_agent = components.agent_registry.get(base_id)
        if base_agent is None:
            continue

        adapter = CustomAgentAdapter(definition=definition, base_agent=base_agent)
        components.agent_registry[custom_id] = adapter
        components.orchestrator_registry[custom_id] = OrchestratorApi(
            agent=adapter,
            state_store=components.state_store,
        )
        components.custom_agent_ids.add(custom_id)
        if bool(getattr(definition, "allow_subrun_delegation", False)):
            components.custom_orchestrator_agent_ids.add(custom_id)

    if components.subrun_lane is not None:
        components.subrun_lane._orchestrator_agent_ids = effective_orchestrator_agent_ids_fn(components)


def resolve_agent(
    *,
    agent_id: str | None,
    sync_custom_agents_fn,
    normalize_agent_id_fn,
    agent_registry: MutableMapping,
    orchestrator_registry: MutableMapping,
):
    sync_custom_agents_fn()
    normalized_agent_id = normalize_agent_id_fn(agent_id)
    selected_agent = agent_registry.get(normalized_agent_id)
    selected_orchestrator = orchestrator_registry.get(normalized_agent_id)
    if selected_agent is None or selected_orchestrator is None:
        raise ValueError(f"Unsupported agent: {agent_id}")
    return normalized_agent_id, selected_agent, selected_orchestrator


def looks_like_coding_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    # Bug 12: word-boundary matching for short/ambiguous keywords to avoid false positives
    # e.g. "test" in "contest", "class" in "classify", "fix" in "prefix", "code" in "decode"
    _CODING_WB_RE = re.compile(
        r"\b(?:code|bug|fix|class|api|test|function|endpoint|debug|refactor|implement)\b"
    )
    if _CODING_WB_RE.search(text):
        return True

    # These tokens are long/distinctive enough to be safe as plain substring matches
    unambiguous_markers = (
        "python", "javascript", "typescript", "java", "c++", "c#",
        "golang", "rust", "sql", "html", "css",
        "pytest", "unit test", "write file", "apply patch",
    )
    if any(marker in text for marker in unambiguous_markers):
        return True

    return bool(re.search(r"\b(build|create|generate|update)\b.*\b(script|module|component|service|backend|frontend)\b", text))


def infer_request_capabilities(*, message: str, preset: str | None = None) -> set[str]:
    text = (message or "").strip().lower()
    selected_preset = (preset or "").strip().lower()
    capabilities: set[str] = set()

    if selected_preset == "review":
        capabilities.update({"review_analysis", "security_review", "quality_review"})

    review_markers = (
        "review",
        "audit",
        "security review",
        "quality check",
        "find issues",
        "critique",
    )
    if any(marker in text for marker in review_markers):
        capabilities.update({"review_analysis", "security_review", "quality_review"})

    # --- Research intent ---
    _RESEARCH_RE = re.compile(
        r"\b(?:recherchiere|research|recherche|analysiere\s+ausf[üu]hrlich|investigate|deep\s*dive|literature)\b"
    )
    if _RESEARCH_RE.search(text):
        capabilities.update({"deep_research", "synthesis", "fact_checking"})

    # --- Architecture intent ---
    _ARCH_RE = re.compile(
        r"\b(?:architektur|architecture|design|adr|trade[\s-]?off|system[\s-]?design|strukturanalyse)\b"
    )
    if _ARCH_RE.search(text):
        capabilities.update({"architecture_analysis", "system_design", "trade_off_analysis"})

    # --- Test intent ---
    _TEST_GENERATION_RE = re.compile(
        r"\b(?:teste|schreibe?\s+tests?|test\s+generation|coverage|edge[\s-]?case|unit[\s-]?test|integration[\s-]?test)\b"
    )
    if _TEST_GENERATION_RE.search(text):
        capabilities.update({"test_generation", "test_execution", "coverage_analysis"})

    # --- Security intent ---
    _SECURITY_RE = re.compile(
        r"\b(?:sicherheit|security|vulnerabilit|schwachstelle|owasp|secret[\s-]?detection|dependency[\s-]?audit)\b"
    )
    if _SECURITY_RE.search(text):
        capabilities.update({"security_review", "vulnerability_analysis", "dependency_audit"})

    # --- Documentation intent ---
    _DOC_RE = re.compile(
        r"\b(?:dokumentation|documentation|readme|docs|changelog|api[\s-]?dok|api[\s-]?doc)\b"
    )
    if _DOC_RE.search(text):
        capabilities.update({"documentation", "api_docs", "readme_generation"})

    # --- Refactoring intent ---
    _REFACTOR_RE = re.compile(
        r"\b(?:refactor|clean[\s-]?up|code[\s-]?smell|aufr[äa]umen|umstrukturier|extract[\s-]?method)\b"
    )
    if _REFACTOR_RE.search(text):
        capabilities.update({"refactoring", "code_smell_detection", "safe_transformation"})

    # --- DevOps intent ---
    _DEVOPS_RE = re.compile(
        r"\b(?:deploy|ci[\s/]cd|docker|pipeline|kubernetes|k8s|containeriz|infrastruktur|infrastructure|github[\s-]?action)\b"
    )
    if _DEVOPS_RE.search(text):
        capabilities.update({"ci_cd", "containerization", "deployment"})

    # --- FinTech intent ---
    _FINTECH_RE = re.compile(
        r"\b(?:fintech|payment|zahlung|pci[\s-]?dss|psd2|mifid|ledger|buchung|audit[\s-]?trail|fraud|betrug|idempot)\b"
    )
    if _FINTECH_RE.search(text):
        capabilities.update({"fintech_compliance", "payment_flow_analysis", "audit_trail_review"})

    # --- HealthTech intent ---
    _HEALTHTECH_RE = re.compile(
        r"\b(?:healthtech|health[\s-]?tech|hipaa|phi|pii|fhir|hl7|dicom|patient|klinisch|clinical|anonymisier|pseudonymisier|medizin|medical|mdr)\b"
    )
    if _HEALTHTECH_RE.search(text):
        capabilities.update({"healthtech_compliance", "phi_protection", "hipaa"})

    # --- LegalTech intent ---
    _LEGALTECH_RE = re.compile(
        r"\b(?:legaltech|legal[\s-]?tech|dsgvo|gdpr|ccpa|ai[\s-]?act|dpia|datenschutz|privacy|lizenz|license[\s-]?scan|cookie[\s-]?consent|eprivacy|impressum)\b"
    )
    if _LEGALTECH_RE.search(text):
        capabilities.update({"legal_compliance", "gdpr", "license_scanning"})

    # --- E-Commerce intent ---
    _ECOMMERCE_RE = re.compile(
        r"\b(?:e[\s-]?commerce|shop|warenkorb|cart|checkout|katalog|catalog|inventory|bestell|order[\s-]?process|pricing|schema\.org|structured[\s-]?data|seo|produkt[\s-]?katalog)\b"
    )
    if _ECOMMERCE_RE.search(text):
        capabilities.update({"ecommerce_design", "checkout_flow", "catalog_modeling"})

    # --- IndustryTech intent ---
    _INDUSTRYTECH_RE = re.compile(
        r"\b(?:industrytech|industry[\s-]?tech|iot|mqtt|opc[\s-]?ua|sensor|predictive[\s-]?maintenance|digital[\s-]?twin|edge[\s-]?computing|iec[\s-]?62443|sil[\s-]?level|time[\s-]?series|scada|plc)\b"
    )
    if _INDUSTRYTECH_RE.search(text):
        capabilities.update({"iot_analysis", "predictive_maintenance", "edge_computing"})

    # Bug 12: word-boundary matching for short/ambiguous coding keywords
    _INFER_CODING_WB_RE = re.compile(
        r"\b(?:code|bug|fix|class|api|test|function|endpoint|debug|refactor|implement)\b"
    )
    unambiguous_coding = ("python", "javascript", "typescript", "java", "golang", "rust", "pytest")
    if _INFER_CODING_WB_RE.search(text) or any(m in text for m in unambiguous_coding):
        capabilities.update({"code_reasoning", "code_modification", "tooling"})

    command_markers = (
        "run ",
        "execute ",
        "command",
        "terminal",
        "shell",
    )
    if any(marker in text for marker in command_markers):
        capabilities.add("command_execution")

    if not capabilities:
        capabilities.update({"general_reasoning", "coordination"})
    return capabilities


def resolve_agent_capabilities(*, agent_id: str, agent_registry: Mapping[str, object]) -> tuple[str, ...]:
    normalized_agent_id = str(agent_id or "").strip().lower()
    defaults = DEFAULT_AGENT_CAPABILITIES.get(normalized_agent_id)
    if defaults is not None:
        return defaults

    candidate = agent_registry.get(normalized_agent_id)
    if isinstance(candidate, CustomAgentAdapter):
        raw_capabilities = getattr(candidate.definition, "capabilities", ())
        normalized = tuple(
            str(item).strip().lower()
            for item in (raw_capabilities or ())
            if isinstance(item, str) and str(item).strip()
        )
        if normalized:
            return normalized

    return ("general_reasoning", "coordination")


def capability_route_agent(
    *,
    requested_agent_id: str,
    message: str,
    preset: str | None,
    primary_agent_id: str,
    agent_registry: Mapping[str, object],
) -> tuple[str, str | None, tuple[str, ...], list[AgentCapabilityMatch]]:
    requested = str(requested_agent_id or primary_agent_id).strip().lower() or primary_agent_id
    primary = str(primary_agent_id).strip().lower() or "head-agent"
    selected_preset = str(preset or "").strip().lower()
    normalized_message = str(message or "").strip().lower()

    required_capabilities = infer_request_capabilities(message=message, preset=preset)
    if requested != primary:
        return requested, None, tuple(sorted(required_capabilities)), []

    if selected_preset == "review" and "review-agent" in agent_registry:
        return "review-agent", "preset_review", tuple(sorted(required_capabilities)), []

    mixed_review_research_markers = (
        "research",
        "orchestrate",
        "fact check",
        "write",
        "save",
        "essay",
    )
    if "review_analysis" in required_capabilities and any(
        marker in normalized_message for marker in mixed_review_research_markers
    ):
        return primary, None, tuple(sorted(required_capabilities)), []

    should_delegate_by_capability = bool(
        {
            "code_reasoning", "review_analysis",
            "deep_research", "architecture_analysis", "test_generation",
            "security_review", "vulnerability_analysis",
            "documentation", "refactoring", "ci_cd",
            "fintech_compliance", "payment_flow_analysis",
            "healthtech_compliance", "phi_protection",
            "legal_compliance", "gdpr", "license_scanning",
            "ecommerce_design", "checkout_flow", "catalog_modeling",
            "iot_analysis", "predictive_maintenance", "edge_computing",
        } & required_capabilities
    )
    if not should_delegate_by_capability:
        return primary, None, tuple(sorted(required_capabilities)), []

    ranked: list[AgentCapabilityMatch] = []
    for agent_id in agent_registry.keys():
        normalized_agent_id = str(agent_id or "").strip().lower()
        capabilities = set(resolve_agent_capabilities(agent_id=normalized_agent_id, agent_registry=agent_registry))
        matched = tuple(sorted(required_capabilities & capabilities))
        ranked.append(
            AgentCapabilityMatch(
                agent_id=normalized_agent_id,
                matched_capabilities=matched,
                score=len(matched),
            )
        )

    ranked.sort(
        key=lambda item: (
            item.score,
            1 if item.agent_id == "coder-agent" and "code_reasoning" in required_capabilities else 0,
            1 if item.agent_id == "review-agent" and "review_analysis" in required_capabilities else 0,
            1 if item.agent_id == "researcher-agent" and "deep_research" in required_capabilities else 0,
            1 if item.agent_id == "architect-agent" and "architecture_analysis" in required_capabilities else 0,
            1 if item.agent_id == "test-agent" and "test_generation" in required_capabilities else 0,
            1 if item.agent_id == "security-agent" and "vulnerability_analysis" in required_capabilities else 0,
            1 if item.agent_id == "doc-agent" and "documentation" in required_capabilities else 0,
            1 if item.agent_id == "refactor-agent" and "refactoring" in required_capabilities else 0,
            1 if item.agent_id == "devops-agent" and "ci_cd" in required_capabilities else 0,
            1 if item.agent_id == "fintech-agent" and "fintech_compliance" in required_capabilities else 0,
            1 if item.agent_id == "healthtech-agent" and "healthtech_compliance" in required_capabilities else 0,
            1 if item.agent_id == "legaltech-agent" and "legal_compliance" in required_capabilities else 0,
            1 if item.agent_id == "ecommerce-agent" and "ecommerce_design" in required_capabilities else 0,
            1 if item.agent_id == "industrytech-agent" and "iot_analysis" in required_capabilities else 0,
            1 if item.agent_id == primary else 0,
        ),
        reverse=True,
    )

    best = ranked[0] if ranked else AgentCapabilityMatch(agent_id=primary, matched_capabilities=(), score=0)
    if best.score <= 0:
        return primary, None, tuple(sorted(required_capabilities)), ranked

    _AGENT_ROUTE_REASONS = {
        "review-agent": "review_intent",
        "coder-agent": "coding_intent",
        "researcher-agent": "research_intent",
        "architect-agent": "architecture_intent",
        "test-agent": "test_intent",
        "security-agent": "security_intent",
        "doc-agent": "documentation_intent",
        "refactor-agent": "refactoring_intent",
        "devops-agent": "devops_intent",
        "fintech-agent": "fintech_intent",
        "healthtech-agent": "healthtech_intent",
        "legaltech-agent": "legaltech_intent",
        "ecommerce-agent": "ecommerce_intent",
        "industrytech-agent": "industrytech_intent",
    }
    reason = _AGENT_ROUTE_REASONS.get(best.agent_id, "capability_match")
    return best.agent_id, reason, tuple(sorted(required_capabilities)), ranked
