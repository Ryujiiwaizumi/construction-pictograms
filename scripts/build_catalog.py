"""Rebuild transparent PNGs and the catalog from SVG masters and YAML metadata."""

import argparse
import html
import io
import math
from pathlib import Path
import re
import sys

from defusedxml import ElementTree
from PIL import Image
import resvg_py
import yaml

FIELDS = {"id", "name_ja", "file", "category", "note"}
SVG_NS = "{http://www.w3.org/2000/svg}"


class BuildError(ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject accidentally repeated YAML keys instead of silently overriding them."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise BuildError(f"Invalid or duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_metadata(root):
    entries, ids, files = [], set(), set()
    for path in sorted((root / "metadata").glob("*.yml")):
        if path.is_symlink():
            raise BuildError(f"Symlink metadata is not supported: {path.name}")
        try:
            entry = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except (yaml.YAMLError, BuildError) as exc:
            raise BuildError(f"{path.name}: {exc}") from exc
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise BuildError(f"{path.name}: required fields are {sorted(FIELDS)}")
        if any(not isinstance(v, str) or not v.strip() for v in entry.values()):
            raise BuildError(f"{path.name}: every field must be a non-empty string")
        if not re.fullmatch(r"[A-Z]+[0-9]{3,}", entry["id"]):
            raise BuildError(f"{path.name}: invalid ID {entry['id']!r}")
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\.svg", entry["file"]):
            raise BuildError(f"{path.name}: invalid SVG filename")
        # Numeric comparison also catches aliases such as W001 and W0001.
        identity = id_key(entry)
        if identity in ids:
            raise BuildError(f"Duplicate ID: {entry['id']}")
        if entry["file"] in files:
            raise BuildError(f"Duplicate filename: {entry['file']}")
        svg = root / "svg" / entry["file"]
        if not svg.is_file() or svg.is_symlink():
            raise BuildError(f"Missing SVG or unsupported symlink: {entry['file']}")
        ids.add(identity)
        files.add(entry["file"])
        entries.append(entry)
    if not entries:
        raise BuildError("metadata/*.yml contains no entries")
    unregistered = {p.name for p in (root / "svg").glob("*.svg")} - files
    if unregistered:
        raise BuildError(f"SVG without metadata: {', '.join(sorted(unregistered))}")
    return sorted(entries, key=id_key)


def id_key(entry):
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", entry["id"])
    return match[1], int(match[2])


def render_png(path):
    source = path.read_text(encoding="utf-8")
    tree = ElementTree.fromstring(source)
    if tree.tag != SVG_NS + "svg":
        raise BuildError(f"{path.name}: expected SVG root")
    try:
        box = [float(v) for v in re.split(r"[\s,]+", tree.attrib["viewBox"].strip())]
        if len(box) != 4 or not all(math.isfinite(v) for v in box) or min(box[2:]) <= 0:
            raise ValueError()
    except (KeyError, ValueError):
        raise BuildError(f"{path.name}: valid viewBox is required") from None
    allowed = {SVG_NS + tag for tag in ("svg", "g", "path", "title", "desc", "metadata")}
    for element in tree.iter():
        if element.tag not in allowed:
            raise BuildError(f"{path.name}: unsupported element {element.tag}; use vector paths")
        # Metadata is inert descriptive text, never a container for SVG/XML content.
        # Keep the attribute security checks below active for metadata as well.
        if element.tag == SVG_NS + "metadata" and len(element):
            raise BuildError(f"{path.name}: metadata must contain text only")
        for key, value in element.attrib.items():
            if key.split("}")[-1].lower().startswith("on") or key.split("}")[-1] in {"href", "src"}:
                raise BuildError(f"{path.name}: external resources and scripts are prohibited")
            if re.search(r"url\s*\(|@import", value, flags=re.I):
                raise BuildError(f"{path.name}: resource references are prohibited")
    if not tree.findall(".//" + SVG_NS + "path"):
        raise BuildError(f"{path.name}: vector path is required")
    png = resvg_py.svg_to_bytes(svg_string=source, skip_system_fonts=True)
    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        if rgba.getchannel("A").getextrema()[0] != 0:
            raise BuildError(f"{path.name}: transparent background is required")
        if not rgba.getbbox():
            raise BuildError(f"{path.name}: image has no visible content")
        if any(a and (r or g or b) for r, g, b, a in rgba.get_flattened_data()):
            raise BuildError(f"{path.name}: visible pixels must be black; use transparent cutouts")
    return png


def markdown(value):
    value = html.escape(value, quote=False)
    for char in "\\`*_[]|":
        value = value.replace(char, f"&#{ord(char)};")
    return "<br>".join(value.splitlines())


def catalog_text(entries):
    lines = ["# 建設系ピクトグラムカタログ", "",
             "<!-- 自動生成: metadata/*.yml を編集し、scripts/build_catalog.py を実行してください。 -->", "",
             "| ID | 日本語名 | ファイル名 | 分類 | 備考 |", "|---|---|---|---|---|"]
    for entry in entries:
        link = f"[`{entry['file']}`](../svg/{entry['file']})"
        cells = [markdown(entry["id"]), markdown(entry["name_ja"]), link,
                 markdown(entry["category"]), markdown(entry["note"])]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "## プレビュー", ""])
    for entry in entries:
        label = markdown(entry["id"] + " " + entry["name_ja"])
        lines.extend([f"### {label}", "", f"![{label}](../png/{Path(entry['file']).stem}.png)", ""])
    return "\n".join(lines)


def build(root, check=False):
    root = Path(root).resolve()
    for folder in ("metadata", "svg", "png", "catalog"):
        if (root / folder).is_symlink():
            raise BuildError(f"Symlink directory is not supported: {folder}")
    entries = load_metadata(root)
    # Validate and render every entry before touching any generated output.
    outputs = {root / "png" / (Path(e["file"]).stem + ".png"):
               render_png(root / "svg" / e["file"]) for e in entries}
    outputs[root / "catalog" / "catalog.md"] = catalog_text(entries).encode("utf-8")
    stale = set((root / "png").glob("*.png")) - outputs.keys()
    for path in set(outputs) | stale:
        if path.is_symlink():
            raise BuildError(f"Symlink output is not supported: {path.name}")
    changed = [p for p, data in outputs.items() if not p.exists() or p.read_bytes() != data]
    if check:
        if changed or stale:
            raise BuildError("Generated assets are outdated: " + ", ".join(
                str(p.relative_to(root)) for p in sorted(set(changed) | stale)))
    else:
        for path in changed:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(outputs[path])
        for path in stale:
            path.unlink()
    return len(entries), len(changed), len(stale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Verify generated outputs without writing")
    args = parser.parse_args()
    try:
        count, changed, removed = build(args.root, args.check)
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {count} pictograms; {changed} changed outputs; {removed} stale PNGs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
