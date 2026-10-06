"""Check the active stock chart using the real infrastructure value layers."""

from pathlib import Path
import sys

import yaml


root = Path(__file__).resolve().parents[1]
staged = root / "infrastructure/system/proxmox-csi"
assert not (staged / "app.yaml.disabled").exists()
app = yaml.safe_load((staged / "app.yaml").read_text())
assert app["deployPhase"] == "controllers"
bootstrap = root / "infrastructure/system/sealed-secrets"
prerequisite = yaml.safe_load((bootstrap / "app.yaml").read_text())
assert prerequisite["deployPhase"] == "foundation" and prerequisite["manifests"] is True
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
assert not any(obj["kind"] == "Namespace" for obj in objects), "Namespace belongs to the foundation prerequisite"
namespace = yaml.safe_load((bootstrap / "manifests/namespace.yaml").read_text())
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
trust = next(volume["configMap"] for volume in controller["volumes"] if volume["name"] == "proxmox-api-trust")
assert trust == {"name": "proxmox-api-trust"}
plugin = next(container for container in controller["containers"] if container["image"] == "ghcr.io/sergelogvinov/proxmox-csi-controller:v0.20.0")
assert {"name": "proxmox-api-trust", "mountPath": "/etc/ssl/certs/proxmox.pem", "subPath": "proxmox.pem", "readOnly": True} in plugin["volumeMounts"]
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
print("Proxmox CSI render: prerequisite ordering, secret reference, native attachment/resize and Retain checks passed")
