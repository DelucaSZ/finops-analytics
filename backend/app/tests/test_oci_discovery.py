from __future__ import annotations

from types import SimpleNamespace

import oci
import pytest
from requests import exceptions as requests_exceptions

from app.services.collection_executors import has_collection_executor
from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory, list_all_pages
from app.services.oci_credentials import OciCredentialResolutionError
from app.services.oci_discovery import OciDiscoveryService
from app.services.provider_capabilities import get_provider_capabilities

TENANCY = "ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
COMP_A = "ocid1.compartment.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
COMP_B = "ocid1.compartment.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
COMP_C = "ocid1.compartment.oc1..cccccccccccccccccccccccccccccccc"
AD1 = "SA-SAOPAULO-1-AD-1"
AD2 = "SA-SAOPAULO-1-AD-2"
PRIVATE_KEY_MARKER = "-----BEGIN PRIVATE KEY-----SECRET-DISCOVERY-----END PRIVATE KEY-----"
PASSPHRASE_MARKER = "DISCOVERY-PASSPHRASE-SECRET"


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def response(data, next_page: str | None = None):
    headers = {"opc-next-page": next_page} if next_page else {}
    return obj(data=data, headers=headers)


class PagedCall:
    def __init__(self, pages=None, *, wrap=None, failure_page=None, failure=None):
        self.pages = pages if pages is not None else [[]]
        self.wrap = wrap or (lambda items: items)
        self.failure_page = failure_page
        self.failure = failure or RuntimeError("paged failure")
        self.calls = []

    def __call__(self, *args, page=None, **kwargs):
        self.calls.append((args, dict(kwargs, page=page)))
        index = 0 if page is None else int(str(page).split("-")[-1]) - 1
        if self.failure_page == index:
            raise self.failure
        next_page = f"page-{index + 2}" if index + 1 < len(self.pages) else None
        return response(self.wrap(self.pages[index]), next_page)


class FakeFactory:
    def __init__(
        self,
        *,
        search=None,
        identity=None,
        compute=None,
        block=None,
        network=None,
    ):
        self.search_client = search or obj(
            search_resources=PagedCall([[]], wrap=lambda x: obj(items=x))
        )
        self.identity_client = identity or obj(
            list_availability_domains=lambda _tenancy: response([obj(name=AD1)]),
            list_compartments=PagedCall([[]]),
        )
        self.compute_client = compute or obj(
            list_instances=PagedCall([[]]),
            list_volume_attachments=PagedCall([[]]),
            list_boot_volume_attachments=PagedCall([[]]),
        )
        self.block_client = block or obj(
            list_volumes=PagedCall([[]]),
            list_boot_volumes=PagedCall([[]]),
        )
        self.network_client = network or obj(list_public_ips=PagedCall([[]]))
        self.requests = []

    def _get(self, service, region, client):
        self.requests.append((service, region))
        return client

    def resource_search(self, region):
        return self._get("resource_search", region, self.search_client)

    def identity(self, region):
        return self._get("identity", region, self.identity_client)

    def compute(self, region):
        return self._get("compute", region, self.compute_client)

    def blockstorage(self, region):
        return self._get("block_storage", region, self.block_client)

    def virtual_network(self, region):
        return self._get("virtual_network", region, self.network_client)


class RegionalFactory(FakeFactory):
    def __init__(self, *, compute_by_region=None, network_by_region=None, **kwargs):
        super().__init__(**kwargs)
        self.compute_by_region = compute_by_region or {}
        self.network_by_region = network_by_region or {}

    def compute(self, region):
        client = self.compute_by_region.get(region, self.compute_client)
        return self._get("compute", region, client)

    def virtual_network(self, region):
        client = self.network_by_region.get(region, self.network_client)
        return self._get("virtual_network", region, client)


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
        user_ocid="ocid1.user.oc1..dddddddddddddddddddddddddddddddd",
        fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
        region="sa-saopaulo-1",
        scope_regions=tuple(regions),
        compartment_ocids=tuple(compartments),
        include_root_compartment=include_root,
        include_subcompartments=include_subcompartments,
        private_key_pem=PRIVATE_KEY_MARKER,
        private_key_password=PASSPHRASE_MARKER,
    )


