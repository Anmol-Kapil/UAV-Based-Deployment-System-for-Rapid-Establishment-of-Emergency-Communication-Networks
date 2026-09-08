#pragma once

#include <QtQmlIntegration/QtQmlIntegration>

#include "SettingsGroup.h"

/// UAV Emergency GCS custom settings group.
/// Exposes domain-specific facts to QML as:
///   QGroundControl.settingsManager.customSettings.<factName>
class CustomSettings : public SettingsGroup
{
    Q_OBJECT
    QML_ELEMENT
    QML_UNCREATABLE("")

public:
    CustomSettings(QObject *parent = nullptr);

    DEFINE_SETTING_NAME_GROUP()

    // Emergency deployment settings
    DEFINE_SETTINGFACT(deployPayloadServo)   // Servo channel for payload release (default 9)
    DEFINE_SETTINGFACT(deployPayloadPwmOpen) // PWM open/release value (default 1900)
    DEFINE_SETTINGFACT(deployPayloadPwmClose)// PWM close value (default 1100)
    DEFINE_SETTINGFACT(totalRelayNodes)      // Total planned relay nodes for this mission

    // RF Survey settings
    DEFINE_SETTINGFACT(rfFrequencyBand)      // RF band (2.4GHz / 5.8GHz / 915MHz)
    DEFINE_SETTINGFACT(rfSurveyDuration)     // Dwell time per survey point (seconds)

    // Operator info
    DEFINE_SETTINGFACT(operatorCallsign)     // Field operator callsign
    DEFINE_SETTINGFACT(showAttitudeWidget)   // Show/hide attitude overlay
};
