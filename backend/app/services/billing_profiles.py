from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_profile import BillingProfile
from app.schemas.billing import (
    AwsBillingApiRequest,
    AwsBillingRequest,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
    BillingProfileCreate,
    BillingProfileUpdate,
    ResolvedBillingOptions,
)

FINOPS_SYSTEM_PROFILE_ID = "00000000-0000-0000-0000-000000023015"
FINOPS_SYSTEM_PROFILE_NAME = "FinOps"
DEFAULT_GRANULARITY = BillingGranularity.DAILY
DEFAULT_METRIC = BillingMetric.AMORTIZED_COST
DEFAULT_GROUP_BY = BillingGroupBy.SERVICE
DEFAULT_EXCLUDE_RECORD_TYPES = ("Credit",)


class BillingProfileError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ResolvedBillingRequest:
    request: AwsBillingRequest
    profile_id: str | None
    profile_name: str | None

    def options(self, *, group_by: BillingGroupBy | None = None) -> ResolvedBillingOptions:
        return ResolvedBillingOptions(
            granularity=self.request.granularity,
            metric=self.request.metric,
            group_by=group_by if group_by is not None else self.request.group_by,
            exclude_record_types=list(self.request.exclude_record_types),
        )


def ensure_finops_profile(db: Session) -> BillingProfile:
    """Create the system FinOps profile once without overwriting existing customization."""

    existing = db.get(BillingProfile, FINOPS_SYSTEM_PROFILE_ID)
    if existing is None:
        existing = db.scalar(
            select(BillingProfile).where(
                func.lower(BillingProfile.name) == FINOPS_SYSTEM_PROFILE_NAME.lower()
            )
        )
    if existing is not None:
        return existing

    has_default = db.scalar(
        select(BillingProfile.id).where(BillingProfile.is_default.is_(True))
    )
    profile = BillingProfile(
        id=FINOPS_SYSTEM_PROFILE_ID,
        name=FINOPS_SYSTEM_PROFILE_NAME,
        description="Visão diária amortizada usada pelo time FinOps.",
        granularity=DEFAULT_GRANULARITY.value,
        metric=DEFAULT_METRIC.value,
        group_by=DEFAULT_GROUP_BY.value,
        exclude_record_types=list(DEFAULT_EXCLUDE_RECORD_TYPES),
        is_default=has_default is None,
        enabled=True,
        is_system=True,
        created_by=None,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.get(BillingProfile, FINOPS_SYSTEM_PROFILE_ID)
        if concurrent is None:
            concurrent = db.scalar(
                select(BillingProfile).where(
                    func.lower(BillingProfile.name) == FINOPS_SYSTEM_PROFILE_NAME.lower()
                )
            )
        if concurrent is not None:
            return concurrent
        raise
    db.refresh(profile)
    return profile


class BillingProfileService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, *, enabled: bool | None = None) -> list[BillingProfile]:
        statement = select(BillingProfile)
        if enabled is not None:
            statement = statement.where(BillingProfile.enabled.is_(enabled))
        return list(
            self._db.scalars(
                statement.order_by(
                    BillingProfile.is_default.desc(),
                    func.lower(BillingProfile.name),
                )
            )
        )

    def get(self, profile_id: str, *, require_enabled: bool = False) -> BillingProfile:
        profile = self._db.get(BillingProfile, profile_id)
        if profile is None:
            raise BillingProfileError(
                "PROFILE_NOT_FOUND", "Perfil de Billing não encontrado."
            )
        if require_enabled and not profile.enabled:
            raise BillingProfileError(
                "PROFILE_INACTIVE", "O perfil de Billing está inativo."
            )
        return profile

    def _ensure_unique_name(self, name: str, *, exclude_id: str | None = None) -> None:
        statement = select(BillingProfile.id).where(
            func.lower(BillingProfile.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(BillingProfile.id != exclude_id)
        if self._db.scalar(statement) is not None:
            raise BillingProfileError(
                "PROFILE_NAME_CONFLICT",
                "Já existe um perfil de Billing com esse nome.",
            )

    def _lock_profiles(self) -> list[BillingProfile]:
        statement = select(BillingProfile).order_by(BillingProfile.id).with_for_update()
        return list(self._db.scalars(statement))

    def _flush_mutation(
        self,
        profile: BillingProfile,
        *,
        commit: bool,
        conflict_code: str,
        message: str,
    ) -> BillingProfile:
        try:
            self._db.flush()
            if commit:
                self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise BillingProfileError(conflict_code, message) from exc
        self._db.refresh(profile)
        return profile

    def create(
        self,
        payload: BillingProfileCreate,
        *,
        actor_user_id: str,
        commit: bool = True,
    ) -> BillingProfile:
        self._ensure_unique_name(payload.name)
        if payload.is_default:
            profiles = self._lock_profiles()
            for profile in profiles:
                profile.is_default = False

        profile = BillingProfile(
            name=payload.name,
            description=payload.description,
            granularity=payload.granularity.value,
            metric=payload.metric.value,
            group_by=payload.group_by.value,
            exclude_record_types=list(payload.exclude_record_types),
            is_default=payload.is_default,
            enabled=True,
            is_system=False,
            created_by=actor_user_id,
        )
        self._db.add(profile)
        return self._flush_mutation(
            profile,
            commit=commit,
            conflict_code="PROFILE_CONFLICT",
            message="Não foi possível criar o perfil por conflito com outra alteração.",
        )

    def update(
        self,
        profile_id: str,
        payload: BillingProfileUpdate,
        *,
        commit: bool = True,
    ) -> BillingProfile:
        profile = self.get(profile_id)
        fields = payload.model_fields_set
        if "name" in fields:
            if payload.name is None:
                raise BillingProfileError(
                    "INVALID_PROFILE", "O nome do perfil é obrigatório."
                )
            self._ensure_unique_name(payload.name, exclude_id=profile.id)
            profile.name = payload.name
        if "description" in fields:
            profile.description = payload.description

        enum_fields = {
            "granularity": payload.granularity,
            "metric": payload.metric,
            "group_by": payload.group_by,
        }
        for field, value in enum_fields.items():
            if field in fields:
                if value is None:
                    raise BillingProfileError(
                        "INVALID_PROFILE", f"{field} não pode ser nulo."
                    )
                setattr(profile, field, value.value)
        if "exclude_record_types" in fields:
            if payload.exclude_record_types is None:
                raise BillingProfileError(
                    "INVALID_PROFILE", "exclude_record_types não pode ser nulo."
                )
            profile.exclude_record_types = list(payload.exclude_record_types)

        return self._flush_mutation(
            profile,
            commit=commit,
            conflict_code="PROFILE_CONFLICT",
            message="Não foi possível atualizar o perfil por conflito com outra alteração.",
        )

    def set_default(self, profile_id: str, *, commit: bool = True) -> BillingProfile:
        profiles = self._lock_profiles()
        target = next((profile for profile in profiles if profile.id == profile_id), None)
        if target is None:
            raise BillingProfileError(
                "PROFILE_NOT_FOUND", "Perfil de Billing não encontrado."
            )
        if not target.enabled:
            raise BillingProfileError(
                "PROFILE_INACTIVE", "Um perfil inativo não pode ser definido como padrão."
            )
        for profile in profiles:
            profile.is_default = profile.id == target.id
        return self._flush_mutation(
            target,
            commit=commit,
            conflict_code="DEFAULT_CONFLICT",
            message="Outro perfil foi definido como padrão simultaneamente. Tente novamente.",
        )

    def deactivate(self, profile_id: str, *, commit: bool = True) -> BillingProfile:
        profile = self.get(profile_id)
        if profile.is_default:
            raise BillingProfileError(
                "DEFAULT_PROFILE_REQUIRED",
                "Defina outro perfil como padrão antes de desativar este perfil.",
            )
        if profile.is_system:
            raise BillingProfileError(
                "SYSTEM_PROFILE_PROTECTED",
                "O perfil de sistema FinOps deve permanecer disponível como fallback.",
            )
        if profile.enabled:
            profile.enabled = False
            self._flush_mutation(
                profile,
                commit=commit,
                conflict_code="PROFILE_CONFLICT",
                message="Não foi possível desativar o perfil por conflito com outra alteração.",
            )
        return profile

    def _default_profile(self) -> BillingProfile | None:
        profile = self._db.scalar(
            select(BillingProfile).where(
                BillingProfile.is_default.is_(True),
                BillingProfile.enabled.is_(True),
            )
        )
        if profile is not None:
            return profile
        return self._db.scalar(
            select(BillingProfile).where(
                BillingProfile.id == FINOPS_SYSTEM_PROFILE_ID,
                BillingProfile.enabled.is_(True),
            )
        )

    @staticmethod
    def _profile_options(
        profile: BillingProfile | None,
    ) -> tuple[BillingGranularity, BillingMetric, BillingGroupBy, list[str]]:
        if profile is None:
            return (
                DEFAULT_GRANULARITY,
                DEFAULT_METRIC,
                DEFAULT_GROUP_BY,
                list(DEFAULT_EXCLUDE_RECORD_TYPES),
            )
        try:
            return (
                BillingGranularity(profile.granularity),
                BillingMetric(profile.metric),
                BillingGroupBy(profile.group_by),
                list(profile.exclude_record_types),
            )
        except (TypeError, ValueError) as exc:
            raise BillingProfileError(
                "PROFILE_INVALID",
                "O perfil de Billing possui configuração incompatível com o backend atual.",
            ) from exc

    def resolve(self, payload: AwsBillingApiRequest) -> ResolvedBillingRequest:
        profile = (
            self.get(payload.profile_id, require_enabled=True)
            if payload.profile_id is not None
            else self._default_profile()
        )
        granularity, metric, group_by, exclude_record_types = self._profile_options(profile)

        request = AwsBillingRequest(
            account_ids=payload.account_ids,
            start_date=payload.start_date,
            end_date=payload.end_date,
            granularity=payload.granularity or granularity,
            metric=payload.metric or metric,
            group_by=payload.group_by or group_by,
            exclude_record_types=(
                payload.exclude_record_types
                if payload.exclude_record_types is not None
                else exclude_record_types
            ),
        )
        return ResolvedBillingRequest(
            request=request,
            profile_id=profile.id if profile is not None else None,
            profile_name=profile.name if profile is not None else None,
        )