def run(factory: FakeFactory, snap=None):
    service = OciDiscoveryService(client_factory_cls=lambda _snapshot: factory)
    return service.discover(snap or snapshot())


def search_item(
    resource_id,
    resource_type,
    *,
    region="sa-saopaulo-1",
    compartment=COMP_A,
    state="AVAILABLE",
    freeform_tags=None,
    defined_tags=None,
):
    return obj(
        identifier=resource_id,
        resource_type=resource_type,
        display_name=f"search-{resource_id[-4:]}",
        region=region,
        compartment_id=compartment,
        lifecycle_state=state,
        availability_domain=None,
        freeform_tags=freeform_tags,
        defined_tags=defined_tags,
        time_created=None,
    )


def instance(
    resource_id,
    *,
    state="RUNNING",
    compartment=COMP_A,
    ad=AD1,
    shape="VM.Standard.E5.Flex",
    ocpus=2.0,
    memory=16.0,
    freeform_tags=None,
    defined_tags=None,
):
    shape_config = (
        None if ocpus is None and memory is None else obj(ocpus=ocpus, memory_in_gbs=memory)
    )
    return obj(
        id=resource_id,
        display_name="compute",
        compartment_id=compartment,
        lifecycle_state=state,
        availability_domain=ad,
        fault_domain="FAULT-DOMAIN-1",
        shape=shape,
        shape_config=shape_config,
        time_created=None,
        freeform_tags=freeform_tags or {},
        defined_tags=defined_tags or {},
    )


def volume(resource_id, *, compartment=COMP_A, ad=AD1, tags=None):
    return obj(
        id=resource_id,
        display_name="volume",
        compartment_id=compartment,
        lifecycle_state="AVAILABLE",
        availability_domain=ad,
        size_in_gbs=100,
        vpus_per_gb=10,
        is_auto_tune_enabled=False,
        time_created=None,
        freeform_tags=tags or {},
        defined_tags={},
    )


def boot_volume(resource_id, *, compartment=COMP_A, ad=AD1):
    return obj(
        id=resource_id,
        display_name="boot",
        compartment_id=compartment,
        lifecycle_state="AVAILABLE",
        availability_domain=ad,
        size_in_gbs=50,
        vpus_per_gb=10,
        time_created=None,
        freeform_tags={},
        defined_tags={},
    )


def public_ip(resource_id, *, assigned=None, lifetime="RESERVED", ad=None, tags=None):
    return obj(
        id=resource_id,
        display_name="public-ip",
        compartment_id=COMP_A,
        lifecycle_state="AVAILABLE",
        availability_domain=ad,
        lifetime=lifetime,
        ip_address="203.0.113.10",
        assigned_entity_id=assigned,
        assigned_entity_type="PRIVATE_IP" if assigned else None,
        time_created=None,
        freeform_tags=tags or {},
        defined_tags={"Operations": {"Status": "Ativo"}} if tags else {},
    )


def service_error(status, code="ServiceError", message="raw-secret-service-message"):
    return oci.exceptions.ServiceError(status, code, {}, message)


def test_paginator_consumes_three_pages():
    call = PagedCall([[1], [2, 3], [4]])

    result = list_all_pages(call)

    assert result.items == [1, 2, 3, 4]
    assert result.pages == 3
    assert [entry[1]["page"] for entry in call.calls] == [None, "page-2", "page-3"]


def test_scope_one_region_and_explicit_compartment():
    factory = FakeFactory()
    result = run(factory)

    assert result.status == "success"
    assert result.regions_scanned == ("sa-saopaulo-1",)
    assert result.compartments_scanned == (COMP_A,)
    assert {region for _, region in factory.requests} == {"sa-saopaulo-1"}


