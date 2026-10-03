"""Read-only native NAS verification; this command cannot allocate or initialize."""
import json
from nas_rpc import NAS
from lab import PRIVATE
from identity import verify_native


def capture(nas):
    state = {key: nas.call(method, *args) for key, method, args in [
        ("pools", "pool.query", []),
        ("datasets", "pool.dataset.query", [[["id", "^", "iscsi_lab/volumes/"]], {"extra": {"properties": ["guid", "volsize"]}}]),
        ("extents", "iscsi.extent.query", []),
        ("targets", "iscsi.target.query", []),
        ("mappings", "iscsi.targetextent.query", []),
        ("portals", "iscsi.portal.query", []),
        ("initiators", "iscsi.initiator.query", []),
    ]}
    state["basename"] = nas.call("iscsi.global.config")["basename"]
    return state


def verify_all():
    records = json.loads((PRIVATE/"native-records.json").read_text())
    state = capture(NAS())
    for record in records:
        verify_native(record, state)
    return records


if __name__ == "__main__":
    records = verify_all()
    print(json.dumps({"native_identities_verified": [r["service"] for r in records],
                      "mutating_api_calls": 0, "filesystem_identity_gate": "still required before writers"}))
