class GuardrailViolation(Exception):
    pass


class ToolExecutionError(Exception):
    pass


class LlmClientError(Exception):
    pass


class RuntimeSwitchError(Exception):
    pass
