"""Public collection errors are an allowlist, never a redacted copy of exceptions.

Also applied on reads to protect historical rows. Unknown messages, provider
payloads, SQL parameters, URLs and tracebacks are intentionally not echoed.
"""

ERROR_MESSAGES = {
    "AccessDenied": "Acesso negado (AccessDenied). Verifique as permissões da coleta.",
    "UnauthorizedOperation": "Sem permissão (UnauthorizedOperation). Verifique a função de coleta.",
    "ExpiredToken": "Credencial temporária expirada (ExpiredToken). Verifique a autenticação.",
    "InvalidClientTokenId": "Credencial inválida (InvalidClientTokenId). Verifique a autenticação.",
    "Throttling": "Limite de requisições atingido (Throttling). Tente novamente mais tarde.",
    "RequestLimitExceeded": "Limite atingido (RequestLimitExceeded). Tente novamente.",
    "EndpointConnectionError": "Falha de conexão (EndpointConnectionError). Verifique a rede.",
    "ConnectTimeoutError": "Tempo limite de conexão com o provider (ConnectTimeoutError).",
    "ReadTimeoutError": "Tempo limite de resposta do provider (ReadTimeoutError).",
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
}
GENERIC_ERROR = "Falha durante a coleta. Verifique a conexão e as permissões da conta."


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
