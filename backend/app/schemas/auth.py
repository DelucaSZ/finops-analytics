from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordProof(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=128)


class CompleteAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr = Field(min_length=43, max_length=43)
    password: SecretStr = Field(min_length=12, max_length=128)


class ResetRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