def test_scope_multiple_regions_are_respected_without_implicit_regions():
    factory = FakeFactory()
    snap = snapshot(regions=("sa-saopaulo-1", "us-ashburn-1"))

    result = run(factory, snap)

    assert result.regions_scanned == ("sa-saopaulo-1", "us-ashburn-1")
    requested_regions = {region for _, region in factory.requests}
    assert requested_regions == {"sa-saopaulo-1", "us-ashburn-1"}


def test_empty_scope_regions_means_no_regional_collection():
    factory = FakeFactory()

    result = run(factory, snapshot(regions=()))

    assert result.status == "success"
    assert result.regions_scanned == ()
    assert result.resources == []
    assert factory.requests == []


def test_root_inclusion_and_exclusion_are_deterministic():
    excluded = run(FakeFactory(), snapshot(compartments=(), include_root=False))
    included = run(FakeFactory(), snapshot(compartments=(), include_root=True))

    assert excluded.compartments_scanned == ()
    assert included.compartments_scanned == (TENANCY,)


def test_subcompartments_disabled_does_not_call_list_compartments():
    listing = PagedCall([[obj(id=COMP_B)]])
    factory = FakeFactory(
        identity=obj(
            list_availability_domains=lambda _tenancy: response([obj(name=AD1)]),
            list_compartments=listing,
        )
    )

    result = run(factory, snapshot(include_subcompartments=False))

    assert result.compartments_scanned == (COMP_A,)
    assert listing.calls == []


def test_subcompartments_expand_only_configured_roots_and_deduplicate_child():
    def list_children(compartment_id, page=None, **_kwargs):
        assert page is None
        mapping = {
            COMP_A: [obj(id=COMP_B)],
            COMP_B: [obj(id=COMP_C)],
            COMP_C: [],
        }
        return response(mapping.get(compartment_id, []))

    factory = FakeFactory(
        identity=obj(
            list_availability_domains=lambda _tenancy: response([obj(name=AD1)]),
            list_compartments=list_children,
        )
    )
    snap = snapshot(
        compartments=(COMP_A, COMP_B),
        include_subcompartments=True,
    )

    result = run(factory, snap)

    assert result.compartments_scanned == (COMP_A, COMP_B, COMP_C)
    assert result.compartments_scanned.count(COMP_B) == 1


def test_root_subtree_uses_single_tenancy_subtree_listing_with_pagination():
    listing = PagedCall([[obj(id=COMP_A)], [obj(id=COMP_B)], [obj(id=COMP_C)]])
    factory = FakeFactory(
        identity=obj(
            list_availability_domains=lambda _tenancy: response([obj(name=AD1)]),
            list_compartments=listing,
        )
    )

    result = run(
        factory,
        snapshot(compartments=(), include_root=True, include_subcompartments=True),
    )

    assert result.compartments_scanned == (TENANCY, COMP_A, COMP_B, COMP_C)
    assert len(listing.calls) == 3
    first_kwargs = listing.calls[0][1]
    assert first_kwargs["compartment_id_in_subtree"] is True
    assert first_kwargs["access_level"] == "ACCESSIBLE"


def test_identity_authorization_failure_is_partial_not_empty_scope_success():
    listing = PagedCall(
        [[]],
        failure_page=0,
        failure=service_error(403, "NotAuthorizedOrNotFound"),
    )
    factory = FakeFactory(
        identity=obj(
            list_availability_domains=lambda _tenancy: response([obj(name=AD1)]),
            list_compartments=listing,
        )
    )

    result = run(factory, snapshot(include_subcompartments=True))

    assert result.status == "partial"
    assert result.compartments_scanned == (COMP_A,)
    assert any(error.category == "authorization_failed" for error in result.errors)
    assert all(value is None for value in result.counts_by_type.values())


