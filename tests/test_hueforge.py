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
    """The complete template must use the correct KilnOS printer settings."""

    def test_bundled_template_matches_user_printer_profile(self):
        root = Path(__file__).resolve().parents[1]
        template = json.loads((root / "ad5x_template.json").read_text(encoding="utf-8"))
        profile = json.loads((root / "profiles" / "AD5X KilnOS Adaptive Purge - 0.4mm.json").read_text(encoding="utf-8"))

        # The source is an Orca printer PRESET, not a whole .3mf project.
        # Preserve the project envelope and the AD5X process selection.
        excluded = {"name", "from", "inherits", "version"}
        for key, value in profile.items():
            if key not in excluded:
                self.assertEqual(template[key], value, key)

        self.assertEqual(template["printer_settings_id"], "AD5X KilnOS Adaptive Purge - 0.4mm")
        self.assertEqual(template["default_print_profile"], "0.20mm Standard @FF AD5X - default")
        self.assertNotIn("AD5M", json.dumps(profile))
        self.assertNotIn("AD5M", json.dumps(template))
        self.assertEqual(template["name"], "project_settings")
        self.assertEqual(template["from"], "project")
        self.assertNotIn("inherits", template)
        self.assertGreater(len(template), len(profile))

        self.assertIn("PRINT_START BED=", template["machine_start_gcode"])
        self.assertEqual(template["machine_end_gcode"], "PRINT_END\nLED_OFF")
        self.assertIn("SET_PRINT_STATS_INFO CURRENT_LAYER=", template["layer_change_gcode"])

