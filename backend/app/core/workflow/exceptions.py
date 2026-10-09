from app.core.errors import BusinessRuleException


class InvalidTransitionException(BusinessRuleException):
    def __init__(
        self,
        from_state: str | None,
        to_state: str,
        entity_type: str | None = None,
        detail: str | None = None,
        code: str = "INVALID_TRANSITION",
    ) -> None:
        entity_prefix = f" for {entity_type}" if entity_type else ""
        msg = detail or f"Cannot transition{entity_prefix} from '{from_state}' to '{to_state}'."
        super().__init__(code=code, detail=msg)
        self.from_state = from_state
        self.to_state = to_state
        self.entity_type = entity_type


class GuardViolationException(BusinessRuleException):
    def __init__(
        self,
        detail: str = "A workflow transition guard condition was not met.",
        code: str = "GUARD_VIOLATION",
    ) -> None:
        super().__init__(code=code, detail=detail)


class ApprovalRequiredException(BusinessRuleException):
    def __init__(
        self,
        rule_code: str,
        detail: str,
        request_id: int | None = None,
        code: str = "APPROVAL_REQUIRED",
    ) -> None:
        super().__init__(code=code, detail=detail)
        self.rule_code = rule_code
        self.request_id = request_id


# Aliases
InvalidTransitionError = InvalidTransitionException
GuardViolationError = GuardViolationException
ApprovalRequiredError = ApprovalRequiredException