def test_resource_search_three_pages_tags_and_unknown_type():
    search = obj(
        search_resources=PagedCall(
            [
                [search_item("ocid1.instance.x", "Instance", freeform_tags={"Owner": "FinOps"})],
                [
                    search_item(
                        "ocid1.volume.y",
                        "Volume",
                        defined_tags={"Operations": {"Status": "Ativo"}},
                    )
                ],
                [search_item("ocid1.widget.z", "UnfamiliarWidget")],
            ],
            wrap=lambda items: obj(items=items),
        )
    )
    factory = FakeFactory(search=search)

    result = run(factory)

    by_id = {resource.resource_id: resource for resource in result.resources}
    assert by_id["ocid1.instance.x"].freeform_tags == {"Owner": "FinOps"}
    assert by_id["ocid1.volume.y"].defined_tags == {"Operations": {"Status": "Ativo"}}
    assert by_id["ocid1.widget.z"].resource_type == "oci_resource"
    assert by_id["ocid1.widget.z"].freeform_tags == {}
    assert by_id["ocid1.widget.z"].defined_tags == {}
    assert by_id["ocid1.widget.z"].attributes["native_resource_type"] == "UnfamiliarWidget"


def test_resource_search_discards_out_of_scope_region_and_compartment():
    search = obj(
        search_resources=PagedCall(
            [
                [
                    search_item("ocid1.instance.good", "Instance"),
                    search_item("ocid1.instance.region", "Instance", region="us-phoenix-1"),
                    search_item("ocid1.instance.comp", "Instance", compartment=COMP_B),
                ]
            ],
            wrap=lambda items: obj(items=items),
        )
    )

    result = run(FakeFactory(search=search))

    ids = {resource.resource_id for resource in result.resources}
    assert "ocid1.instance.good" in ids
    assert "ocid1.instance.region" not in ids
    assert "ocid1.instance.comp" not in ids


def test_resource_search_authorization_error_preserves_wave1_lists_and_marks_partial():
    search = obj(
        search_resources=PagedCall(
            [[]],
            wrap=lambda items: obj(items=items),
            failure_page=0,
            failure=service_error(403, "NotAuthorized"),
        )
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.listed")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(search=search, compute=compute))

    assert result.status == "partial"
    assert result.counts_by_type["compute_instance"] == 1
    assert any(r.resource_id == "ocid1.instance.listed" for r in result.resources)
    assert any(error.source == "resource_search" for error in result.errors)


def test_resource_search_transient_error_is_partial_and_service_inventory_survives():
    search = obj(
        search_resources=PagedCall(
            [[]],
            wrap=lambda items: obj(items=items),
            failure_page=0,
            failure=service_error(500, "InternalError"),
        )
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.search-fallback")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(search=search, compute=compute))

    assert result.status == "partial"
    assert result.counts_by_type["compute_instance"] == 1
    assert any(error.category == "service_unavailable" for error in result.errors)


def test_compute_partial_failure_in_one_region_preserves_other_region():
    sa_compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.sa")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )
    ashburn_compute = obj(
        list_instances=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(403, "NotAuthorized"),
        ),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )
    factory = RegionalFactory(
        compute_by_region={
            "sa-saopaulo-1": sa_compute,
            "us-ashburn-1": ashburn_compute,
        }
    )

    result = run(factory, snapshot(regions=("sa-saopaulo-1", "us-ashburn-1")))

    kept = next(
        resource for resource in result.resources if resource.resource_id == "ocid1.instance.sa"
    )
    assert kept.region == "sa-saopaulo-1"
    assert result.status == "partial"
    assert result.observed_counts_by_type["compute_instance"] == 1
    assert result.counts_by_type["compute_instance"] is None


def test_compute_running_stopped_flex_and_non_flex_are_normalized():
    compute = obj(
        list_instances=PagedCall(
            [
                [
                    instance("ocid1.instance.running", state="RUNNING"),
                    instance("ocid1.instance.stopped", state="STOPPED", ocpus=None, memory=None),
                ]
            ]
        ),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))

    by_id = {r.resource_id: r for r in result.resources}
    assert by_id["ocid1.instance.running"].lifecycle_state == "RUNNING"
    assert by_id["ocid1.instance.running"].attributes["ocpus"] == 2.0
    assert by_id["ocid1.instance.running"].attributes["memory_in_gbs"] == 16.0
    assert by_id["ocid1.instance.stopped"].lifecycle_state == "STOPPED"
    assert "ocpus" not in by_id["ocid1.instance.stopped"].attributes


