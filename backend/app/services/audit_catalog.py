from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditActionDefinition:
    module: str
    label: str


AUDIT_MODULE_LABELS: dict[str, str] = {
    "users": "Usuários",
    "security": "Segurança",
    "auth": "Segurança",
    "mfa": "Segurança",
    "accounts": "Contas",
    "collections": "Coletas",
    "policies": "Policies",
    "opportunities": "Oportunidades",
    "pricing": "Pricing",
    "billing": "Billing",
    "tls": "HTTPS",
    "settings": "Configurações",
    "system": "Sistema",
}

AUDIT_ACTIONS: dict[str, AuditActionDefinition] = {
    # SecurityEvent actions kept here so the unified UI can use the same labels.
    "auth.login": AuditActionDefinition("security", "Login concluído"),
    "auth.login_failed": AuditActionDefinition("security", "Tentativa de login recusada"),
    "auth.logout": AuditActionDefinition("security", "Saída da conta"),
    "auth.logout_all": AuditActionDefinition("security", "Todas as sessões encerradas"),
    "auth.session_revoked": AuditActionDefinition(
        "security", "Sessão encerrada pelo titular"
    ),
    "auth.reauthenticated": AuditActionDefinition("security", "Identidade confirmada"),
    "auth.password_changed": AuditActionDefinition("security", "Senha alterada"),
    "auth.password_reset": AuditActionDefinition("security", "Senha redefinida"),
    "auth.invitation_accepted": AuditActionDefinition("security", "Convite aceito"),
    "user.created": AuditActionDefinition("users", "Usuário criado"),
    "user.updated": AuditActionDefinition("users", "Cadastro de usuário alterado"),
    "user.invited": AuditActionDefinition("users", "Usuário convidado"),
    "user.invitation_renewed": AuditActionDefinition("users", "Convite renovado"),
    "user.password_reset_issued": AuditActionDefinition(
        "users", "Link de recuperação gerado"
    ),
    "user.sessions_revoked": AuditActionDefinition("users", "Sessões revogadas"),
    "user.session_revoked": AuditActionDefinition("users", "Sessão revogada"),
    "mfa.setup_started": AuditActionDefinition(
        "security", "Cadastro do autenticador iniciado"
    ),
    "mfa.enabled": AuditActionDefinition(
        "security", "Autenticador ativado ou substituído"
    ),
    "mfa.login_failed": AuditActionDefinition("security", "Segundo fator recusado"),
    "mfa.login_verified": AuditActionDefinition(
        "security", "Login com segundo fator concluído"
    ),
    "mfa.recovery_used": AuditActionDefinition(
        "security", "Código de recuperação utilizado"
    ),
    "mfa.recovery_regenerated": AuditActionDefinition(
        "security", "Códigos de recuperação regenerados"
    ),
    "mfa.reset": AuditActionDefinition("security", "MFA redefinido"),
    # Administrative AuditEvent actions.
    "user.create": AuditActionDefinition("users", "Usuário criado"),
    "user.update": AuditActionDefinition("users", "Usuário alterado"),
    "user.enable": AuditActionDefinition("users", "Usuário ativado"),
    "user.disable": AuditActionDefinition("users", "Usuário desativado"),
    "user.invite": AuditActionDefinition("users", "Usuário convidado"),
    "user.invitation_renew": AuditActionDefinition("users", "Convite renovado"),
    "user.password_reset_issue": AuditActionDefinition(
        "users", "Recuperação de senha emitida"
    ),
    "user.sessions_revoke": AuditActionDefinition(
        "users", "Sessões de usuário revogadas"
    ),
    "user.mfa_reset": AuditActionDefinition("users", "MFA de usuário redefinido"),
    "account.create": AuditActionDefinition("accounts", "Conta cloud criada"),
    "account.update": AuditActionDefinition("accounts", "Conta cloud alterada"),
    "account.enable": AuditActionDefinition("accounts", "Conta cloud habilitada"),
    "account.disable": AuditActionDefinition("accounts", "Conta cloud desabilitada"),
    "account.delete": AuditActionDefinition("accounts", "Conta cloud removida"),
    "account.connection_test": AuditActionDefinition(
        "accounts", "Conexão da conta testada"
    ),
    "account.schedule_update": AuditActionDefinition(
        "accounts", "Agenda de coleta alterada"
    ),
    "policy.update": AuditActionDefinition("policies", "Policy alterada"),
    "policy.enable": AuditActionDefinition("policies", "Policy habilitada"),
    "policy.disable": AuditActionDefinition("policies", "Policy desabilitada"),
    "policy.reset": AuditActionDefinition("policies", "Policy restaurada ao padrão"),
    "opportunity.treat": AuditActionDefinition(
        "opportunities", "Oportunidade tratada"
    ),
    "opportunity.reject": AuditActionDefinition(
        "opportunities", "Oportunidade rejeitada"
    ),
    "opportunity.reopen": AuditActionDefinition(
        "opportunities", "Oportunidade reaberta"
    ),
    "opportunity.archive": AuditActionDefinition(
        "opportunities", "Oportunidade arquivada"
    ),
    "opportunity.unarchive": AuditActionDefinition(
        "opportunities", "Oportunidade desarquivada"
    ),
    "opportunity.bulk_treat": AuditActionDefinition(
        "opportunities", "Oportunidades tratadas em massa"
    ),
    "opportunity.bulk_reject": AuditActionDefinition(
        "opportunities", "Oportunidades rejeitadas em massa"
    ),
    "opportunity.bulk_reopen": AuditActionDefinition(
        "opportunities", "Oportunidades reabertas em massa"
    ),
    "pricing.create": AuditActionDefinition("pricing", "Preço criado"),
    "pricing.update": AuditActionDefinition("pricing", "Preço alterado"),
    "pricing.deactivate": AuditActionDefinition("pricing", "Preço desativado"),
    "pricing.import": AuditActionDefinition("pricing", "Pricing importado"),
    "pricing.override": AuditActionDefinition("pricing", "Override de pricing aplicado"),
    "billing.profile_create": AuditActionDefinition(
        "billing", "Perfil de Billing criado"
    ),
    "billing.profile_update": AuditActionDefinition(
        "billing", "Perfil de Billing alterado"
    ),
    "billing.profile_set_default": AuditActionDefinition(
        "billing", "Perfil padrão de Billing alterado"
    ),
    "billing.profile_deactivate": AuditActionDefinition(
        "billing", "Perfil de Billing desativado"
    ),
    "billing.settings_update": AuditActionDefinition(
        "billing", "Configuração de Billing alterada"
    ),
    "tls.apply": AuditActionDefinition("tls", "HTTPS/TLS aplicado"),
    "tls.mode_change": AuditActionDefinition("tls", "Modo HTTPS/TLS alterado"),
    "settings.update": AuditActionDefinition("settings", "Configuração alterada"),
    "security.settings_update": AuditActionDefinition(
        "settings", "Configuração de segurança alterada"
    ),
    "retention.update": AuditActionDefinition("settings", "Retenção alterada"),
}


def audit_catalog() -> dict[str, list[dict[str, str]]]:
    modules = [
        {"value": value, "label": label}
        for value, label in AUDIT_MODULE_LABELS.items()
        if value not in {"auth", "mfa"}
    ]
    actions = [
        {"value": action, "module": definition.module, "label": definition.label}
        for action, definition in AUDIT_ACTIONS.items()
    ]
    return {"modules": modules, "actions": actions}
