from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import oci
import pytest
from requests import exceptions as requests_exceptions

from app.services.collection_executors import has_collection_executor
from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory
from app.services.oci_cloud_advisor import OciCloudAdvisorService
from app.services.oci_credentials import OciCredentialResolutionError
from app.services.provider_capabilities import get_provider_capabilities

TENANCY = "ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
COMP_A = "ocid1.compartment.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
COMP_B = "ocid1.compartment.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----ADVISOR-SECRET-----END PRIVATE KEY-----"
PASSPHRASE = "ADVISOR-PASSPHRASE-SECRET"


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def response(items, next_page=None, *, collection=True):
    data = obj(items=items) if collection else items
    return obj(
        data=data,
        headers={"opc-next-page": next_page} if next_page else {},
    )


class PagedCall:
    def __init__(self, pages=None, *, failure_page=None, failure=None):
        self.pages = pages if pages is not None else [[]]
        self.failure_page = failure_page
        self.failure = failure or RuntimeError("private failure")
        self.calls = []

    def __call__(self, *args, page=None, **kwargs):
        self.calls.append((args, dict(kwargs, page=page)))
        index = 0 if page is None else int(str(page).split("-")[-1]) - 1
        if self.failure_page == index:
            raise self.failure
        next_page = f"page-{index + 2}" if index + 1 < len(self.pages) else None
        return response(self.pages[index], next_page)


class FakeFactory:
    def __init__(self, optimizer=None, identity=None):
        self.optimizer_client = optimizer or obj(
            list_recommendations=PagedCall(),
            list_resource_actions=PagedCall(),
        )
        self.identity_client = identity or obj(list_compartments=PagedCall())
        self.requests = []

    def optimizer(self, region):
        self.requests.append(("optimizer", region))
        return self.optimizer_client

    def identity(self, region):
        self.requests.append(("identity", region))
        return self.identity_client


def snapshot(
    *,
    regions=("sa-saopaulo-1",),
    compartments=(COMP_A,),
    include_root=False,
    include_subcompartments=False,
):
    return OciConnectionSnapshot(
        cloud_account_id=7,
        configuration_revision=3,
        tenancy_ocid=TENANCY,
        user_ocid="ocid1.user.oc1..cccccccccccccccccccccccccccccccc",
        fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
        region="sa-saopaulo-1",
        scope_regions=tuple(regions),
        compartment_ocids=tuple(compartments),
        include_root_compartment=include_root,
        include_subcompartments=include_subcompartments,
        private_key_pem=PRIVATE_KEY,
        private_key_password=PASSPHRASE,
    )


def recommendation(
    rec_id="ocid1.optimizerrecommendation.oc1..one",
    *,
    name="Compute Rightsizing",
    status="PENDING",
    lifecycle_state="ACTIVE",
    saving=42.5,
    importance="HIGH",
    metadata=None,
):
    now = datetime(2026, 10, 2, tzinfo=UTC)
    return obj(
        id=rec_id,
        compartment_id=TENANCY,
        category_id="ocid1.optimizercategory.oc1..cost",
        name=name,
        description="Native recommendation",
        importance=importance,
        lifecycle_state=lifecycle_state,
        estimated_cost_saving=saving,
        status=status,
        time_status_begin=now,
        time_status_end=None,
        time_created=now,
        time_updated=now,
        extended_metadata=metadata,
    )


def resource_action(
    action_id="ocid1.optimizerresourceaction.oc1..one",
    *,
    recommendation_id="ocid1.optimizerrecommendation.oc1..one",
    resource_id="ocid1.instance.oc1.sa-saopaulo-1.resource",
    resource_type="Instance",
    compartment_id=COMP_A,
    status="PENDING",
    saving=21.25,
    metadata=None,
    extended_metadata=None,
):
    now = datetime(2026, 10, 2, tzinfo=UTC)
    return obj(
        id=action_id,
        recommendation_id=recommendation_id,
        name="instance-a",
        resource_id=resource_id,
        resource_type=resource_type,
        compartment_id=compartment_id,
        compartment_name="App",
        action=obj(type="KB_ARTICLE", description="Resize safely", url="/advisor/docs"),
        lifecycle_state="ACTIVE",
        estimated_cost_saving=saving,
        status=status,
        time_status_begin=now,
        time_status_end=None,
        time_created=now,
        time_updated=now,
        metadata=metadata,
        extended_metadata=extended_metadata,
    )


def service_error(status, code="ServiceError"):
    return oci.exceptions.ServiceError(status, code, {}, "raw-secret-service-message")


