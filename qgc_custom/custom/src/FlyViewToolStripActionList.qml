/****************************************************************************
 * UAV Emergency GCS — Custom Fly View Tool Strip
 *
 * Replaces QGC''s default action list in the left tool strip with:
 *  - Standard: Takeoff, Land, RTL, Pause
 *  - Emergency: Deploy Node (custom action)
 *  - RF Survey mode toggle
 *  - Preflight Checklist
 ****************************************************************************/

import QtQml.Models

import QGroundControl
import QGroundControl.Controls
import QGroundControl.FlyView

ToolStripActionList {
    id: _root

    signal displayPreFlightChecklist

    model: [
        PreFlightCheckListShowAction { onTriggered: displayPreFlightChecklist() },
        GuidedActionTakeoff          { },
        GuidedActionLand             { },
        GuidedActionRTL              { },
        GuidedActionPause            { },
        FlyViewAdditionalActionsButton { },
        GuidedToolStripAction {
            text:       "Deploy Node"
            iconSource: "/res/gear-white.svg"
            visible:    QGroundControl.multiVehicleManager.activeVehicle !== null
            enabled:    QGroundControl.multiVehicleManager.activeVehicle !== null &&
                        QGroundControl.multiVehicleManager.activeVehicle.armed
            actionID:   _guidedController._customController.actionCustomButton
        }
    ]
}
