"""Read-only native identity gate; names never authorize replacement allocation."""
def verify_native(record, state):
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    def one(section, field, value):
        matches = [item for item in state[section] if item[field] == value]
        require(len(matches) == 1, section + " missing or ambiguous")
        return matches[0]

    require(state['version'] == 'TrueNAS-25.10.7', 'NAS version changed')
    require(record.get('sync') == 'STANDARD', 'STANDARD sync intent required')
    pool = one("pools", "name", record["dataset"].split("/")[0])
    require(str(pool["guid"]) == record["pool_guid"], "Pool GUID changed")
    require(pool['status'] == 'ONLINE', 'Pool is not healthy')
    dataset = one("datasets", "id", record["dataset"])
    require(dataset["guid"]["value"] == record["zvol_guid"], "ZVOL GUID changed")
    require(dataset["volsize"]["parsed"] == record["bytes"], "Unreconciled capacity change")
    require(dataset['sync']['value'] == 'STANDARD' and dataset['sync']['source'] == 'LOCAL', 'Durability policy changed')
    require(dataset['volblocksize']['value'] == '16K', 'Volume block size changed')
    require(sum(e['disk'] == 'zvol/' + record['dataset'] for e in state['extents']) == 1, 'Aliased extent')
    extent = one("extents", "id", record["extent_id"])
    require(extent["disk"] == "zvol/" + record["dataset"], "Extent redirected")
    require(extent["serial"] == record["serial"] and extent["naa"] == record["naa"], "Extent identity changed")
    require(extent["enabled"] and not extent["ro"] and not extent["insecure_tpc"], "Extent access changed")
    require(extent['blocksize'] == 512, 'Exported sector size changed')
    require(sum(m['extent'] == record['extent_id'] for m in state['mappings']) == 1, 'Aliased or missing extent mapping')
    mapping = one("mappings", "target", record["target_id"])
    require(mapping["extent"] == record["extent_id"] and mapping["lunid"] == record["lun"], "LUN redirected")
    target = one("targets", "id", record["target_id"])
    require(state["basename"] + ":" + target["name"] == record["iqn"], "Target IQN changed")
    require(target["groups"] == [record["group"]], "Target access changed")
    group = record["group"]
    require(group["authmethod"] == "CHAP" and group["auth"] is not None and group["initiator"] is not None, "CHAP and initiator restriction required")
    require(target["auth_networks"] == record["auth_networks"], "Storage network restriction changed")
    portal = one("portals", "id", group["portal"])
    require(len(portal["listen"]) == 1, "Portal listener count changed")
    listener = portal["listen"][0]
    require(listener["ip"] + ":" + str(listener["port"]) == record["portal"], "Portal changed")
    initiator = one("initiators", "id", group["initiator"])
    require(record["initiators"] and sorted(initiator["initiators"]) == sorted(record["initiators"]), "Initiator ACL changed")

    auth = one('auth', 'tag', group['auth'])
    require(auth['user'] == record['chap_user'], 'CHAP identity changed')
