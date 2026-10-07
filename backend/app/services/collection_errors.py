"""Safe collection error handling and operational classification.

Public collection errors are an allowlist, never a redacted copy of exceptions.
The same helpers are applied on reads to protect historical rows. Unknown messages,
provider payloads, SQL parameters, URLs and tracebacks are intentionally not echoed.
"""

ERROR_MESSAGES = {
    "AccessDenied": "Acesso negado (AccessDenied). Verifique as permissões da coleta.",
    "UnauthorizedOperation": "Sem permissão (UnauthorizedOperation). Verifique a função de coleta.",
    "ExpiredToken": "Credencial temporária expirada (ExpiredToken). Verifique a autenticação.",
    "InvalidClientTokenId": "Credencial inválida (InvalidClientTokenId). Verifique a autenticação.",
    "SignatureDoesNotMatch": (
        "Assinatura inválida (SignatureDoesNotMatch). Verifique a autenticação."
    ),
    "NotAuthenticated": "Falha de autenticação no provider. Verifique as credenciais configuradas.",
    "NotAuthorizedOrNotFound": "Sem permissão para consultar esta fonte no provider.",
    "Forbidden": "Sem permissão para consultar esta fonte no provider.",
    "Throttling": "Limite de requisições atingido (Throttling). Tente novamente mais tarde.",
    "RequestLimitExceeded": "Limite atingido (RequestLimitExceeded). Tente novamente.",
    "TooManyRequests": "Limite de requisições atingido. Tente novamente mais tarde.",
    "EndpointConnectionError": "Falha de conexão (EndpointConnectionError). Verifique a rede.",
    "ConnectTimeoutError": "Tempo limite de conexão com o provider (ConnectTimeoutError).",
    "ReadTimeoutError": "Tempo limite de resposta do provider (ReadTimeoutError).",
    "TimeoutError": "Tempo limite durante a coleta.",
    "AWS account was removed or disabled": "A conta foi removida ou desabilitada.",
    "OCI credential failure": (
        "Falha de credencial OCI (OCI credential failure). Verifique a autenticação e a assinatura."
    ),
    "OCI authentication failure": (
        "Falha de autenticação OCI (OCI authentication failure). "
        "Verifique a autenticação e a assinatura."
    ),
    "OCI credential tenancy": (
        "A credencial OCI não corresponde ao tenancy configurado (OCI credential tenancy)."
    ),
    "local_configuration_invalid": "A configuração local do provider é inválida ou incompleta.",
}
GENERIC_ERROR = "Falha durante a coleta. Verifique a conexão e as permissões da conta."


class CollectionErrorInfo:
    __slots__ = ("category", "retryable", "public_message")

    def __init__(
        self,
        category: str,
        retryable: bool | None,
        public_message: str,
    ) -> None:
        self.category = category
        self.retryable = retryable
        self.public_message = public_message


_AUTHENTICATION_TOKENS = (
    "expiredtoken",
    "invalidclienttokenid",
    "signaturedoesnotmatch",
    "notauthenticated",
    "authentication",
    "credential failure",
    "invalid credential",
    "invalid credentials",
)
_AUTHORIZATION_TOKENS = (
    "accessdenied",
    "unauthorizedoperation",
    "notauthorizedornotfound",
    "forbidden",
    "authorization",
    "permission denied",
)
_RATE_LIMIT_TOKENS = (
    "throttling",
    "requestlimitexceeded",
    "toomanyrequests",
    "rate limit",
    "rate_limit",
    "429",
)
_TIMEOUT_TOKENS = (
    "connecttimeouterror",
    "readtimeouterror",
    "timeouterror",
    "timed out",
    "timeout",
)
_CONFIGURATION_TOKENS = (
    "local_configuration_invalid",
    "configuration is missing",
    "configuration missing",
    "configuration invalid",
    "operational configuration is missing",
    "encryption key",
)
_DATA_COVERAGE_TOKENS = (
    "data coverage",
    "coverage",
    "metric unavailable",
    "metrics unavailable",
    "partial data",
)
_VALIDATION_TOKENS = (
    "precondition",
    "disabled",
    "unsupported provider",
    "unknown cloud provider",
    "does not match",
)
_PERSISTENCE_TYPE_TOKENS = (
    "integrityerror",
    "operationalerror",
    "databaseerror",
    "sqlalchemyerror",
)
_PROVIDER_SERVICE_TOKENS = (
    "service unavailable",
    "serviceerror",
    "internalservererror",
    "badgateway",
    "gatewaytimeout",
    "service_unavailable",
    " 500",
    " 502",
    " 503",
    " 504",
)


def sanitize_collection_error(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    message = str(value)
    if message in ERROR_MESSAGES.values() or message == GENERIC_ERROR:
        return message
    # Only predefined text leaves this function, even if a code occurs in a
    # malicious header, credential or stack trace supplied by a remote service.
    for code, public_message in ERROR_MESSAGES.items():
        if code in message or code == type(value).__name__:
            return public_message
    return GENERIC_ERROR


def classify_collection_error(value: object | None) -> CollectionErrorInfo:
    """Classify an error without copying provider payloads into operational metadata."""

    public_message = sanitize_collection_error(value) or GENERIC_ERROR
    if value is None:
        return CollectionErrorInfo("internal", None, public_message)

    message = str(value).lower()
    type_name = type(value).__name__.lower()
    combined = f"{type_name} {message}"

    if any(token in combined for token in _CONFIGURATION_TOKENS):
        return CollectionErrorInfo("configuration", False, public_message)
    if any(token in combined for token in _AUTHENTICATION_TOKENS):
        return CollectionErrorInfo("authentication", False, public_message)
    if any(token in combined for token in _AUTHORIZATION_TOKENS):
        return CollectionErrorInfo("authorization", False, public_message)
    if any(token in combined for token in _RATE_LIMIT_TOKENS):
        return CollectionErrorInfo("rate_limit", True, public_message)
    if any(token in combined for token in _TIMEOUT_TOKENS):
        return CollectionErrorInfo("timeout", True, public_message)
    if any(token in combined for token in _PERSISTENCE_TYPE_TOKENS):
        return CollectionErrorInfo("persistence", None, public_message)
    if any(token in combined for token in _DATA_COVERAGE_TOKENS):
        return CollectionErrorInfo("data_coverage", None, public_message)
    if any(token in combined for token in _VALIDATION_TOKENS):
        return CollectionErrorInfo("validation", False, public_message)
    if any(token in combined for token in _PROVIDER_SERVICE_TOKENS):
        return CollectionErrorInfo("provider_service", True, public_message)
    return CollectionErrorInfo("internal", None, public_message)
