# 3MF-to-AD5X Android — alpha

Native Android interface for the shared Python converter. The packaging script copies the current engine, MIT license and full converter template into the Android build inputs. A machine-only Orca printer JSON is not a valid replacement for the full template.

## Build on GitHub Actions

Open the repository Actions tab and select Android APK. Relevant pushes trigger a build; manual dispatch is available once the workflow exists on the default branch. The workflow runs the converter regression tests before building the debug APK. Download the 3MF-to-AD5X-Android-ARM64 artifact from a successful run, extract the ZIP and install the APK on an ARM64 device. Each runner uses a temporary debug signing key: future builds may require uninstalling the previous version. Persistent release signing is not configured.

## Build locally on Linux

Requires JDK 17, Android SDK 35, Gradle 8.9 and host Python 3.11.

```sh
cd android
python3 prepare_engine.py
gradle wrapper --gradle-version 8.9
./gradlew assembleDebug
```

The debug APK is at app/build/outputs/apk/debug/app-debug.apk.

## First test

1. Open a small Bambu/Orca print-profile 3MF, convert, save and open as a project in the Android slicer.
2. Compare against a desktop conversion with the same engine and template. Check metadata, filament order, painted regions, project overrides, plugins, HueForge, and process selection. Review generated G-code before printing.
3. Try the Android Share action. Receiving slicer support for 3MF content URIs needs device verification. If sharing fails, save and open from inside the slicer.

## Limitations

Alpha source: Android build and device behavior require validation. The installed app has no Internet permission; conversion is local. Source files are never overwritten. Reports can be exported separately. No batch conversion, custom template selection, persistent jobs, or automatic cache cleanup yet. The existing converter's capabilities are inherited, not independently reimplemented or guaranteed on Android. No changes to the Linux converter or PPP are needed.