def run(factory, snap=None, discovery=None):
    service = OciCloudAdvisorService(client_factory_cls=lambda _snapshot: factory)
    return service.collect(snap or snapshot(), discovery=discovery)


def test_client_factory_caches_optimizer_per_region(monkeypatch):
    created = []

    class DummyOptimizer:
        def __init__(self, config, **kwargs):
            created.append((config["region"], kwargs))

    monkeypatch.setattr(oci.optimizer, "OptimizerClient", DummyOptimizer)
    factory = OciClientFactory(snapshot())

    first = factory.optimizer("sa-saopaulo-1")
    second = factory.optimizer("sa-saopaulo-1")
    third = factory.optimizer("us-ashburn-1")

    assert first is second
    assert third is not first
    assert len(created) == 2
    assert PRIVATE_KEY not in repr(factory)
    assert PASSPHRASE not in repr(factory)


def test_zero_recommendations_is_successful_zero_not_unknown():
    result = run(FakeFactory())

    assert result.status == "success"
    assert result.recommendation_count == 0
    assert result.resource_action_count == 0
    assert result.coverage == {"recommendations": True, "resource_actions": True}


def test_recommendation_fields_financial_data_status_and_timestamps_are_preserved():
    rec = recommendation(status="DISMISSED", saving=99.5, importance="CRITICAL")
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[rec]]),
                list_resource_actions=PagedCall([[]]),
            )
        )
    )

    normalized = result.recommendations[0]
    assert normalized.recommendation_id == rec.id
    assert normalized.name == "Compute Rightsizing"
    assert normalized.status == "DISMISSED"
    assert normalized.lifecycle_state == "ACTIVE"
    assert normalized.importance == "CRITICAL"
    assert normalized.native_estimated_savings == 99.5
    assert normalized.currency is None
    assert normalized.time_created == rec.time_created
    assert normalized.time_updated == rec.time_updated
    assert normalized.scope_match == "unknown"


def test_unknown_recommendation_name_and_optional_fields_do_not_crash():
    rec = recommendation(name="NEW_ORACLE_TYPE", saving=None, metadata=None)
    rec.description = None
    rec.time_updated = None

    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[rec]]),
                list_resource_actions=PagedCall([[]]),
            )
        )
    )

    normalized = result.recommendations[0]
    assert normalized.name == "NEW_ORACLE_TYPE"
    assert normalized.native_estimated_savings is None
    assert normalized.currency is None
    assert normalized.description is None
    assert normalized.time_updated is None


def test_three_page_recommendation_pagination_and_native_id_deduplication():
    duplicate = recommendation("rec-2")
    listing = PagedCall(
        [
            [recommendation("rec-1")],
            [duplicate, recommendation("rec-3")],
            [duplicate],
        ]
    )
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=listing,
                list_resource_actions=PagedCall([[]]),
            )
        )
    )

    assert [item.recommendation_id for item in result.recommendations] == [
        "rec-1",
        "rec-2",
        "rec-3",
    ]
    assert result.pages["recommendations"] == 3
    assert [call[1]["page"] for call in listing.calls] == [None, "page-2", "page-3"]


def test_resource_actions_preserve_parent_resource_action_saving_and_status():
    rec = recommendation()
    action = resource_action(
        status="POSTPONED",
        saving=12.75,
        extended_metadata={
            "CurrentShape": {"name": "VM.Standard.E5.Flex"},
            "RecommendedShape": {"name": "VM.Standard.E5.Flex"},
            "Region": "sa-saopaulo-1",
        },
    )
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[rec]]),
                list_resource_actions=PagedCall([[action]]),
            )
        )
    )

    normalized = result.resource_actions[0]
    assert normalized.recommendation_id == rec.id
    assert normalized.resource_id == action.resource_id
    assert normalized.resource_type == "Instance"
    assert normalized.status == "POSTPONED"
    assert normalized.native_estimated_savings == 12.75
    assert normalized.currency is None
    assert normalized.action["type"] == "KB_ARTICLE"
    assert normalized.action["description"] == "Resize safely"
    assert normalized.raw_metadata["CurrentShape"]["name"] == "VM.Standard.E5.Flex"
    assert normalized.scope_match == "inside"


def test_resource_action_without_resource_id_is_supported():
    action = resource_action(resource_id=None)
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[action]]),
            )
        )
    )

    assert result.resource_actions[0].resource_id is None
    assert result.resource_actions[0].inventory_match is None


