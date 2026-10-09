from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenException
from app.core.status_history import record_status_change
from app.core.workflow.exceptions import (
    GuardViolationException,
    InvalidTransitionException,
)
from app.core.workflow.transition import Transition


class StateMachine:
    """
    Unified state machine engine (Roadmap V0.7).
    Executes code-defined transitions atomically:
    Validate -> Permission Check -> Guards -> State Change -> Status History -> Side Effects.
    """

    def __init__(
        self,
        name: str,
        entity_type: str,
        transitions: list[Transition],
        status_attr: str = "status",
        allow_same_state_noop: bool = True,
    ) -> None:
        self.name = name
        self.entity_type = entity_type
        self.transitions = transitions
        self.status_attr = status_attr
        self.allow_same_state_noop = allow_same_state_noop

    def find_transition(self, from_state: str | None, to_state: str) -> Transition | None:
        for t in self.transitions:
            if t.matches(from_state, to_state):
                return t
        return None

    def can_transition(self, entity_or_state: Any, target_state: str) -> bool:
        current_state = (
            getattr(entity_or_state, self.status_attr, entity_or_state)
            if hasattr(entity_or_state, self.status_attr)
            else entity_or_state
        )
        return self.find_transition(current_state, target_state) is not None

    def get_available_transitions(self, entity_or_state: Any) -> list[Transition]:
        current_state = (
            getattr(entity_or_state, self.status_attr, entity_or_state)
            if hasattr(entity_or_state, self.status_attr)
            else entity_or_state
        )
        return [t for t in self.transitions if t.matches(current_state, t.to_state)]

    def trigger(
        self,
        entity: Any,
        target_state: str,
        db: Session,
        context: Any = None,
        user_id: int | None = None,
        reason: str | None = None,
        record_history: bool = True,
    ) -> Any:
        current_state = getattr(entity, self.status_attr, None)

        # Handle same-state transition
        if current_state == target_state:
            if self.allow_same_state_noop:
                return entity
            raise InvalidTransitionException(
                from_state=current_state,
                to_state=target_state,
                entity_type=self.entity_type,
                detail=f"{self.entity_type.capitalize()} is already in '{target_state}' status.",
            )

        # 1. Validate transition existence
        transition = self.find_transition(current_state, target_state)
        if not transition:
            raise InvalidTransitionException(
                from_state=current_state,
                to_state=target_state,
                entity_type=self.entity_type,
            )

        # Extract effective user
        acting_user = None
        if context is not None:
            if hasattr(context, "user"):
                acting_user = context.user
            elif hasattr(context, "is_superuser"):
                acting_user = context

        actor_id = user_id or (
            acting_user.id if acting_user and hasattr(acting_user, "id") else None
        )

        # 2. Permission Check
        if transition.permission and context is not None:
            is_super = getattr(acting_user, "is_superuser", False)
            if not is_super:
                has_perm = False
                if hasattr(context, "permissions"):
                    # ScopeContext or auth response with permissions dict
                    has_perm = transition.permission in context.permissions
                elif hasattr(acting_user, "permissions"):
                    has_perm = transition.permission in acting_user.permissions

                if not has_perm:
                    raise ForbiddenException(
                        detail=f"Permission '{transition.permission}' required to transition {self.entity_type} to '{target_state}'."
                    )

        # 3. Run Guards
        for guard in transition.guards:
            res = guard(entity, context, db)
            if isinstance(res, tuple):
                passed, err_msg = res
                if not passed:
                    raise GuardViolationException(
                        detail=err_msg
                        or f"Guard condition rejected transition from '{current_state}' to '{target_state}'."
                    )
            elif res is False:
                raise GuardViolationException(
                    detail=f"Guard condition rejected transition from '{current_state}' to '{target_state}'."
                )

        # 4. State Change
        setattr(entity, self.status_attr, target_state)

        # 5. Status History Recording
        entity_id = getattr(entity, "id", None)
        if record_history and entity_id is not None:
            record_status_change(
                db=db,
                entity_type=self.entity_type,
                entity_id=entity_id,
                to_status=target_state,
                from_status=current_state,
                reason=reason,
                changed_by=actor_id,
            )

        # 6. Run Side Effects
        for effect in transition.effects:
            effect(entity, context, db)

        return entity
