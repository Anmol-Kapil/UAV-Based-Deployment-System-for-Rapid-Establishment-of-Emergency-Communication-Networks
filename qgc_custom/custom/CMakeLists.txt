# =============================================================================
# UAV Emergency GCS — Custom Build CMakeLists
# Based on QGroundControl custom-example pattern
# =============================================================================

cmake_minimum_required(VERSION 3.28)

# Load application branding and icon overrides
include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/CustomOverrides.cmake)

# =============================================================================
# Custom Image Resources (telemetry HUD SVGs from custom-example base)
# =============================================================================
set(CUSTOM_IMAGE_RESOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/altitude.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/attitude_crosshair.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/attitude_dial.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/attitude_pointer.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/chronometer.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/compass_needle.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/compass_pointer.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/distance.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/horizontal_speed.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/microSD.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/odometer.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/vertical_speed.svg"
)
qgc_set_qt_resource_alias(${CUSTOM_IMAGE_RESOURCES})
qt_add_resources(${CMAKE_PROJECT_NAME} custom_images
    PREFIX "/custom/img"
    FILES ${CUSTOM_IMAGE_RESOURCES}
)

# Drone vehicle icon (paper plane ? emergency UAV icon override)
set(CUSTOM_VEHICLE_ICON "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/CustomVehicleIcon.svg")
set_source_files_properties("${CUSTOM_VEHICLE_ICON}" PROPERTIES QT_RESOURCE_ALIAS "PaperPlane.svg")
qt_add_resources(${CMAKE_PROJECT_NAME} custom_vehicle_icon
    PREFIX "/Custom/qmlimages"
    FILES "${CUSTOM_VEHICLE_ICON}"
)

# =============================================================================
# QML Overrides — these files replace stock QGC QML via URL interceptor
# =============================================================================
set(CUSTOM_QML_OVERRIDES
    "${CMAKE_CURRENT_SOURCE_DIR}/src/CustomGuidedActionsController.qml"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/FlyViewCustomLayer.qml"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/FlyViewToolStripActionList.qml"
)
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/src/CustomGuidedActionsController.qml"
    PROPERTIES QT_RESOURCE_ALIAS "QGroundControl/FlyView/CustomGuidedActionsController.qml"
)
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/src/FlyViewCustomLayer.qml"
    PROPERTIES QT_RESOURCE_ALIAS "QGroundControl/FlyView/FlyViewCustomLayer.qml"
)
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/src/FlyViewToolStripActionList.qml"
    PROPERTIES QT_RESOURCE_ALIAS "QGroundControl/FlyView/FlyViewToolStripActionList.qml"
)
qt_add_resources(${CMAKE_PROJECT_NAME} custom_qml_overrides
    PREFIX "/Custom/qml"
    FILES ${CUSTOM_QML_OVERRIDES}
)

# =============================================================================
# Brand Resources — Logo + Windows ICO
# =============================================================================
set(CUSTOM_BRAND_RESOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/res/Images/QGCLogoFull.svg"
    "${CMAKE_CURRENT_SOURCE_DIR}/res/icons/custom_qgroundcontrol.ico"
)
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/res/Images/QGCLogoFull.svg"
    PROPERTIES QT_RESOURCE_ALIAS "QGCLogoFull.svg"
)
set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/res/icons/custom_qgroundcontrol.ico"
    PROPERTIES QT_RESOURCE_ALIAS "qgroundcontrol.ico"
)
qt_add_resources(${CMAKE_PROJECT_NAME} custom_brand
    PREFIX "/Custom/res"
    FILES ${CUSTOM_BRAND_RESOURCES}
)

# Shared gear icon (used by tool strip)
set(CUSTOM_SHARED_GEAR "${CMAKE_SOURCE_DIR}/resources/gear-white.svg")
set_source_files_properties("${CUSTOM_SHARED_GEAR}" PROPERTIES QT_RESOURCE_ALIAS "gear-white.svg")
qt_add_resources(${CMAKE_PROJECT_NAME} custom_shared_resources
    PREFIX "/res"
    FILES "${CUSTOM_SHARED_GEAR}"
)