def test_three_page_resource_action_pagination_and_deduplication():
    repeated = resource_action("action-2")
    listing = PagedCall(
        [
            [resource_action("action-1")],
            [repeated, resource_action("action-3")],
            [repeated],
        ]
    )
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=listing,
            )
        )
    )

    assert [item.resource_action_id for item in result.resource_actions] == [
        "action-1",
        "action-2",
        "action-3",
    ]
    assert result.pages["resource_actions"] == 3


def test_different_action_ids_for_same_resource_are_not_collapsed():
    a1 = resource_action("action-1")
    a2 = resource_action("action-2")
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[a1, a2]]),
            )
        )
    )

    assert len(result.resource_actions) == 2
    assert result.resource_actions[0].resource_id == result.resource_actions[1].resource_id


def test_scope_filters_outside_compartment_but_keeps_recommendation_with_in_scope_action():
    inside = resource_action("inside", compartment_id=COMP_A)
    outside = resource_action("outside", compartment_id=COMP_B)
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[inside, outside]]),
            )
        )
    )

    assert [item.resource_action_id for item in result.resource_actions] == ["inside"]
    assert result.recommendations[0].scope_match == "inside"


def test_scope_filters_outside_region_from_metadata():
    action = resource_action(metadata={"Region": "us-ashburn-1"})
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[action]]),
            )
        )
    )

    assert result.resource_actions == []
    assert result.recommendations == []


def test_scope_unknown_is_explicit_and_not_silently_dropped():
    action = resource_action(compartment_id=None, metadata={})
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[action]]),
            )
        )
    )

    assert result.resource_actions[0].scope_match == "unknown"
    assert any(w.category == "scope_unknown" for w in result.warnings)


def test_root_subtree_uses_one_server_side_subtree_query():
    class IdentityPagedCall(PagedCall):
        def __call__(self, *args, page=None, **kwargs):
            self.calls.append((args, dict(kwargs, page=page)))
            index = 0 if page is None else int(str(page).split("-")[-1]) - 1
            next_page = f"page-{index + 2}" if index + 1 < len(self.pages) else None
            return response(self.pages[index], next_page, collection=False)

    identity_listing = IdentityPagedCall([[obj(id=COMP_A)], [obj(id=COMP_B)]])
    rec_listing = PagedCall([[recommendation()]])
    action_listing = PagedCall([[resource_action(compartment_id=COMP_A)]])
    factory = FakeFactory(
        optimizer=obj(
            list_recommendations=rec_listing,
            list_resource_actions=action_listing,
        ),
        identity=obj(list_compartments=identity_listing),
    )

    result = run(
        factory,
        snapshot(compartments=(), include_root=True, include_subcompartments=True),
    )

    assert result.status == "success"
    assert len(rec_listing.calls) == 1
    assert rec_listing.calls[0][1]["compartment_id"] == TENANCY
    assert rec_listing.calls[0][1]["compartment_id_in_subtree"] is True
    assert len(action_listing.calls) == 1


def test_explicit_subcompartment_scope_is_resolved_then_queried_without_tenancy_wide_scan():
    def list_compartments(compartment_id, page=None, **kwargs):
        assert page is None
        assert kwargs["access_level"] == "ACCESSIBLE"
        return response(
            [obj(id=COMP_B)] if compartment_id == COMP_A else [],
            collection=False,
        )

    rec_listing = PagedCall([[]])
    action_listing = PagedCall([[]])
    factory = FakeFactory(
        optimizer=obj(
            list_recommendations=rec_listing,
            list_resource_actions=action_listing,
        ),
        identity=obj(list_compartments=list_compartments),
    )

    run(factory, snapshot(compartments=(COMP_A,), include_subcompartments=True))

    compartments = [call[1]["compartment_id"] for call in rec_listing.calls]
    assert compartments == [COMP_A, COMP_B]
    assert all(call[1]["compartment_id_in_subtree"] is False for call in rec_listing.calls)


def test_discovery_correlation_true_false_and_missing_resource_id_are_factual_only():
    found = resource_action("found", resource_id="resource-found")
    missing = resource_action("missing", resource_id="resource-missing")
    aggregate = resource_action("aggregate", resource_id=None)
    discovery = obj(resources=[obj(resource_id="resource-found")])

    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[found, missing, aggregate]]),
            )
        ),
        discovery=discovery,
    )

    by_id = {item.resource_action_id: item for item in result.resource_actions}
    assert by_id["found"].inventory_match is True
    assert by_id["missing"].inventory_match is False
    assert by_id["aggregate"].inventory_match is None
    assert any(w.category == "resource_not_in_discovery_inventory" for w in result.warnings)


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (service_error(403, "NotAuthorizedOrNotFound"), "authorization_failed"),
        (service_error(429, "TooManyRequests"), "service_throttled"),
        (requests_exceptions.Timeout("secret timeout"), "timeout"),
        (service_error(503, "ServiceUnavailable"), "service_unavailable"),
    ],
)
def test_recommendation_failure_is_partial_not_false_zero(failure, category):
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[]], failure_page=0, failure=failure),
                list_resource_actions=PagedCall([[]]),
            )
        )
    )

    assert result.status == "partial"
    assert result.recommendation_count is None
    assert result.resource_action_count == 0
    assert result.coverage["recommendations"] is False
    assert any(error.category == category for error in result.errors)
    assert "raw-secret-service-message" not in repr(result)
    assert "secret timeout" not in repr(result)


