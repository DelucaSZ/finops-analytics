from pydantic import BaseModel, Field


class PolicyUpdate(BaseModel):
    enabled: bool | None = None
    config: dict = Field(default_factory=dict)


class PolicyRead(BaseModel):
    rule_key: str
    name: str
    description: str
    implemented: bool
    enabled: bool
    config: dict
    inherited: bool = True
    override_fields: list[str] = Field(default_factory=list)
