"""Copy the shared engine and complete project template from the repository root."""
from pathlib import Path
import json
import shutil

android = Path(__file__).resolve().parent
root = android.parent
python_dir = android / 'app/src/main/python'
assets = android / 'app/src/main/assets'
engine = root / 'bambu2ad5x.py'
template = root / 'ad5x_template.json'
license_file = root / 'LICENSE'
for path in (engine, template, license_file):
    if not path.is_file():
        raise SystemExit(f'Missing {path}. Place android/ inside the existing converter repository.')
settings = json.loads(template.read_text(encoding='utf-8'))
if not all(k in settings for k in ('print_settings_id', 'filament_settings_id', 'machine_start_gcode', 'change_filament_gcode')):
    raise SystemExit('Expected the full conversion template, not a machine-only preset.')
python_dir.mkdir(parents=True, exist_ok=True)
assets.mkdir(parents=True, exist_ok=True)
shutil.copyfile(engine, python_dir / engine.name)
shutil.copyfile(template, assets / template.name)
shutil.copyfile(license_file, assets / 'ENGINE-LICENSE.txt')
print(f'Engine ready. Target: {settings.get("printer_settings_id")}')
