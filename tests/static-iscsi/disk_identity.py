"""Select the lab data disk by fixed serial, never an unstable Linux device name."""
def data_disk(disks, boot_disks):
    matches = [disk for disk in disks if disk.get("serial") == "ISCSILABDATA"]
    if len(matches) != 1:
        raise ValueError("Lab data serial is missing or ambiguous")
    disk = matches[0]
    if disk["name"] in boot_disks or disk["size"] != 16*1024**3 or disk.get("pool") is not None:
        raise ValueError("Lab data disk is a boot disk, wrong size or already in a pool")
    return disk["name"]
