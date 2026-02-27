class GuardrailViolation(Exception):
    pass


class ToolExecutionError(Exception):
    pass


class LlmClientError(Exception):
    pass


class RuntimeSwitchError(Exception):
    pass


class RuntimeAuthRequiredError(Exception):
    def __init__(self, auth_url: str):
        super().__init__("Authentication required")
        self.auth_url = auth_url