# =============================================================================
# JSON Resources — Settings groups + RF Survey mission type
# =============================================================================
set(CUSTOM_JSON_RESOURCE "${CMAKE_CURRENT_SOURCE_DIR}/res/json/PerimeterScan.SettingsGroup.json")
qgc_set_qt_resource_alias("${CUSTOM_JSON_RESOURCE}")
qt_add_resources(${CMAKE_PROJECT_NAME} custom_json
    PREFIX "/json"
    FILES "${CUSTOM_JSON_RESOURCE}"
)

set(CUSTOM_SETTINGS_JSON_RESOURCE "${CMAKE_CURRENT_SOURCE_DIR}/src/Settings/Custom.SettingsGroup.json")
qgc_set_qt_resource_alias("${CUSTOM_SETTINGS_JSON_RESOURCE}")
qt_add_resources(${CMAKE_PROJECT_NAME} custom_settings_json
    PREFIX "/json"
    FILES "${CUSTOM_SETTINGS_JSON_RESOURCE}"
)

list(APPEND QML_IMPORT_PATH "${CMAKE_CURRENT_SOURCE_DIR}/res")
set(QML_IMPORT_PATH "${QML_IMPORT_PATH}" CACHE STRING "Extra QML import paths" FORCE)

# =============================================================================
# Custom QML Module — Emergency Widgets
# =============================================================================
qt_add_library(CustomModule STATIC)
qgc_configure_target(CustomModule)

set_source_files_properties(${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomArtificialHorizon.qml
    PROPERTIES QT_RESOURCE_ALIAS CustomArtificialHorizon.qml)
qgc_set_qt_resource_alias(
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomAttitudeWidget.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomIconButton.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomOnOffSwitch.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomQuickButton.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomSignalStrength.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomToolBarButton.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomVehicleButton.qml
)

qt_add_qml_module(CustomModule
    URI Custom.Widgets
    VERSION 1.0
    RESOURCE_PREFIX /qml
    QML_FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomArtificialHorizon.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomAttitudeWidget.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomIconButton.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomOnOffSwitch.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomQuickButton.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomSignalStrength.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomToolBarButton.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/res/Custom/Widgets/CustomVehicleButton.qml
    NO_PLUGIN
)

# =============================================================================
# Custom Plan Module — RF Network Survey mission type
# =============================================================================
qt_add_library(CustomPlanModule STATIC)
qgc_configure_target(CustomPlanModule)

qgc_set_qt_resource_alias(
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PlanView/PerimeterScanMapVisual.qml
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PlanView/PerimeterScanEditor.qml
)

qt_add_qml_module(CustomPlanModule
    URI Custom.Plan
    VERSION 1.0
    RESOURCE_PREFIX /qml
    QML_FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/src/PlanView/PerimeterScanMapVisual.qml
        ${CMAKE_CURRENT_SOURCE_DIR}/src/PlanView/PerimeterScanEditor.qml
    NO_PLUGIN
)

# =============================================================================
# Custom Plugin C++ Sources
# =============================================================================
set(CUSTOM_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/CustomPlugin.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/CustomPlugin.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/AutoPilotPlugin/CustomAutoPilotPlugin.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/AutoPilotPlugin/CustomAutoPilotPlugin.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FirmwarePlugin/CustomFirmwarePlugin.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FirmwarePlugin/CustomFirmwarePlugin.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FirmwarePlugin/CustomFirmwarePluginFactory.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FirmwarePlugin/CustomFirmwarePluginFactory.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MissionManager/PerimeterScanComplexItem.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MissionManager/PerimeterScanComplexItem.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MissionManager/PerimeterScanPlanCreator.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MissionManager/PerimeterScanPlanCreator.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Settings/CustomSettings.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Settings/CustomSettings.h
    PARENT_SCOPE
)

# =============================================================================
# Exported CMake variables required by QGC parent CMakeLists
# =============================================================================
set(CUSTOM_LIBRARIES
    CustomModule
    CustomPlanModule
    PARENT_SCOPE
)

set(CUSTOM_INCLUDE_DIRECTORIES
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/AutoPilotPlugin
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FirmwarePlugin
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MissionManager
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Settings
    PARENT_SCOPE
)

set(CUSTOM_DEFINITIONS
    QGC_CUSTOM_BUILD
    CUSTOMHEADER="CustomPlugin.h"
    CUSTOMCLASS=CustomPlugin
    PARENT_SCOPE
)

set(CUSTOM_QT_COMPONENTS
    Core
    PARENT_SCOPE
)
