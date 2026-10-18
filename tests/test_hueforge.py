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


class TestBundledAD5XPrinterProfile(unittest.TestCase):
    """The complete template must use the correct ZMOD printer settings."""

    def test_bundled_template_matches_user_printer_profile(self):
        root = Path(__file__).resolve().parents[1]
        template = json.loads((root / "ad5x_template.json").read_text(encoding="utf-8"))
        profile = json.loads((root / "profiles" / "Flashforge AD5X.json").read_text(encoding="utf-8"))

        # The source is an Orca printer PRESET, not a whole .3mf project.
        # Preserve the project envelope and the AD5X process selection.
        excluded = {"name", "from", "inherits", "default_print_profile"}
        for key, value in profile.items():
            if key not in excluded:
                self.assertEqual(template[key], value, key)

        self.assertEqual(template["printer_settings_id"], "Flashforge AD5X")
        self.assertEqual(template["default_print_profile"], "0.20mm Standard @FF AD5X")
        self.assertEqual(template["name"], "project_settings")
        self.assertEqual(template["from"], "project")
        self.assertNotIn("inherits", template)
        self.assertGreater(len(template), len(profile))

        self.assertTrue(template["machine_start_gcode"].startswith("LED_ON\\nSTART_PRINT"))
        self.assertEqual(template["machine_end_gcode"], "END_PRINT\\nLED_OFF")
        self.assertIn("SET_PRINT_STATS_INFO CURRENT_LAYER=", template["before_layer_change_gcode"])

class TestSyntheticHueForgeConversion(unittest.TestCase):
    """Run the real converter on a tiny generated five-color 3MF."""

    def test_full_conversion_keeps_slots_swaps_and_slicing_settings(self):
        template = Path(converter.find_default_template())
        source_settings = json.loads(template.read_text(encoding="utf-8"))
        source_settings.update({
            "printer_model": "Bambu Lab X1 Carbon",
            "filament_colour": COLORS,
            "filament_type": ["PLA"] * 5,
            "filament_settings_id": ["Generic PLA"] * 5,
            "layer_height": "0.08",
            "initial_layer_print_height": "0.16",
            "sparse_infill_density": "100%",
            "print_settings_id": "0.08mm High Quality @BBL X1C",
        })
        # A tiny valid triangle model, with no face painting: switching
        # colors by layer is the only reason to keep slots 2..5.
        model = b'''<?xml version="1.0"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources><object id="1" type="model">
    <mesh>
      <vertices>
        <vertex x="0" y="0" z="0"/>
        <vertex x="10" y="0" z="0"/>
        <vertex x="0" y="10" z="0"/>
      </vertices>
      <triangles><triangle v1="0" v2="1" v3="2"/></triangles>
    </mesh>
  </object></resources>
  <build><item objectid="1"/></build>
</model>'''
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "hueforge.3mf"
            converted = Path(tmp) / "hueforge_AD5X.3mf"
            with zipfile.ZipFile(original, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("Metadata/project_settings.config", json.dumps(source_settings))
                archive.writestr("Metadata/model_settings.config", OBJECT_CONFIG)
                archive.writestr("Metadata/custom_gcode_per_layer.xml", LAYER_CHANGES)
                archive.writestr("3D/3dmodel.model", model)

            converter.convert(str(original), str(converted), str(template))
            with zipfile.ZipFile(converted) as archive:
                settings = json.loads(archive.read("Metadata/project_settings.config"))
                self.assertEqual(settings["filament_colour"], COLORS)
                self.assertEqual(len(settings["filament_settings_id"]), len(COLORS))
                self.assertEqual(settings["layer_height"], "0.08")
                self.assertEqual(settings["initial_layer_print_height"], "0.16")
                self.assertEqual(settings["sparse_infill_density"], "100%")
                self.assertEqual(archive.read("Metadata/custom_gcode_per_layer.xml"), LAYER_CHANGES)
                self.assertEqual(settings["printer_settings_id"], "Flashforge AD5X")
                self.assertTrue(settings["machine_start_gcode"].startswith("LED_ON\\nSTART_PRINT"))
                self.assertEqual(settings["machine_end_gcode"], "END_PRINT\\nLED_OFF")
                self.assertEqual(settings["default_print_profile"], "0.20mm Standard @FF AD5X")


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