def test_compute_pagination_and_multiple_compartments_use_list_not_get():
    calls = []

    def list_instances(compartment_id, page=None):
        calls.append((compartment_id, page))
        if compartment_id == COMP_A and page is None:
            return response([instance("ocid1.instance.a", compartment=COMP_A)], "page-2")
        if compartment_id == COMP_A:
            return response([instance("ocid1.instance.a2", compartment=COMP_A)])
        return response([instance("ocid1.instance.b", compartment=COMP_B)])

    compute = obj(
        list_instances=list_instances,
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )
    factory = FakeFactory(compute=compute)

    result = run(factory, snapshot(compartments=(COMP_A, COMP_B)))

    assert result.counts_by_type["compute_instance"] == 3
    assert (COMP_A, None) in calls
    assert (COMP_A, "page-2") in calls
    assert (COMP_B, None) in calls
    assert not hasattr(compute, "get_instance")


def test_one_hundred_instances_do_not_trigger_n_plus_one_get_calls():
    items = [instance(f"ocid1.instance.{index}") for index in range(100)]
    list_instances = PagedCall([items])
    compute = obj(
        list_instances=list_instances,
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))

    assert result.counts_by_type["compute_instance"] == 100
    assert len(list_instances.calls) == 1
    assert not hasattr(compute, "get_instance")


def test_search_and_compute_deduplicate_by_ocid_and_service_state_wins():
    resource_id = "ocid1.instance.same"
    search = obj(
        search_resources=PagedCall(
            [[search_item(resource_id, "Instance", state="RUNNING", freeform_tags={"old": "tag"})]],
            wrap=lambda items: obj(items=items),
        )
    )
    compute = obj(
        list_instances=PagedCall(
            [
                [
                    instance(
                        resource_id,
                        state="STOPPED",
                        freeform_tags={"Owner": "Platform"},
                        defined_tags={"Operations": {"Status": "Ativo"}},
                    )
                ]
            ]
        ),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(search=search, compute=compute))

    matches = [r for r in result.resources if r.resource_id == resource_id]
    assert len(matches) == 1
    resource = matches[0]
    assert resource.lifecycle_state == "STOPPED"
    assert resource.attributes["search_lifecycle_state"] == "RUNNING"
    assert resource.freeform_tags == {"Owner": "Platform"}
    assert resource.defined_tags == {"Operations": {"Status": "Ativo"}}
    assert set(resource.sources) == {"resource_search", "compute_api"}
    assert any(w.category == "search_service_state_conflict" for w in result.warnings)


