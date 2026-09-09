import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import yaml

spec = importlib.util.spec_from_file_location("build_catalog", Path(__file__).parents[1] / "build_catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30" viewBox="0 0 40 30"><path d="M5 5H25V20H5Z"/></svg>'


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "svg").mkdir()
        (self.root / "metadata").mkdir()

    def entry(self, filename="worker_a.svg", identity="W001", **changes):
        entry = dict(id=identity, name_ja="作業員", file=filename, category="作業員", note="工具を使用")
        entry.update(changes)
        (self.root / "svg" / filename).write_text(SVG, encoding="utf-8")
        path = self.root / "metadata" / (Path(filename).stem + ".yml")
        path.write_text(yaml.safe_dump(entry, allow_unicode=True), encoding="utf-8")
        return path

    def test_full_build_numeric_order_links_transparency_and_idempotence(self):
        self.entry("worker_a.svg", "W010")
        self.entry("worker_z.svg", "W002", name_ja="防水材塗布作業員（前面）")
        self.assertEqual(catalog.build(self.root), (2, 3, 0))
        text = (self.root / "catalog/catalog.md").read_text(encoding="utf-8")
        self.assertLess(text.index("W002"), text.index("W010"))
        self.assertIn("../svg/worker_z.svg", text)
        self.assertIn("../png/worker_z.png", text)
        with Image.open(self.root / "png/worker_z.png") as image:
            self.assertEqual(image.size, (40, 30))
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
            self.assertEqual(image.getpixel((10, 10)), (0, 0, 0, 255))
        self.assertEqual(catalog.build(self.root, check=True), (2, 0, 0))
        self.assertEqual(catalog.build(self.root), (2, 0, 0))

    def test_duplicate_id_and_numeric_alias(self):
        for identity in ("W001", "W0001"):
            with self.subTest(identity=identity):
                self.entry()
                self.entry("worker_b.svg", identity)
                with self.assertRaisesRegex(catalog.BuildError, "Duplicate ID"):
                    catalog.build(self.root)
                self.assertFalse((self.root / "png").exists())

    def test_duplicate_filename(self):
        source = self.entry()
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
        data["id"] = "W002"
        (source.parent / "duplicate.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
        with self.assertRaisesRegex(catalog.BuildError, "Duplicate filename"):
            catalog.build(self.root)

    def test_missing_svg_preserves_existing_outputs(self):
        self.entry()
        catalog.build(self.root)
        before = (self.root / "catalog/catalog.md").read_bytes()
        (self.root / "svg/worker_a.svg").unlink()
        with self.assertRaisesRegex(catalog.BuildError, "Missing SVG"):
            catalog.build(self.root)
        self.assertEqual(before, (self.root / "catalog/catalog.md").read_bytes())

    def test_missing_metadata(self):
        self.entry()
        (self.root / "svg/worker_orphan.svg").write_text(SVG)
        with self.assertRaisesRegex(catalog.BuildError, "SVG without metadata"):
            catalog.build(self.root)

    def test_yaml_errors(self):
        for value in ("id: W001\nid: W002\n", "[]", "id: [", "id: 1"):
            with self.subTest(value=value):
                (self.root / "metadata/bad.yml").write_text(value)
                with self.assertRaises(catalog.BuildError):
                    catalog.build(self.root)

    def test_invalid_filename(self):
        self.entry(file="../outside.svg")
        with self.assertRaisesRegex(catalog.BuildError, "invalid SVG filename"):
            catalog.build(self.root)

    def test_table_escapes_multiline_and_markdown(self):
        self.entry(note="A | B\n[link](x) <tag>")
        catalog.build(self.root)
        text = (self.root / "catalog/catalog.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| W001"))
        self.assertEqual(row.count("|"), 6)
        self.assertIn("&#124;", row)
        self.assertIn("<br>", row)
        self.assertIn("&lt;tag&gt;", row)

    def test_check_detects_modified_png_and_catalog_without_writing(self):
        self.entry()
        catalog.build(self.root)
        for relative in ("png/worker_a.png", "catalog/catalog.md"):
            with self.subTest(relative=relative):
                path = self.root / relative
                path.write_bytes(b"manually changed")
                with self.assertRaisesRegex(catalog.BuildError, "outdated"):
                    catalog.build(self.root, check=True)
                self.assertEqual(path.read_bytes(), b"manually changed")
                catalog.build(self.root)

    def test_deleted_entry_removes_stale_generated_png(self):
        self.entry()
        self.entry("worker_b.svg", "W002")
        catalog.build(self.root)
        (self.root / "metadata/worker_b.yml").unlink()
        (self.root / "svg/worker_b.svg").unlink()
        self.assertEqual(catalog.build(self.root), (1, 1, 1))
        self.assertFalse((self.root / "png/worker_b.png").exists())

    def test_text_metadata_preserves_rendering_and_catalog_source(self):
        self.entry()
        path = self.root / "svg/worker_a.svg"
        expected = catalog.render_png(path)
        path.write_text(SVG.replace('<path ', '<metadata>id: W999\nname_ja: 説明 &amp; 注記</metadata><path '), encoding="utf-8")
        self.assertEqual(catalog.render_png(path), expected)
        catalog.build(self.root)
        text = (self.root / "catalog/catalog.md").read_text(encoding="utf-8")
        self.assertIn("W001", text)
        self.assertNotIn("W999", text)
        self.assertEqual(catalog.build(self.root, check=True), (1, 0, 0))

    def test_metadata_rejects_children_and_unsafe_attributes(self):
        self.entry()
        for metadata in (
            '<metadata><path d="M5 5H25V20H5Z"/></metadata>',
            '<metadata><script>alert(1)</script></metadata>',
            '<metadata><image href="https://example.invalid/a"/></metadata>',
            '<metadata><foreign xmlns="urn:example">text</foreign></metadata>',
            '<metadata onload="alert(1)">text</metadata>',
            '<metadata href="https://example.invalid/a">text</metadata>',
            '<metadata xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="https://example.invalid/a">text</metadata>',
            '<metadata src="https://example.invalid/a">text</metadata>',
            '<metadata style="fill:url(https://example.invalid/a)">text</metadata>',
            '<metadata style="@import example">text</metadata>',
        ):
            with self.subTest(metadata=metadata):
                (self.root / "svg/worker_a.svg").write_text(SVG.replace('<path ', metadata + '<path '))
                with self.assertRaises(catalog.BuildError):
                    catalog.build(self.root)
                self.assertFalse((self.root / "png").exists())

    def test_metadata_rejects_entity_expansion(self):
        self.entry()
        from defusedxml.common import DefusedXmlException
        source = '<!DOCTYPE svg [<!ENTITY data "unsafe">]>' + SVG.replace('<path ', '<metadata>&data;</metadata><path ')
        (self.root / "svg/worker_a.svg").write_text(source)
        with self.assertRaises(DefusedXmlException):
            catalog.build(self.root)
        self.assertFalse((self.root / "png").exists())

    def test_invalid_svgs_do_not_publish_partial_outputs(self):
        self.entry()
        for replacement in (
            SVG.replace('viewBox="0 0 40 30"', ''),
            SVG.replace('<path ', '<image href="data:image/png;base64,AA=="/><path '),
            SVG.replace('<path ', '<path fill="white" '),
            SVG.replace('M5 5H25V20H5Z', 'M0 0H40V30H0Z'),
            SVG.replace('M5 5H25V20H5Z', ''),
            SVG.replace('<path ', '<path style="fill:url(https://example.invalid/a)" '),
        ):
            with self.subTest(svg=replacement):
                (self.root / "svg/worker_a.svg").write_text(replacement)
                with self.assertRaises((catalog.BuildError, ValueError)):
                    catalog.build(self.root)
                self.assertFalse((self.root / "png").exists())


if __name__ == "__main__":
    unittest.main()
