from __future__ import annotations

from typing import Any

def explicit_ref(
    *,
    service: str,
    relationship_type: str,
    target_euid: Any,
    field_path: str,
    timestamp: str,
    target_kind: str | None = None,
) -> dict[str, Any] | None:
    euid = str(target_euid or "").strip()
    if not euid:
        return None
    ref: dict[str, Any] = {
        "system": service,
        "service": service,
        "root_euid": euid,
        "relationship_type": relationship_type,
        "target_euid": euid,
        "field_path": field_path,
        "source_field": field_path,
        "label": f"{relationship_type}: {euid}",
        "recorded_at": timestamp,
        "inferred": False,
    }
    if target_kind:
        ref["target_kind"] = target_kind
    return ref


def compact_refs(refs: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for ref in refs:
        if not ref:
            continue
        key = (
            str(ref.get("service") or ""),
            str(ref.get("relationship_type") or ""),
            str(ref.get("target_euid") or ""),
            str(ref.get("field_path") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        compacted.append(ref)
    return compacted


def tapdb_graph_payload(*, refs: list[dict[str, Any] | None], timestamp: str) -> dict[str, Any]:
    del timestamp
    return compact_refs(refs)


def payload_with_tapdb_graph(
    payload: dict[str, Any],
    *,
    refs: list[dict[str, Any] | None],
    timestamp: str,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flattened = dict(payload)
    existing_properties = flattened.pop("properties", None)
    properties = dict(existing_properties) if isinstance(existing_properties, dict) else {}
    properties.update(flattened)
    external_payload = dict(properties.get("external_payload") or {})
    external_payload["tapdb_graph"] = tapdb_graph_payload(refs=refs, timestamp=timestamp)
    properties["external_payload"] = external_payload
    if graph is not None:
        properties["graph"] = graph
    return {"properties": properties}


def replace_instance_properties(instance: Any, payload: dict[str, Any]) -> None:
    existing = dict(getattr(instance, "json_addl", {}) or {})
    existing_properties = existing.get("properties")
    properties = dict(existing_properties) if isinstance(existing_properties, dict) else {}
    flattened = dict(payload)
    flattened.pop("properties", None)
    properties.update(flattened)
    instance.json_addl = {"properties": properties}


def expected_fanout_graph(
    *,
    node_kind: str,
    relationship_type: str,
    expected_fanout_max: int,
) -> dict[str, Any]:
    return {
        "node_kind": node_kind,
        "role": node_kind,
        "expected_fanout_max": int(expected_fanout_max),
        "fanout_reason": (
            f"{node_kind} intentionally fans out through {relationship_type} relationships"
        ),
        "fanout": {
            "classification": "expected",
            "relationship_type": relationship_type,
            "expected_fanout_max": int(expected_fanout_max),
        },
    }


def dewey_refs_from_inputs(
    *,
    artifact_set_euid: str | None = None,
    artifact_euids: list[str] | None = None,
    input_references: list[dict[str, Any]] | None = None,
    timestamp: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any] | None] = []
    refs.append(
        explicit_ref(
            service="dewey",
            relationship_type="uses_fastq_artifact",
            target_euid=artifact_set_euid,
            field_path="artifact_set_euid",
            timestamp=timestamp,
            target_kind="artifact_set",
        )
    )
    for index, artifact_euid in enumerate(list(artifact_euids or [])):
        refs.append(
            explicit_ref(
                service="dewey",
                relationship_type="uses_fastq_artifact",
                target_euid=artifact_euid,
                field_path=f"artifact_euids[{index}]",
                timestamp=timestamp,
                target_kind="artifact",
            )
        )
    for index, reference in enumerate(list(input_references or [])):
        if not isinstance(reference, dict):
            continue
        reference_type = str(reference.get("reference_type") or "").strip()
        if reference_type == "artifact_euid":
            target_euid = reference.get("artifact_euid") or reference.get("value")
            target_kind = "artifact"
        elif reference_type == "artifact_set_euid":
            target_euid = reference.get("artifact_set_euid") or reference.get("value")
            target_kind = "artifact_set"
        elif reference.get("artifact_euid"):
            target_euid = reference.get("artifact_euid")
            target_kind = "artifact"
        else:
            continue
        refs.append(
            explicit_ref(
                service="dewey",
                relationship_type="uses_fastq_artifact",
                target_euid=target_euid,
                field_path=f"input_references[{index}]",
                timestamp=timestamp,
                target_kind=target_kind,
            )
        )
        for member_index, member_euid in enumerate(list(reference.get("artifact_euids") or [])):
            refs.append(
                explicit_ref(
                    service="dewey",
                    relationship_type="uses_fastq_artifact",
                    target_euid=member_euid,
                    field_path=f"input_references[{index}].artifact_euids[{member_index}]",
                    timestamp=timestamp,
                    target_kind="artifact",
                )
            )
    return compact_refs(refs)