def test_service_only_and_search_only_resources_get_consistency_state_without_failure():
    search = obj(
        search_resources=PagedCall(
            [[search_item("ocid1.instance.searchonly", "Instance")]],
            wrap=lambda items: obj(items=items),
        )
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.serviceonly")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(search=search, compute=compute))

    assert result.status == "success"
    by_id = {r.resource_id: r for r in result.resources}
    assert by_id["ocid1.instance.searchonly"].attributes["discovery_consistency"] == "search_only"
    assert by_id["ocid1.instance.serviceonly"].attributes["discovery_consistency"] == "service_only"
    assert len([w for w in result.warnings if w.category == "search_eventual_consistency"]) == 2


def test_block_volume_pagination_collects_all_pages_and_marks_service_only_resource():
    list_volumes = PagedCall(
        [
            [volume("ocid1.volume.page1")],
            [volume("ocid1.volume.page2")],
            [volume("ocid1.volume.page3")],
        ]
    )
    block = obj(
        list_volumes=list_volumes,
        list_boot_volumes=PagedCall([[]]),
    )

    result = run(FakeFactory(block=block))

    assert result.counts_by_type["block_volume"] == 3
    assert len(list_volumes.calls) == 3
    assert list_volumes.calls[0][0] == ()
    assert list_volumes.calls[0][1]["compartment_id"] == COMP_A
    by_id = {resource.resource_id: resource for resource in result.resources}
    assert by_id["ocid1.volume.page1"].attributes["discovery_consistency"] == "service_only"


def test_block_volume_attached_unattached_and_multiple_attachments():
    v1 = "ocid1.volume.attached"
    v2 = "ocid1.volume.free"
    attachments = [
        obj(volume_id=v1, instance_id="ocid1.instance.1", lifecycle_state="ATTACHED"),
        obj(volume_id=v1, instance_id="ocid1.instance.2", lifecycle_state="ATTACHED"),
    ]
    block = obj(
        list_volumes=PagedCall([[volume(v1), volume(v2)]]),
        list_boot_volumes=PagedCall([[]]),
    )
    compute = obj(
        list_instances=PagedCall([[]]),
        list_volume_attachments=PagedCall([attachments]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(block=block, compute=compute))

    by_id = {r.resource_id: r for r in result.resources}
    assert by_id[v1].attributes["attachment_count"] == 2
    assert by_id[v2].attributes["attachment_count"] == 0
    assert by_id[v2].attributes["attachment_coverage"] == "complete"
    assert len([r for r in result.relationships if r.relation_type == "volume_attachment"]) == 2


def test_boot_volume_attachment_relationship_and_unrelated_boot_volume():
    b1 = "ocid1.bootvolume.one"
    b2 = "ocid1.bootvolume.two"
    block = obj(
        list_volumes=PagedCall([[]]),
        list_boot_volumes=PagedCall([[boot_volume(b1), boot_volume(b2)]]),
    )
    compute = obj(
        list_instances=PagedCall([[]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall(
            [[obj(boot_volume_id=b1, instance_id="ocid1.instance.1", lifecycle_state="ATTACHED")]]
        ),
    )

    result = run(FakeFactory(block=block, compute=compute))

    by_id = {r.resource_id: r for r in result.resources}
    assert by_id[b1].attributes["attachment_count"] == 1
    assert by_id[b2].attributes["attachment_count"] == 0
    assert any(
        r.source_id == b1 and r.target_id == "ocid1.instance.1" for r in result.relationships
    )


def test_block_storage_partial_failure_preserves_compute_and_count_is_unknown():
    block = obj(
        list_volumes=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(403, "NotAuthorizedOrNotFound"),
        ),
        list_boot_volumes=PagedCall([[]]),
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.kept")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(block=block, compute=compute))

    assert result.status == "partial"
    assert result.counts_by_type["block_volume"] is None
    assert result.counts_by_type["compute_instance"] == 1
    assert any(r.resource_id == "ocid1.instance.kept" for r in result.resources)
    assert any(e.category == "authorization_failed" for e in result.errors)


def test_attachment_failure_never_turns_unknown_relationship_into_zero():
    vol_id = "ocid1.volume.unknown-attachment"
    block = obj(
        list_volumes=PagedCall([[volume(vol_id)]]),
        list_boot_volumes=PagedCall([[]]),
    )
    compute = obj(
        list_instances=PagedCall([[]]),
        list_volume_attachments=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(403, "NotAuthorized"),
        ),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(block=block, compute=compute))

    resource = next(r for r in result.resources if r.resource_id == vol_id)
    assert resource.attributes["attachment_coverage"] == "incomplete"
    assert "attachment_count" not in resource.attributes


def test_public_ip_association_lifetime_tags_and_unassociated_state():
    assigned = "ocid1.privateip.oc1.sa-saopaulo-1.assigned"
    p1 = public_ip("ocid1.publicip.assigned", assigned=assigned, tags={"Owner": "NetOps"})
    p2 = public_ip("ocid1.publicip.free", lifetime="RESERVED")
    network = obj(list_public_ips=PagedCall([[p1, p2]]))

    result = run(FakeFactory(network=network))

    by_id = {r.resource_id: r for r in result.resources}
    assert by_id[p1.id].attributes["is_associated"] is True
    assert by_id[p1.id].attributes["assigned_entity_id"] == assigned
    assert by_id[p1.id].attributes["lifetime"] == "RESERVED"
    assert by_id[p1.id].freeform_tags == {"Owner": "NetOps"}
    assert by_id[p1.id].defined_tags == {"Operations": {"Status": "Ativo"}}
    assert by_id[p2.id].attributes["is_associated"] is False
    assert any(
        rel.relation_type == "public_ip_assignment"
        and rel.source_id == p1.id
        and rel.target_id == assigned
        and rel.target_type == "private_ip"
        for rel in result.relationships
    )


def test_public_ip_enumerates_region_and_each_availability_domain():
    call = PagedCall([[]])
    identity = obj(
        list_availability_domains=lambda _tenancy: response([obj(name=AD1), obj(name=AD2)]),
        list_compartments=PagedCall([[]]),
    )
    factory = FakeFactory(identity=identity, network=obj(list_public_ips=call))

    result = run(factory)

    assert result.counts_by_type["public_ip"] == 0
    scopes = [(args[0], kwargs.get("availability_domain")) for args, kwargs in call.calls]
    assert ("REGION", None) in scopes
    assert ("AVAILABILITY_DOMAIN", AD1) in scopes
    assert ("AVAILABILITY_DOMAIN", AD2) in scopes


def test_public_ip_pagination_collects_every_page():
    calls = []

    def list_public_ips(scope, compartment_id, page=None, availability_domain=None):
        calls.append((scope, compartment_id, page, availability_domain))
        if scope == "REGION" and page is None:
            return response([public_ip("ocid1.publicip.page1")], "page-2")
        if scope == "REGION" and page == "page-2":
            return response([public_ip("ocid1.publicip.page2")])
        return response([])

    result = run(FakeFactory(network=obj(list_public_ips=list_public_ips)))

    assert result.counts_by_type["public_ip"] == 2
    assert any(call[2] == "page-2" for call in calls)


def test_public_ip_region_is_taken_from_each_scanned_region():
    sa_network = obj(list_public_ips=PagedCall([[public_ip("ocid1.publicip.sa")]]))
    ashburn_network = obj(list_public_ips=PagedCall([[public_ip("ocid1.publicip.ashburn")]]))
    factory = RegionalFactory(
        network_by_region={
            "sa-saopaulo-1": sa_network,
            "us-ashburn-1": ashburn_network,
        }
    )

    result = run(factory, snapshot(regions=("sa-saopaulo-1", "us-ashburn-1")))

    by_id = {resource.resource_id: resource for resource in result.resources}
    assert by_id["ocid1.publicip.sa"].region == "sa-saopaulo-1"
    assert by_id["ocid1.publicip.ashburn"].region == "us-ashburn-1"


def test_network_failure_marks_public_ip_count_unknown_without_erasing_other_resources():
    network = obj(
        list_public_ips=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(403, "NotAuthorized"),
        )
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.ok")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(network=network, compute=compute))

    assert result.status == "partial"
    assert result.counts_by_type["public_ip"] is None
    assert result.counts_by_type["compute_instance"] == 1


def test_availability_domain_failure_makes_public_ip_coverage_unknown_but_uses_observed_ads():
    identity = obj(
        list_availability_domains=lambda _tenancy: (_ for _ in ()).throw(service_error(500)),
        list_compartments=PagedCall([[]]),
    )
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.ad-source", ad=AD2)]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )
    public_call = PagedCall([[]])

    result = run(
        FakeFactory(
            identity=identity,
            compute=compute,
            network=obj(list_public_ips=public_call),
        )
    )

    assert result.status == "partial"
    assert result.counts_by_type["public_ip"] is None
    assert any(
        args[0] == "AVAILABILITY_DOMAIN" and kwargs.get("availability_domain") == AD2
        for args, kwargs in public_call.calls
    )


@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (service_error(429, "TooManyRequests"), "service_throttled"),
        (requests_exceptions.Timeout("private URL timeout"), "timeout"),
        (service_error(500, "InternalError"), "service_unavailable"),
    ],
)
def test_partial_transient_failures_are_structured_and_sanitized(error, expected_category):
    compute = obj(
        list_instances=PagedCall([[]], failure_page=0, failure=error),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))

    assert result.status == "partial"
    assert result.counts_by_type["compute_instance"] is None
    assert any(item.category == expected_category for item in result.errors)
    assert "private URL" not in repr(result)
    assert "raw-secret-service-message" not in repr(result)


