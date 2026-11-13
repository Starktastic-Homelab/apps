"""Homepage catalog loader and generator helpers."""
from pathlib import Path
from typing import Any

import yaml


class CatalogError(Exception):
    pass


class UniqueLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys (as js-yaml does) and unquoted yes/no/on/off."""

    def compose_node(self, parent, index):
        node = super().compose_node(parent, index)
        if (isinstance(node, yaml.ScalarNode) and node.style is None
                and node.tag == "tag:yaml.org,2002:bool"
                and node.value.lower() in ("yes", "no", "on", "off")):
            raise yaml.composer.ComposerError(
                None, None,
                f"unquoted {node.value!r} is a boolean in YAML 1.1; quote it or use true/false",
                node.start_mark,
            )
        return node

    def compose_mapping_node(self, anchor):
        node = super().compose_mapping_node(anchor)
        seen = set()
        # Checked before `<<` merges are expanded, so a key may still override a merged one.
        for key, _ in node.value:
            if key.tag == "tag:yaml.org,2002:merge":
                continue
            if key.value in seen:
                raise yaml.composer.ComposerError(
                    "while composing a mapping", node.start_mark,
                    f"found duplicate key {key.value!r}", key.start_mark,
                )
            seen.add(key.value)
        return node


def loads_yaml(text: str, where: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as err:
        raise CatalogError(f"{where}: {err}") from err


def load_yaml(path: Path) -> Any:
    data = loads_yaml(Path(path).read_text(encoding="utf-8"), str(path))
    return {} if data is None else data