def test_recommendations_survive_when_resource_actions_fail():
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall(
                    [[]],
                    failure_page=0,
                    failure=service_error(403, "NotAuthorized"),
                ),
            )
        )
    )

    assert result.status == "partial"
    assert result.recommendation_count == 1
    assert result.resource_action_count is None
    assert len(result.recommendations) == 1


def test_401_is_fatal_but_service_authorization_is_not_connection_status_logic():
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall(
                    [[]],
                    failure_page=0,
                    failure=service_error(401, "NotAuthenticated"),
                ),
                list_resource_actions=PagedCall([[]]),
            )
        )
    )

    assert result.status == "failed"
    assert any(error.fatal and error.category == "authentication_failed" for error in result.errors)
    assert not hasattr(result, "connection_status")


def test_credential_resolution_failure_stops_before_client_creation():
    def resolver(_db, _account_id):
        raise OciCredentialResolutionError("configuration_missing", "OCI config missing")

    class FailFactory:
        def __init__(self, _snapshot):
            pytest.fail("client must not be created")

    result = OciCloudAdvisorService(
        credential_resolver=resolver,
        client_factory_cls=FailFactory,
    ).collect_account(None, 99)

    assert result.status == "failed"
    assert result.errors[0].category == "configuration_missing"


def test_provider_mismatch_from_shared_resolver_is_preserved():
    def resolver(_db, _account_id):
        raise OciCredentialResolutionError("provider_mismatch", "Cloud account provider is not OCI")

    result = OciCloudAdvisorService(credential_resolver=resolver).collect_account(None, 1)

    assert result.status == "failed"
    assert result.errors[0].category == "provider_mismatch"


def test_normalized_payload_and_errors_never_expose_credentials_or_signer_data():
    rec = recommendation(metadata={"privateKey": PRIVATE_KEY, "SafeField": "ok"})
    action = resource_action(
        metadata={"passphrase": PASSPHRASE, "Region": "sa-saopaulo-1"},
        extended_metadata={"signer": "secret", "CurrentShape": {"name": "VM.Standard"}},
    )
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[rec]]),
                list_resource_actions=PagedCall([[action]]),
            )
        )
    )

    text = repr(result)
    assert PRIVATE_KEY not in text
    assert PASSPHRASE not in text
    assert "signer" not in text.lower()
    assert result.recommendations[0].raw_metadata == {"SafeField": "ok"}
    assert result.resource_actions[0].raw_metadata["Region"] == "sa-saopaulo-1"


def test_cloud_advisor_is_list_only_and_does_not_use_get_or_mutation_endpoints():
    optimizer = obj(
        list_recommendations=PagedCall([[recommendation()]]),
        list_resource_actions=PagedCall([[resource_action()]]),
    )

    result = run(FakeFactory(optimizer=optimizer))

    assert result.status == "success"
    for forbidden in (
        "get_recommendation",
        "get_resource_action",
        "update_recommendation",
        "bulk_apply_recommendations",
        "update_resource_action",
    ):
        assert not hasattr(optimizer, forbidden)


def test_oci_public_collection_capabilities_and_executor_are_enabled():
    capabilities = get_provider_capabilities("oci")

    assert capabilities.manual_collection is True
    assert capabilities.scheduling is True
    assert capabilities.finops_policies is False
    assert has_collection_executor("oci") is True
    assert has_collection_executor("aws") is True


def test_result_contract_contains_no_opportunity_or_finding_entities():
    result = run(
        FakeFactory(
            optimizer=obj(
                list_recommendations=PagedCall([[recommendation()]]),
                list_resource_actions=PagedCall([[resource_action()]]),
            )
        )
    )

    text = repr(result).lower()
    assert "opportunityobservation" not in text
    assert "collectedfinding" not in text
    assert not hasattr(result, "opportunities")
    assert not hasattr(result, "findings")