def test_authentication_failure_is_fatal_and_distinct_from_partial_result():
    compute = obj(
        list_instances=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(401, "NotAuthenticated"),
        ),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))

    assert result.status == "failed"
    assert result.is_failed is True
    assert all(value is None for value in result.counts_by_type.values())
    assert any(error.fatal and error.category == "authentication_failed" for error in result.errors)


def test_credential_resolver_failure_returns_failed_result_without_client_creation():
    def resolver(_db, _account_id):
        raise OciCredentialResolutionError("configuration_missing", "OCI config missing")

    class FailFactory:
        def __init__(self, _snapshot):
            pytest.fail("client factory must not be created after credential resolution failure")

    service = OciDiscoveryService(
        credential_resolver=resolver,
        client_factory_cls=FailFactory,
    )

    result = service.discover_account(None, 99)

    assert result.status == "failed"
    assert result.errors[0].category == "configuration_missing"


def test_discovery_result_and_error_repr_never_contains_credentials():
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.safe")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))
    representation = repr(result)

    assert PRIVATE_KEY_MARKER not in representation
    assert PASSPHRASE_MARKER not in representation
    assert "fingerprint" not in representation.lower()


def test_counts_distinguish_successful_zero_from_failed_unknown():
    successful = run(FakeFactory())
    failed_block = obj(
        list_volumes=PagedCall(
            [[]],
            failure_page=0,
            failure=service_error(403, "NotAuthorizedOrNotFound"),
        ),
        list_boot_volumes=PagedCall([[]]),
    )
    partial = run(FakeFactory(block=failed_block))

    assert successful.counts_by_type["block_volume"] == 0
    assert partial.counts_by_type["block_volume"] is None


