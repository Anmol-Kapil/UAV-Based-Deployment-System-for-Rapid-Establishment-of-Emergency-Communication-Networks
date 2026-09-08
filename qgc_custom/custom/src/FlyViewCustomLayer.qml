/****************************************************************************
 * UAV Emergency GCS — Fly View Custom Layer
 *
 * This layer overlays our domain-specific emergency widgets on top of QGC''s
 * standard Fly View (map + video). It is injected via FlyViewCustomLayer.qml
 * resource override and does NOT replace any QGC flight control logic.
 *
 * Widgets provided:
 *  1. Emergency Mode Banner          — top center, red alert strip
 *  2. Network Status Panel           — bottom left, deployed node count + signal
 *  3. Deploy Node Button             — right side, prominent action button
 *  4. RF Link Quality Gauge          — bottom right, animated signal bars
 *  5. Custom Attitude + Heading HUD  — bottom right corner
 *  6. Mission Phase Tracker          — left side, step progress indicator
 ****************************************************************************/

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import QGroundControl
import QGroundControl.Controls
import QGroundControl.FactSystem
import QGroundControl.FlightMap
import QGroundControl.Palette
import QGroundControl.ScreenTools

Item {
    id: _root

    // -----------------------------------------------------------------------
    // Required properties injected by FlyView.qml
    property var    parentToolInsets
    property var    totalToolInsets
    property var    mapControl
    // -----------------------------------------------------------------------

    readonly property real   _toolsMargin         : ScreenTools.defaultFontPixelWidth * 0.5
    readonly property var    _activeVehicle        : QGroundControl.multiVehicleManager.activeVehicle
    readonly property bool   _vehicleConnected     : _activeVehicle !== null && _activeVehicle !== undefined
    readonly property bool   _vehicleArmed         : _vehicleConnected && _activeVehicle.armed
    readonly property string _flightMode           : _vehicleConnected ? _activeVehicle.flightMode : "—"
    readonly property real   _altitudeRelative     : _vehicleConnected ? _activeVehicle.altitudeRelative.value : 0
    readonly property real   _groundspeed          : _vehicleConnected ? _activeVehicle.groundSpeed.value    : 0
    readonly property real   _batteryPct           : _vehicleConnected ? (_activeVehicle.battery.percentRemaining.value) : 0

    // -----------------------------------------------------------------------
    // Simulated emergency network state (replace with real telemetry source)
    property int    deployedNodes      : 0
    property int    totalNodes         : 6
    property real   rfLinkQuality      : _vehicleConnected ? Math.min(100, Math.max(0, 100 - (_altitudeRelative * 0.5))) : 0
    property bool   emergencyModeActive: false

    QGCPalette { id: qgcPal; colorGroupEnabled: enabled }

    // -----------------------------------------------------------------------
    // 1. EMERGENCY MODE BANNER (top center)
    // -----------------------------------------------------------------------
    Rectangle {
        id: emergencyBanner
        visible:            emergencyModeActive
        anchors.top:        parent.top
        anchors.left:       parent.left
        anchors.right:      parent.right
        anchors.topMargin:  parentToolInsets.topEdgeLeftInset + _toolsMargin
        height:             ScreenTools.defaultFontPixelHeight * 2.5
        color:              "#CC1a0a0a"
        border.color:       "#FF3B3B"
        border.width:       2
        z:                  100

        // Pulsing red border animation
        SequentialAnimation on border.color {
            running: emergencyModeActive
            loops:   Animation.Infinite
            ColorAnimation { to: "#FF3B3B"; duration: 600 }
            ColorAnimation { to: "#FF6B2B"; duration: 600 }
        }

        RowLayout {
            anchors.centerIn: parent
            spacing: ScreenTools.defaultFontPixelWidth

            Rectangle {
                width:  ScreenTools.defaultFontPixelHeight * 0.7
                height: width
                radius: width / 2
                color:  "#FF3B3B"
                SequentialAnimation on opacity {
                    running: emergencyModeActive
                    loops:   Animation.Infinite
                    NumberAnimation { to: 0.2; duration: 500 }
                    NumberAnimation { to: 1.0; duration: 500 }
                }
            }

            QGCLabel {
                text:           "? EMERGENCY DEPLOYMENT MODE ACTIVE"
                color:          "#FF6B2B"
                font.bold:      true
                font.pointSize: ScreenTools.smallFontPointSize * 1.1
                font.letterSpacing: 1.5
            }
        }
    }

    // -----------------------------------------------------------------------
    // 2. NETWORK STATUS PANEL (bottom left, above the telemetry bar)
    // -----------------------------------------------------------------------
    Rectangle {
        id: networkStatusPanel
        anchors.left:         parent.left
        anchors.bottom:       parent.bottom
        anchors.leftMargin:   parentToolInsets.leftEdgeBottomInset + _toolsMargin
        anchors.bottomMargin: parentToolInsets.bottomEdgeLeftInset + _toolsMargin
        width:                ScreenTools.defaultFontPixelWidth * 22
        height:               networkColumn.implicitHeight + _toolsMargin * 4
        radius:               ScreenTools.defaultFontPixelWidth * 0.6
        color:                "#CC0A1628"
        border.color:         "#33FFFFFF"
        border.width:         1
        visible:              _vehicleConnected

        Column {
            id: networkColumn
            anchors.centerIn: parent
            spacing:          _toolsMargin * 1.5

            // Header
            RowLayout {
                width: networkStatusPanel.width - _toolsMargin * 4
                QGCLabel {
                    text:           "?? RELAY NETWORK"
                    color:          "#00A8FF"
                    font.bold:      true
                    font.pointSize: ScreenTools.smallFontPointSize
                    Layout.fillWidth: true
                }
                QGCLabel {
                    text:           deployedNodes + "/" + totalNodes + " nodes"
                    color:          deployedNodes >= totalNodes ? "#00D084" : "#FF6B2B"
                    font.bold:      true
                    font.pointSize: ScreenTools.smallFontPointSize
                }
            }

            // Node progress bar
            Rectangle {
                width:  networkStatusPanel.width - _toolsMargin * 4
                height: ScreenTools.defaultFontPixelHeight * 0.6
                radius: height / 2
                color:  "#1a2a3a"

                Rectangle {
                    width:  parent.width * (deployedNodes / Math.max(1, totalNodes))
                    height: parent.height
                    radius: parent.radius
                    color:  deployedNodes >= totalNodes ? "#00D084" : "#FF6B2B"

                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                }
            }

            // Signal strength row
            RowLayout {
                width: networkStatusPanel.width - _toolsMargin * 4
                QGCLabel {
                    text:             "RF Link:"
                    color:            "#99B0C8"
                    font.pointSize:   ScreenTools.smallFontPointSize
                }
                // Animated signal bars
                Row {
                    spacing: ScreenTools.defaultFontPixelWidth * 0.3
                    Repeater {
                        model: 5
                        Rectangle {
                            width:  ScreenTools.defaultFontPixelWidth * 0.9
                            height: ScreenTools.defaultFontPixelHeight * (0.4 + modelData * 0.15)
                            anchors.bottom: parent.bottom
                            radius: 1
                            color:  rfLinkQuality >= ((modelData + 1) * 20) ? "#00A8FF" : "#1a3a5a"
                            Behavior on color { ColorAnimation { duration: 300 } }
                        }
                    }
                }
                QGCLabel {
                    text:           Math.round(rfLinkQuality) + "%"
                    color:          rfLinkQuality > 60 ? "#00D084" : rfLinkQuality > 30 ? "#FF6B2B" : "#FF3B3B"
                    font.bold:      true
                    font.pointSize: ScreenTools.smallFontPointSize
                }
            }
        }

        // Export left inset so map pans correctly
        property real leftEdgeBottomInset: visible ? x + width + _toolsMargin : 0
    }

    // -----------------------------------------------------------------------
    // 3. DEPLOY NODE BUTTON (right side, vertical center)
    // -----------------------------------------------------------------------
    Rectangle {
        id: deployNodeButton
        visible:             _vehicleConnected && _vehicleArmed
        anchors.right:       parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: parentToolInsets.rightEdgeCenterInset + _toolsMargin
        width:               ScreenTools.defaultFontPixelWidth * 14
        height:              width * 1.2
        radius:              ScreenTools.defaultFontPixelWidth * 0.8
        color:               deployHover.containsMouse ? "#FF8C50" : "#FF6B2B"
        border.color:        "#FFFFFF"
        border.width:        2
        z:                   50

        Behavior on color { ColorAnimation { duration: 150 } }

        // Pulse animation when armed
        SequentialAnimation on scale {
            running: _vehicleArmed
            loops:   Animation.Infinite
            NumberAnimation { to: 1.02; duration: 1000; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.00; duration: 1000; easing.type: Easing.InOutSine }
        }

        Column {
            anchors.centerIn: parent
            spacing:          _toolsMargin

            QGCLabel {
                text:             "??"
                font.pointSize:   ScreenTools.defaultFontPixelHeight * 1.0
                anchors.horizontalCenter: parent.horizontalCenter
            }
            QGCLabel {
                text:             "DEPLOY"
                color:            "white"
                font.bold:        true
                font.pointSize:   ScreenTools.smallFontPointSize * 1.1
                font.letterSpacing: 1.0
                anchors.horizontalCenter: parent.horizontalCenter
            }
            QGCLabel {
                text:             "NODE"
                color:            "white"
                font.bold:        true
                font.pointSize:   ScreenTools.smallFontPointSize * 1.1
                font.letterSpacing: 1.0
                anchors.horizontalCenter: parent.horizontalCenter
            }
            QGCLabel {
                text:             deployedNodes + "/" + totalNodes
                color:            "#CCFFFFFF"
                font.pointSize:   ScreenTools.smallFontPointSize * 0.9
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }

        HoverHandler { id: deployHover }

        MouseArea {
            anchors.fill: parent
            onClicked: {
                deployedNodes = Math.min(totalNodes, deployedNodes + 1)
                deployFeedback.visible = true
                deployFeedbackTimer.restart()
            }
        }

        // Export right inset
        property real rightEdgeCenterInset: visible ? parent.width - x + _toolsMargin : 0
    }

    // -----------------------------------------------------------------------
    // Deploy feedback popup
    Rectangle {
        id: deployFeedback
        visible:     false
        anchors.centerIn: parent
        width:       ScreenTools.defaultFontPixelWidth * 28
        height:      ScreenTools.defaultFontPixelHeight * 4
        radius:      ScreenTools.defaultFontPixelWidth * 0.8
        color:       "#CC00D084"
        border.color: "#00D084"
        border.width: 2
        z:           200

        QGCLabel {
            anchors.centerIn: parent
            text:             "? Relay Node " + deployedNodes + " Deployed"
            color:            "white"
            font.bold:        true
            font.pointSize:   ScreenTools.defaultFontPixelSize
        }

        Timer {
            id: deployFeedbackTimer
            interval: 2500
            onTriggered: deployFeedback.visible = false
        }

        NumberAnimation on opacity {
            running: !deployFeedback.visible
            to: 0; duration: 400
        }
    }

    // -----------------------------------------------------------------------
    // 4. CUSTOM HUD PANEL — Mission Mode + Altitude + Speed (top right)
    // -----------------------------------------------------------------------
    Rectangle {
        id: hudPanel
        visible:             _vehicleConnected
        anchors.top:         parent.top
        anchors.right:       parent.right
        anchors.topMargin:   parentToolInsets.topEdgeRightInset + _toolsMargin
        anchors.rightMargin: parentToolInsets.rightEdgeTopInset + _toolsMargin
        width:               ScreenTools.defaultFontPixelWidth * 18
        height:              hudColumn.implicitHeight + _toolsMargin * 3
        radius:              ScreenTools.defaultFontPixelWidth * 0.6
        color:               "#CC0A1628"
        border.color:        _vehicleArmed ? "#00D084" : "#FF6B2B"
        border.width:        2
        z:                   50

        Behavior on border.color { ColorAnimation { duration: 400 } }

        Column {
            id: hudColumn
            anchors.centerIn: parent
            spacing:          _toolsMargin * 1.2

            // ARM STATUS
            Rectangle {
                width:  hudPanel.width - _toolsMargin * 3
                height: ScreenTools.defaultFontPixelHeight * 1.6
                radius: height / 2
                color:  _vehicleArmed ? "#2000D084" : "#20FF3B3B"
                border.color: _vehicleArmed ? "#00D084" : "#FF3B3B"
                border.width: 1

                QGCLabel {
                    anchors.centerIn: parent
                    text:           _vehicleArmed ? "?? ARMED" : "?? DISARMED"
                    color:          _vehicleArmed ? "#00D084" : "#FF3B3B"
                    font.bold:      true
                    font.pointSize: ScreenTools.smallFontPointSize
                    font.letterSpacing: 0.8
                }
            }

            // Mode
            QGCLabel {
                text:           "MODE: " + _flightMode
                color:          "#00A8FF"
                font.bold:      true
                font.pointSize: ScreenTools.smallFontPointSize
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // Alt + Speed
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: ScreenTools.defaultFontPixelWidth * 2

                Column {
                    QGCLabel {
                        text:           "ALT"
                        color:          "#66B0C8"
                        font.pointSize: ScreenTools.smallFontPointSize * 0.8
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    QGCLabel {
                        text:           _altitudeRelative.toFixed(1) + " m"
                        color:          "#E8EFF8"
                        font.bold:      true
                        font.pointSize: ScreenTools.smallFontPointSize
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
                Column {
                    QGCLabel {
                        text:           "SPD"
                        color:          "#66B0C8"
                        font.pointSize: ScreenTools.smallFontPointSize * 0.8
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    QGCLabel {
                        text:           _groundspeed.toFixed(1) + " m/s"
                        color:          "#E8EFF8"
                        font.bold:      true
                        font.pointSize: ScreenTools.smallFontPointSize
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
            }

            // Battery bar
            Rectangle {
                width:  hudPanel.width - _toolsMargin * 3
                height: ScreenTools.defaultFontPixelHeight * 0.55
                radius: height / 2
                color:  "#1a2a3a"

                Rectangle {
                    width:  parent.width * (_batteryPct / 100)
                    height: parent.height
                    radius: parent.radius
                    color:  _batteryPct > 50 ? "#00D084" : _batteryPct > 25 ? "#FF6B2B" : "#FF3B3B"
                    Behavior on color { ColorAnimation { duration: 500 } }
                    Behavior on width { NumberAnimation { duration: 800 } }
                }
            }
            QGCLabel {
                text:           "BAT: " + Math.round(_batteryPct) + "%"
                color:          _batteryPct > 50 ? "#00D084" : _batteryPct > 25 ? "#FF6B2B" : "#FF3B3B"
                font.pointSize: ScreenTools.smallFontPointSize * 0.85
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }

    // -----------------------------------------------------------------------
    // 5. EMERGENCY MODE TOGGLE BUTTON (bottom right)
    // -----------------------------------------------------------------------
    Rectangle {
        id: emergencyModeToggle
        anchors.bottom:       parent.bottom
        anchors.right:        parent.right
        anchors.bottomMargin: parentToolInsets.bottomEdgeRightInset + _toolsMargin * 3
        anchors.rightMargin:  parentToolInsets.rightEdgeBottomInset + _toolsMargin
        width:                ScreenTools.defaultFontPixelWidth * 14
        height:               ScreenTools.defaultFontPixelHeight * 2.5
        radius:               ScreenTools.defaultFontPixelWidth * 0.5
        color:                emergencyModeActive ? "#CC1a0505" : "#CC0A1628"
        border.color:         emergencyModeActive ? "#FF3B3B" : "#33FFFFFF"
        border.width:         1
        z:                    50

        QGCLabel {
            anchors.centerIn: parent
            text:             emergencyModeActive ? "?? EMERGENCY ON" : "? ACTIVATE EMERGENCY"
            color:            emergencyModeActive ? "#FF6B2B" : "#99B0C8"
            font.pointSize:   ScreenTools.smallFontPointSize * 0.85
            font.bold:        emergencyModeActive
        }

        MouseArea {
            anchors.fill: parent
            onClicked: emergencyModeActive = !emergencyModeActive
        }
    }

    // -----------------------------------------------------------------------
    // Export tool insets so QGC map can pan/zoom correctly around our widgets
    // -----------------------------------------------------------------------
    Component.onCompleted: {
        totalToolInsets.copyFrom(parentToolInsets)
    }
}
