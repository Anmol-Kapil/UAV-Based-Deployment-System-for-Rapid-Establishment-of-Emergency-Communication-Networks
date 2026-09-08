# UAV Emergency GCS — QGroundControl Custom Build

This directory contains the complete QGroundControl **Custom Build** for the UAV-Based Emergency Communication Network Deployment System.

## Architecture

This is NOT a fork of QGC source — it's a **custom plugin overlay** that plugs into the official QGroundControl codebase using QGC's documented Custom Build mechanism. This means:

- ✅ All of QGC's MAVLink stack, flight control, and telemetry work out of the box
- ✅ ARM, TAKEOFF, LAND, RTL, LOITER, POSCTL all work exactly as in stock QGC  
- ✅ Mission planning, waypoints, and `.plan` file support all included
- ✅ Our emergency domain features are injected as overlay widgets
- ✅ Easy to update from upstream QGC without merge conflicts

## UI Preview

![UAV Emergency GCS UI](../../.gemini/antigravity-ide/brain/48cfa310-6a41-4274-8520-88c16e061083/qgc_custom_preview_1788856132973.jpg)

## Custom Features Added

| Feature | Implementation |
|---------|---------------|
| **Emergency Mode Banner** | Red pulsing alert strip at top of Fly View |
| **Relay Network Status** | Bottom-left panel: deployed node count, RF signal bars |
| **Deploy Node Button** | Prominent orange button — sends `MAV_CMD_DO_SET_SERVO` (AUX1, PWM 1900) |
| **Custom HUD Panel** | ARM status, flight mode, altitude, speed, battery bar |
| **Emergency Mode Toggle** | Bottom-right toggle to activate emergency deployment mode |
| **RF Network Survey** | Custom mission item type via PerimeterScan plugin |
| **Emergency GCS Settings** | Settings page: servo channels, PWM values, operator callsign, RF band |

## Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Deep Navy | `#0A1628` | Background |
| Alert Orange | `#FF6B2B` | Primary accent, Deploy button, warnings |
| Electric Blue | `#00A8FF` | Network/RF info, mode display |
| Success Green | `#00D084` | Armed, connected, deployed nodes |
| Emergency Red | `#FF3B3B` | Disarmed, alerts, low battery |

## Build Instructions

### Prerequisites

1. **Qt 6.8.3** — Download from https://www.qt.io/download-qt-installer
   - Select: `Qt 6.8.3 > MSVC 2019 64-bit`
   - Also select: Qt5Compat, Qt Multimedia, Qt Charts, Qt Positioning, Qt Location
2. **CMake 4.4+** — Already installed via winget
3. **Visual Studio 2022 Build Tools** — Already installed
4. **Git** — Already installed

### Clone QGC (already done at C:\qgc)

```bash
git clone --recursive https://github.com/mavlink/qgroundcontrol.git C:\qgc
```

### Copy this custom/ folder

```bash
# From inside C:\qgc:
xcopy /E /I path\to\this\qgc_custom C:\qgc\custom
```

### Install Dependencies

```bash
cd C:\qgc
python tools/setup/install_dependencies.py --platform windows
```

### Build

```bash
cd C:\qgc
cmake -B build ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DQT_DIR="C:\Qt\6.8.3\msvc2019_64\lib\cmake\Qt6" ^
  -DQGC_CUSTOM_BUILD=ON ^
  -DQGC_CUSTOM_DIR=custom

cmake --build build --parallel --config Release
```

Or open `C:\qgc\CMakeLists.txt` in Qt Creator and configure with `QGC_CUSTOM_BUILD=ON, QGC_CUSTOM_DIR=custom`.

### Run + Connect to SITL

1. Launch PX4 SITL in WSL: `make px4_sitl gz_x500`
2. Run the built `UAV-Emergency-GCS.exe`  
3. Click the connection button → `UDP Link → 127.0.0.1:14550`
4. Drone connects and all flight controls work immediately

## File Structure

```
qgc_custom/
├── CMakeLists.txt                    — Build registration
├── cmake/CustomOverrides.cmake       — App name, icon paths, PX4-only
├── src/
│   ├── CustomPlugin.h/.cc            — QGCCorePlugin subclass (palette, settings, mission items)
│   ├── CustomGuidedActionsController.qml  — "Deploy Node" guided action
│   ├── FlyViewCustomLayer.qml        — Emergency overlay widgets (main custom UI)
│   ├── FlyViewToolStripActionList.qml — Left toolbar with "Deploy Node" button
│   ├── FirmwarePlugin/               — PX4-only firmware plugin
│   ├── AutoPilotPlugin/              — Simplified vehicle setup pages
│   ├── MissionManager/               — RF Network Survey complex mission item
│   ├── Settings/                     — Emergency deployment settings group
│   └── AppSettings/pages/            — Settings UI page definition
└── res/
    ├── Custom/Widgets/               — Custom QML widget components
    ├── Images/                       — HUD SVG assets
    ├── icons/                        — App icons (ICO, ICNS, SVG)
    └── json/                         — Mission item settings JSON
```
