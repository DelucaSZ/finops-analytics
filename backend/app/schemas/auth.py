from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordProof(BaseModel):
    code: SecretStr = Field(default=SecretStr(""), max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordChange(BaseModel):
    code: SecretStr = Field(default=SecretStr(""), max_length=64)
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=128)


class CompleteAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr = Field(min_length=43, max_length=43)
    password: SecretStr = Field(min_length=12, max_length=128)


class ResetRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)


class MfaCode(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=64)


class MfaLogin(MfaCode):
    challenge: SecretStr = Field(min_length=43, max_length=43)


class MfaReset(PasswordProof):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Informe o motivo da recuperação (mínimo de 10 caracteres)")
        return value
