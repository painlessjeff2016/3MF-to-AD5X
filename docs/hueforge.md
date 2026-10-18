# HueForge / layer-based filament switching

## The regression

Some HueForge and OrcaSlicer 3MFs define multiple filament slots but keep
their mesh assigned to filament 1. They switch to the other filaments with
entries such as:

```xml
<layer top_z="1.12" type="2" extruder="2" color="#4F4F4F" gcode="tool_change"/>
```

inside `Metadata/custom_gcode_per_layer.xml`. Older versions of the
converter only looked for `<code>` entries there. They therefore concluded
the other slots were unused, pruned their colors and filament presets, and
left the `tool_change` instructions pointing at missing slots.

The fix recognizes these per-layer color changes and **disables unused-slot
pruning for the entire source project**. It preserves the source order and
filament count, rather than trying to guess which slots are safe to remove.

Other projects that don't use layer color changes keep the existing pruning
behavior. Malformed custom G-code XML is treated conservatively: retain all
filament slots rather than silently lose a needed color.

## Tests

No extra Python packages needed:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

To exercise the full converter with an actual source HueForge 3MF:

```sh
HUEFORGE_SAMPLE="/path/to/original-hueforge.3mf" \
  python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The real-file test writes to a temporary destination, never modifies the
original, and asserts exact filament colors, retained layer change XML,
layer height, initial layer height and infill density. It is skipped in CI
unless a sample is supplied.

For an additional manual check, produce a separate converted project:

```sh
python3 bambu2ad5x.py original-hueforge.3mf \
  --output original-hueforge_AD5X.3mf --report
```

**Open using File → Open Project in OrcaSlicer**, verify the color sequence
and print-process settings, and inspect the sliced layer preview before
printing. A successful test doesn't guarantee OrcaSlicer will honor
a layer-change instruction for every source project.

## Bundled ZMOD AD5X printer profile

The converter's complete `ad5x_template.json` is the project-level baseline.
The matching OrcaSlicer printer preset is preserved in
`profiles/Flashforge AD5X.json`, supplied by the printer owner. It includes:

- `LED_ON` followed by `START_PRINT ...` at print start
- `END_PRINT` followed by `LED_OFF` at print end
- `SET_PRINT_STATS_INFO CURRENT_LAYER=...` before each layer
- 220 x 220 mm printable area, Klipper flavor, 0.4 mm nozzle and
  `printer_settings_id = Flashforge AD5X`

A printer preset alone is **not** a full 3MF project template: it lacks
process settings, author filament settings, and other metadata that the
converter needs. Its machine settings were therefore merged into the
complete default project template. The original preset is kept as a separate
file for auditing and future profile updates.

The preset's `name`, `from` and `inherits` fields are not copied into
project-level metadata. Its `default_print_profile` points to an
**AD5M Pro** process preset; the generated project's default remains
`0.20mm Standard @FF AD5X` instead. The project-specific layer height,
first-layer height, infill, colors and color switches still come from
the author 3MF, not from printer defaults.

This template assumes your ZMOD/Klipper firmware provides `LED_ON`,
`LED_OFF`, `START_PRINT`, `END_PRINT`, and `SET_PRINT_STATS_INFO`.
To use other firmware or another printer, provide your own complete
project template via `--template` rather than reusing these macros.

## AD5X hardware limits

The AD5X IFS holds four active spools. **Preserving five or more filament
definitions in a 3MF does not give the printer extra spool slots.** Plan a
manual change or adjust the project before printing. The converter's
existing warning about more than four filament slots still applies.

If needed, the existing `--keep-unused-filaments` flag can also disable
unused-slot pruning for other projects.
