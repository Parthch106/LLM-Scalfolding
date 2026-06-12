"""
scaffold/schemas.py

Pydantic action schemas for the astronomy observation catalog.

Every LLM output is validated against this discriminated union.
Adding a new action type = add a class here + handle it in execute.py.
The validation gate (validate.py) handles everything else automatically.
"""
from typing import Literal, Union, Annotated, Optional
from pydantic import BaseModel, Field, model_validator, ValidationInfo
from uuid import UUID

# ── Shared base ───────────────────────────────────────────────────────────────

class _Base(BaseModel):
    reasoning: str = Field(..., max_length=600,
        description="Explain which objects were selected and why (max 600 chars)")

    @model_validator(mode='after')
    def check_secret_word(self, info: ValidationInfo):
        if info.context:
            secret = info.context.get("secret_word")
            if secret and secret.upper() not in self.reasoning.upper():
                raise ValueError(f"Backend Business Rule Violation: The reasoning string MUST contain the exact word '{secret}'.")
        return self

# ── Action models ─────────────────────────────────────────────────────────────

ObservationStatus = Literal["Unobserved", "Scheduled", "Observed", "Confirmed", "Anomalous"]
ObservationPriority = Literal["Low", "Medium", "High", "Critical"]

class UpdateStatusAction(_Base):
    action_type: Literal["UPDATE_STATUS"] = Field(default="UPDATE_STATUS", description="Must be exactly 'UPDATE_STATUS'")
    target_object_ids: list[UUID] = Field(..., min_length=1,
        description="IDs of objects to update — must exist in the catalog")
    new_status: ObservationStatus

class UpdatePriorityAction(_Base):
    action_type: Literal["UPDATE_PRIORITY"] = Field(default="UPDATE_PRIORITY", description="Must be exactly 'UPDATE_PRIORITY'")
    target_object_ids: list[UUID] = Field(..., min_length=1,
        description="IDs of objects to update — must exist in the catalog")
    new_priority: ObservationPriority

class LogObjectAction(_Base):
    """Add a new celestial object to the catalog."""
    action_type: Literal["LOG_OBJECT"] = Field(default="LOG_OBJECT", description="Must be exactly 'LOG_OBJECT'")
    catalog_id: str = Field(..., description="Unique catalog identifier, e.g. 'HD 12345' or '2024 XY1'")
    name: Optional[str] = None
    object_type: Literal["Star", "Exoplanet", "Asteroid", "Galaxy", "Nebula", "Comet"]
    observation_status: ObservationStatus = "Unobserved"
    priority: ObservationPriority = "Medium"
    magnitude: Optional[float] = None
    distance_ly: Optional[float] = None
    tags: list[str] = []
    notes: Optional[str] = None

class FlagAnomalyAction(_Base):
    """Flag one or more objects as Anomalous and record an observation note."""
    action_type: Literal["FLAG_ANOMALY"] = Field(default="FLAG_ANOMALY", description="Must be exactly 'FLAG_ANOMALY'")
    target_object_ids: list[UUID] = Field(..., min_length=1)
    anomaly_note: str = Field(..., min_length=10,
        description="Description of the anomaly observed (min 10 chars)")

class ClarificationNeeded(BaseModel):
    """Ask the user to clarify — be specific about what is ambiguous."""
    action_type: Literal["CLARIFICATION_NEEDED"] = Field(default="CLARIFICATION_NEEDED", description="Must be exactly 'CLARIFICATION_NEEDED'")
    reasoning: str = Field(..., max_length=600,
        description="Explain why you are blocked and what information you need.")
    message_to_user: str = Field(...,
        description="Ask the user to clarify — be specific about what is ambiguous")

class SearchCatalogAction(BaseModel):
    """Search the catalog to find UUIDs for celestial objects."""
    action_type: Literal["SEARCH_CATALOG"] = Field(default="SEARCH_CATALOG", description="Must be exactly 'SEARCH_CATALOG'")
    search_query: str = Field(...,
        description="The name or characteristics of the object to search for (e.g., 'Betelgeuse' or 'red supergiant').")

# ── Discriminated union ───────────────────────────────────────────────────────
# Pydantic reads action_type first and routes directly to the correct model.

AgentAction = Annotated[
    Union[
        UpdateStatusAction,
        UpdatePriorityAction,
        LogObjectAction,
        FlagAnomalyAction,
        ClarificationNeeded,
        SearchCatalogAction,
    ],
    Field(discriminator="action_type"),
]

# Master ReAct wrapper
class ReActPayload(BaseModel):
    thought_process: str = Field(..., description="Think step-by-step. What is the user asking? What data do you need? What rules must you follow?")
    execution_plan: list[str] = Field(..., description="List the high-level steps you are about to take.")
    actions: list[AgentAction] = Field(..., description="The concrete database actions to execute.")
