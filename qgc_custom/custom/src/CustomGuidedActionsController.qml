/****************************************************************************
 * UAV Emergency GCS — Custom Guided Actions Controller
 *
 * Adds "Deploy Relay Node" as a custom guided action accessible from the
 * Fly View tool strip. When executed it triggers our node deployment protocol.
 ****************************************************************************/

import QtQml

import QGroundControl

QtObject {
    id: _root

    readonly property int    actionCustomButton   : _guidedController.customActionStart + 0
    readonly property string customButtonTitle    : qsTr("Deploy Relay Node")
    readonly property string customButtonMessage  : qsTr("Deploy a relay/mesh network node at the current vehicle position. The drone will hold position while the node is released.")

    function customConfirmAction(actionCode, actionData, mapIndicator, confirmDialog) {
        switch (actionCode) {
        case actionCustomButton:
            confirmDialog.hideTrigger   = true
            confirmDialog.title         = customButtonTitle
            confirmDialog.message       = customButtonMessage
            break
        default:
            return false
        }
        return true
    }

    function customExecuteAction(actionCode, actionData, sliderOutputValue, optionChecked) {
        switch (actionCode) {
        case actionCustomButton:
            // Issue MAVLink DO_SET_SERVO to trigger payload release mechanism
            // Servo 9 (AUX1), PWM 1900 = release
            var vehicle = QGroundControl.multiVehicleManager.activeVehicle
            if (vehicle) {
                vehicle.sendMavCommand(
                    vehicle.defaultComponentId,
                    183, // MAV_CMD_DO_SET_SERVO
                    true, // showError
                    9,    // Servo number (AUX1 = payload release)
                    1900, // PWM value — open/release
                    0, 0, 0, 0, 0
                )
                QGroundControl.showMessageDialog(
                    mainWindow,
                    "Relay Node Deployment",
                    "? Deployment command sent to drone.\nNode release mechanism activated on AUX1 (PWM 1900).\n\nDrone is holding position."
                )
            }
            break
        default:
            return false
        }
        return true
    }
}
