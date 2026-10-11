"""Read-only native identity gate; names never authorize replacement allocation."""
def verify_native(record, state):
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    def one(section, field, value):
        matches = [item for item in state[section] if item[field] == value]
        require(len(matches) == 1, section + " missing or ambiguous")
        return matches[0]

    pool = one("pools", "name", record["dataset"].split("/")[0])
    require(str(pool["guid"]) == record["pool_guid"], "Pool GUID changed")
    dataset = one("datasets", "id", record["dataset"])
    require(dataset["guid"]["value"] == record["zvol_guid"], "ZVOL GUID changed")
    require(dataset["volsize"]["parsed"] == record["bytes"], "Unreconciled capacity change")
    extent = one("extents", "id", record["extent_id"])
    require(extent["disk"] == "zvol/" + record["dataset"], "Extent redirected")
    require(extent["serial"] == record["serial"] and extent["naa"] == record["naa"], "Extent identity changed")
    require(extent["enabled"] and not extent["ro"] and not extent["insecure_tpc"], "Extent access changed")
    mapping = one("mappings", "target", record["target_id"])
    require(mapping["extent"] == record["extent_id"] and mapping["lunid"] == record["lun"], "LUN redirected")
    target = one("targets", "id", record["target_id"])
    require(state["basename"] + ":" + target["name"] == record["iqn"], "Target IQN changed")
    require(target["groups"] == [record["group"]], "Target access changed")
    group = record["group"]
    require(group["authmethod"] == "CHAP" and group["auth"] is not None and group["initiator"] is not None, "CHAP and initiator restriction required")
    require(target["auth_networks"] == ["172.30.91.0/24"], "Storage network restriction changed")
    portal = one("portals", "id", group["portal"])
    require(len(portal["listen"]) == 1, "Portal listener count changed")
    listener = portal["listen"][0]
    require(listener["ip"] + ":" + str(listener["port"]) == record["portal"], "Portal changed")
    initiator = one("initiators", "id", group["initiator"])
    require(record["initiators"] and sorted(initiator["initiators"]) == sorted(record["initiators"]), "Initiator ACL changed")


def reconcile_capacity(record, state, planned_bytes):
    """Accept only the old or explicitly planned size, without allocating."""
    if planned_bytes <= record['bytes']:
        raise ValueError('Growth intent must increase capacity')
    matches = [d for d in state['datasets'] if d['id'] == record['dataset']]
    if len(matches) != 1:
        raise ValueError('Dataset missing or ambiguous')
    actual = matches[0]['volsize']['parsed']
    if actual not in (record['bytes'], planned_bytes):
        raise ValueError('Capacity outside recorded growth intent')
    observed = dict(record, bytes=actual)
    verify_native(observed, state)
    return observed
