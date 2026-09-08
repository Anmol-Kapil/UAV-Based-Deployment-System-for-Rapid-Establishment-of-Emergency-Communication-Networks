#include "CustomSettings.h"

DECLARE_SETTINGGROUP(Custom, "Custom")
{
}

DECLARE_SETTINGSFACT(CustomSettings, deployPayloadServo)
DECLARE_SETTINGSFACT(CustomSettings, deployPayloadPwmOpen)
DECLARE_SETTINGSFACT(CustomSettings, deployPayloadPwmClose)
DECLARE_SETTINGSFACT(CustomSettings, totalRelayNodes)
DECLARE_SETTINGSFACT(CustomSettings, rfFrequencyBand)
DECLARE_SETTINGSFACT(CustomSettings, rfSurveyDuration)
DECLARE_SETTINGSFACT(CustomSettings, operatorCallsign)
DECLARE_SETTINGSFACT(CustomSettings, showAttitudeWidget)
