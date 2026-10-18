"""Regression tests for HueForge / Orca layer-based filament switching.

Run from the repository root:
    python3 -m unittest discover -s tests -v

Optional integration test with an actual HueForge source file:
    HUEFORGE_SAMPLE=/path/to/original.3mf python3 -m unittest discover -s tests -v
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bambu2ad5x as converter

COLORS = ["#000000", "#4F4F4F", "#FF0000", "#E17100", "#FFFF00"]
OBJECT_CONFIG = b'''<?xml version="1.0"?>
<config><object id="1"><metadata key="extruder" value="1"/></object></config>'''
LAYER_CHANGES = b'''<?xml version="1.0" encoding="utf-8"?>
<custom_gcodes_per_layer><plate><plate_info id="1"/>
<layer top_z="1.12" type="2" extruder="2" color="#4F4F4F" gcode="tool_change"/>
<layer top_z="1.60" type="2" extruder="3" color="#FF0000" gcode="tool_change"/>
<layer top_z="2.00" type="2" extruder="4" color="#E17100" gcode="tool_change"/>
<layer top_z="2.56" type="2" extruder="5" color="#FFFF00" gcode="tool_change"/>
<mode value="MultiAsSingle"/>
</plate></custom_gcodes_per_layer>'''


class TestHueForgeFilamentDetection(unittest.TestCase):
    def analyse(self, layer_xml=None):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.3mf"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("Metadata/model_settings.config", OBJECT_CONFIG)
                if layer_xml is not None:
                    archive.writestr("Metadata/custom_gcode_per_layer.xml", layer_xml)
            with zipfile.ZipFile(source) as archive:
                return converter.analyze_filaments(
                    archive, {"filament_colour": COLORS}, len(COLORS)
                )

    def test_hueforge_tool_changes_protect_all_slots(self):
        result = self.analyse(LAYER_CHANGES)
        self.assertIsNone(result["used"])
        self.assertEqual(result["why"], "colour-change layers")

    def test_unused_slots_still_pruned_on_regular_single_colour(self):
        result = self.analyse()
        self.assertEqual(result["used"], {1})

    def test_legacy_code_keeps_conservative_behavior(self):
        result = self.analyse(
            b"<custom_gcodes_per_layer><plate><code/></plate></custom_gcodes_per_layer>"
        )
        self.assertIsNone(result["used"])

    def test_color_change_alias_protects_slots(self):
        result = self.analyse(
            b'<custom_gcodes_per_layer><layer gcode="color_change" extruder="3" /></custom_gcodes_per_layer>'
        )
        self.assertIsNone(result["used"])

    def test_namespaced_layer_protects_slots(self):
        result = self.analyse(
            b'<r xmlns="urn:orca"><layer gcode="tool_change" extruder="4" /></r>'
        )
        self.assertIsNone(result["used"])

    def test_benign_layer_does_not_disable_pruning(self):
        result = self.analyse(
            b'<custom_gcodes_per_layer><layer gcode="pause" type="0" /></custom_gcodes_per_layer>'
        )
        self.assertEqual(result["used"], {1})

    def test_malformed_custom_change_xml_preserves_slots(self):
        result = self.analyse(b'<custom_gcodes_per_layer><layer gcode="tool_change"')
        self.assertIsNone(result["used"])


class TestActualHueForgeProject(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("HUEFORGE_SAMPLE"), "Set HUEFORGE_SAMPLE for real-file test")
    def test_full_conversion_preserves_colors_layer_changes_and_process(self):
        original = Path(os.environ["HUEFORGE_SAMPLE"]).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "converted.3mf"
            # Default pruning deliberately enabled: this tests the bug fix.
            converter.convert(str(original), str(output), converter.find_default_template())

            settings_name = "Metadata/project_settings.config"
            layer_name = "Metadata/custom_gcode_per_layer.xml"
            with zipfile.ZipFile(original) as before_zip, zipfile.ZipFile(output) as after_zip:
                before = json.loads(before_zip.read(settings_name))
                after = json.loads(after_zip.read(settings_name))
                self.assertEqual(before["filament_colour"], after["filament_colour"])
                self.assertEqual(len(before["filament_colour"]), len(after["filament_settings_id"]))
                self.assertEqual(before_zip.read(layer_name), after_zip.read(layer_name))
                for setting in ("layer_height", "initial_layer_print_height", "sparse_infill_density"):
                    self.assertEqual(before[setting], after.get(setting), setting)


if __name__ == "__main__":
    unittest.main()