def test_no_financial_or_metric_fields_are_emitted():
    compute = obj(
        list_instances=PagedCall([[instance("ocid1.instance.no-finops")]]),
        list_volume_attachments=PagedCall([[]]),
        list_boot_volume_attachments=PagedCall([[]]),
    )

    result = run(FakeFactory(compute=compute))
    text = repr(result).lower()

    for forbidden in ("saving", "monthly_cost", "cpu_utilization", "rightsizing", "price"):
        assert forbidden not in text


def test_oci_capabilities_and_executor_registry_enable_manual_collection():
    capabilities = get_provider_capabilities("oci")

    assert capabilities.manual_collection is True
    assert capabilities.scheduling is False
    assert capabilities.finops_policies is False
    assert has_collection_executor("oci") is True
    assert has_collection_executor("aws") is True


def test_client_factory_caches_clients_per_service_and_region(monkeypatch):
    created = []

    class DummyClient:
        def __init__(self, config, **kwargs):
            created.append((config["region"], kwargs))

    monkeypatch.setattr(oci.core, "ComputeClient", DummyClient)
    factory = OciClientFactory(snapshot())

    first = factory.compute("sa-saopaulo-1")
    second = factory.compute("sa-saopaulo-1")
    third = factory.compute("us-ashburn-1")

    assert first is second
    assert third is not first
    assert len(created) == 2
    assert PRIVATE_KEY_MARKER not in repr(factory)