class TestSyntheticHueForgeConversion(unittest.TestCase):
    """Run the real converter on a tiny generated five-color 3MF."""

    def test_full_conversion_keeps_slots_swaps_and_slicing_settings(self):
        template = Path(converter.find_default_template())
        source_settings = json.loads(template.read_text(encoding="utf-8"))
        source_settings.update({
            "printer_model": "Bambu Lab X1 Carbon",
            "plugins": ["untrusted;;Untrusted"],
            "slicing_pipeline_plugin": ["Untrusted"],
            "post_process": ["/untrusted/script"],
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
                self.assertEqual(settings["printer_settings_id"], "AD5X KilnOS Adaptive Purge - 0.4mm")
                self.assertIn("PRINT_START BED=", settings["machine_start_gcode"])
                self.assertEqual(settings["machine_end_gcode"], "PRINT_END\nLED_OFF")
                self.assertEqual(settings["printer_agent"], "moonraker")
                self.assertEqual(settings["purge_in_prime_tower"], "0")
                self.assertEqual(settings["use_3mf"], "0")
                self.assertEqual(settings["fan_speedup_time"], "1.5")
                self.assertEqual(settings["fan_speedup_overhangs"], "0")
                self.assertEqual(settings["fan_kickstart"], "0.5")
                self.assertEqual(settings["part_cooling_fan_min_pwm"], "10")
                machine_overrides = set(settings["different_settings_to_system"][-1].split(";"))
                expected_machine_keys = set(["adaptive_bed_mesh_margin","auxiliary_fan","bbl_use_printhost","bed_custom_model","bed_custom_texture","bed_exclude_area","bed_exclude_volume_mode","bed_exclude_volumes","bed_mesh_max","bed_mesh_min","bed_mesh_probe_distance","bed_temperature_formula","before_layer_change_gcode","belt_frame_tilt_angle","belt_frame_tilt_decouple","belt_printer","belt_printer_infinite_y","belt_slice_rotation","belt_slice_rotation_angle","belt_support_floor_offset","best_object_pos","build_plate_tilt_x","build_plate_tilt_y","change_extrusion_role_gcode","change_filament_gcode","cooling_filter_enabled","cooling_tube_length","cooling_tube_retraction","default_bed_type","default_filament_profile","default_nozzle_volume_type","default_print_profile","deretract_speed_extruder_change","deretraction_speed","disable_m73","emit_machine_limits_to_gcode","enable_belt_purge_tower","enable_filament_ramming","enable_long_retraction_when_cut","enable_power_loss_recovery","enable_pre_heating","extra_loading_move","extruder_bed_exclude_volumes","extruder_clearance_dist_to_rod","extruder_clearance_height_to_lid","extruder_clearance_height_to_rod","extruder_clearance_radius","extruder_colour","extruder_max_nozzle_count","extruder_nozzle_stats","extruder_offset","extruder_printable_area","extruder_printable_height","extruder_type","extruder_variant_list","fan_direction","fan_kickstart","fan_speedup_overhangs","fan_speedup_time","farthest_point_timelapse","file_start_gcode","flashforge_serial_number","gcode_flavor","gcode_remap_x","gcode_remap_y","gcode_remap_z","gcode_skip_config_block","grab_length","group_algo_with_time","head_wrap_detect_zone","high_current_on_filament_swap","host_type","hotend_cooling_rate","hotend_heating_rate","imex_carriage_margin","imex_firmware_managed_zones","imex_gantry_count","imex_mode_active_tools","imex_mode_gcodes","imex_mode_names","imex_nozzle_clearance_x","imex_nozzle_clearance_y","imex_tool_layout","imex_tools_per_gantry","imex_viz_theme","input_shaping_damp_x","input_shaping_damp_y","input_shaping_emit","input_shaping_freq_x","input_shaping_freq_y","input_shaping_type","is_imex","layer_change_gcode","long_retractions_when_cut","machine_bed_mass_Y","machine_end_gcode","machine_hotend_change_time","machine_load_filament_time","machine_max_acceleration_e","machine_max_acceleration_extruding","machine_max_acceleration_retracting","machine_max_acceleration_travel","machine_max_acceleration_x","machine_max_acceleration_y","machine_max_acceleration_z","machine_max_force_Y","machine_max_jerk_e","machine_max_jerk_x","machine_max_jerk_y","machine_max_jerk_z","machine_max_junction_deviation","machine_max_printed_mass","machine_max_speed_e","machine_max_speed_x","machine_max_speed_y","machine_max_speed_z","machine_min_extruding_rate","machine_min_travel_rate","machine_pause_gcode","machine_prepare_compensation_time","machine_start_gcode","machine_tool_change_time","machine_unload_filament_time","manual_filament_change","master_extruder_id","max_layer_height","max_resonance_avoidance_speed","min_layer_height","min_resonance_avoidance_speed","nozzle_diameter","nozzle_flush_dataset","nozzle_height","nozzle_hrc","nozzle_type","nozzle_volume","parallel_printheads_bed_exclude_areas","parallel_printheads_count","parking_pos_retraction","part_cooling_fan_min_pwm","pellet_modded_printer","physical_extruder_map","preferred_orientation","printable_area","printable_height","printer_agent","printer_extruder_id","printer_extruder_variant","printer_model","printer_notes","printer_plugin_config_overrides","printer_structure","printer_technology","printer_variant","printhost_authorization_type","printhost_ssl_ignore_revoke","printing_by_object_gcode","purge_in_prime_tower","resonance_avoidance","retract_after_wipe","retract_before_wipe","retract_length_toolchange","retract_lift_above","retract_lift_below","retract_lift_enforce","retract_restart_extra","retract_restart_extra_toolchange","retract_when_changing_layer","retraction_distances_when_cut","retraction_length","retraction_minimum_travel","retraction_speed","scan_first_layer","single_extruder_multi_material","support_air_filtration","support_chamber_temp_control","support_cooling_filter","support_fast_purge_mode","support_multi_bed_types","support_object_skip_flush","support_parallel_printheads","template_custom_gcode","thumbnails","thumbnails_format","time_cost","time_lapse_gcode","tool_change_on_wipe_tower","travel_slope","upward_compatible_machine","use_3mf","use_firmware_retraction","use_relative_e_distances","wait_for_temp_on_wipe_tower","wipe","wipe_distance","wipe_tower_type","wrapping_detection_gcode","wrapping_detection_layers","wrapping_exclude_area","z_hop","z_hop_types","z_offset"])
                self.assertEqual(machine_overrides, expected_machine_keys & settings.keys())
                self.assertNotIn("inherits", machine_overrides)
                self.assertNotIn("printer_settings_id", machine_overrides)
                self.assertIn("machine_start_gcode", machine_overrides)
                self.assertIn("change_filament_gcode", machine_overrides)
                self.assertIn("retraction_length", machine_overrides)
                self.assertEqual(settings["inherits_group"], ["0.20mm Standard @FF AD5X"] + [""] * len(settings["filament_settings_id"]) + ["Flashforge AD5X 0.4 nozzle"])
                self.assertIn("_GOTO_TRASH", settings["change_filament_gcode"])
                self.assertEqual(settings["plugins"], ["kiln_ifs_map;;Kiln IFS Tool Map"])
                self.assertEqual(settings["slicing_pipeline_plugin"], ["Kiln IFS Tool Map"])
                self.assertEqual(settings["post_process"], ["/home/jeff/.local/bin/zmod_preprocess-linux-amd64"])
                process_keys = settings["different_settings_to_system"][0].split(";")
                for key in ("plugins", "slicing_pipeline_plugin", "post_process"):
                    self.assertIn(key, process_keys)
                start = settings["machine_start_gcode"]
                self.assertLess(start.index("VALUE=1"), start.index("PRINT_START BED="))
                self.assertLess(start.index("PRINT_START BED="), start.index("VALUE=2"))
                self.assertEqual(settings["default_print_profile"], "0.20mm Standard @FF AD5X - default")
                self.assertEqual(settings["print_settings_id"], settings["default_print_profile"])


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
