"""Check the staged stock chart using the real infrastructure value layers."""

from pathlib import Path
import sys

import yaml


root = Path(__file__).resolve().parents[3]
staged = root / "infrastructure/system/proxmox-csi"
assert not (staged / "app.yaml").exists(), "CSI activation requires separate qualification"
app = yaml.safe_load((staged / "app.yaml.disabled").read_text())
assert app["deployPhase"] == "foundation"
assert app["chart"] == {
    "repo": "ghcr.io/sergelogvinov/charts",
    "name": "proxmox-csi-plugin",
    "version": "0.5.10",
}
objects = [obj for obj in yaml.safe_load_all(Path(sys.argv[1]).read_text()) if obj]


def one(kind):
    matches = [obj for obj in objects if obj["kind"] == kind]
    assert len(matches) == 1, (kind, len(matches))
    return matches[0]


assert not any(obj["kind"] in ("Secret", "PersistentVolume", "PersistentVolumeClaim") for obj in objects)
namespace = one("Namespace")
assert namespace["metadata"]["name"] == app["namespace"] == "csi-proxmox"
assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "privileged"
driver = one("CSIDriver")
assert driver["metadata"]["name"] == "csi.proxmox.sinextra.dev"
assert driver["spec"]["attachRequired"] is True
storage = one("StorageClass")
assert storage["metadata"]["name"] == "proxmox-retained"
assert storage["provisioner"] == driver["metadata"]["name"]
assert storage["allowVolumeExpansion"] is True
assert storage["reclaimPolicy"] == "Retain"
assert storage["volumeBindingMode"] == "WaitForFirstConsumer"
assert storage["parameters"] == {"storage": "k3s-block", "csi.storage.k8s.io/fstype": "ext4", "cache": "none"}
for key in ("storageclass.kubernetes.io/is-default-class", "storageclass.beta.kubernetes.io/is-default-class"):
    assert str(storage["metadata"].get("annotations", {}).get(key, "false")).lower() == "false"
controller = one("Deployment")["spec"]["template"]["spec"]
secret = next(volume["secret"] for volume in controller["volumes"] if volume["name"] == "cloud-config")
assert secret == {"secretName": "proxmox-csi-config", "items": [{"key": "config.yaml", "path": "config.yaml"}]}
assert controller["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"] == [
    {"matchExpressions": [{"key": "node-role.kubernetes.io/control-plane", "operator": "Exists"}]}
]
images = [container["image"] for container in controller["containers"]]
assert "ghcr.io/sergelogvinov/proxmox-csi-controller:v0.20.0" in images
for component in ("csi-attacher", "csi-provisioner", "csi-resizer"):
    assert any(image.startswith(f"registry.k8s.io/sig-storage/{component}:") for image in images)
node = one("DaemonSet")["spec"]["template"]["spec"]
assert node["nodeSelector"] == {"kubernetes.io/os": "linux", "node-role.kubernetes.io/worker": "true"}
assert any(container["image"] == "ghcr.io/sergelogvinov/proxmox-csi-node:v0.20.0" for container in node["containers"])
assert any(volume.get("hostPath", {}).get("path") == "/var/lib/kubelet" for volume in node["volumes"])
assert yaml.safe_load((root / "templates/globals.yaml").read_text())["global"]["storageClass"] == "nfs-pv"
print("Staged Proxmox CSI render: activation boundary, secret reference, native attachment/resize and Retain checks passed")
