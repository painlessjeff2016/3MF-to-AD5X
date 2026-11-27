"""Thin adapter: keep all actual conversion logic in the shared engine."""
from pathlib import Path
import json
import zipfile


def convert_project(source, destination, template, keep_unused=False):
    import bambu2ad5x as engine
    src, dst = Path(source), Path(destination)
    if src.resolve() == dst.resolve() or dst.exists():
        raise ValueError('Output must be a new file')
    report = dst.with_suffix(dst.suffix + '.report.txt')
    try:
        rep, _ = engine.convert(str(src), str(dst), str(template), False, not keep_unused)
        with zipfile.ZipFile(dst) as z:
            bad = z.testzip()
            if bad:
                raise ValueError(f'Invalid converted archive member: {bad}')
            if engine.SETTINGS not in z.namelist():
                raise ValueError('Converted project has no slicer settings')
        engine.write_report(str(report), str(src), str(dst), rep)
        return json.dumps({'summary': engine.summary(rep), 'warnings': rep.get('warn', []), 'notes': rep.get('notes', [])})
    except (Exception, SystemExit) as exc:
        dst.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        raise RuntimeError(str(exc)) from exc
