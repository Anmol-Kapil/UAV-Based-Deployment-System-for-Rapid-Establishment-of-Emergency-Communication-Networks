/****************************************************************************
 * UAV Emergency GCS — Custom QGC Plugin Implementation
 * Emergency theme palette: deep navy + alert orange + electric blue
 ****************************************************************************/

#include "CustomPlugin.h"
#include "CustomSettings.h"
#include "PerimeterScanComplexItem.h"
#include "PerimeterScanPlanCreator.h"
#include "QGCPalette.h"
#include "SettingsManager.h"

#include <QtCore/QFile>
#include <QtQml/QQmlApplicationEngine>

QGC_LOGGING_CATEGORY(CustomLog, "CustomLog")

//=============================================================================
// CustomFlyViewOptions
//=============================================================================

CustomFlyViewOptions::CustomFlyViewOptions(CustomOptions *options, QObject *parent)
    : QGCFlyViewOptions(options, parent)
{
}

//=============================================================================
// CustomOptions
//=============================================================================

CustomOptions::CustomOptions(CustomPlugin *plugin, QObject *parent)
    : QGCOptions(parent)
    , _plugin(plugin)
    , _flyViewOptions(new CustomFlyViewOptions(this, this))
{
}

//=============================================================================
// CustomPlugin
//=============================================================================

CustomPlugin::CustomPlugin(QObject *parent)
    : QGCCorePlugin(parent)
{
    _options = new CustomOptions(this, this);
    connect(this, &QGCCorePlugin::showAdvancedUIChanged, this, &CustomPlugin::_advancedChanged);
}

QGCCorePlugin *CustomPlugin::instance()
{
    return new CustomPlugin();
}

void CustomPlugin::_advancedChanged(bool /*advanced*/)
{
    // Emit toolBarIndicatorsChanged so the toolbar rebuilds with the correct
    // set of indicators for the current advanced/simple mode.
    emit toolBarIndicatorsChanged();
}

void CustomPlugin::adjustSettingMetaData(const QString &settingsGroup, FactMetaData &metaData, bool &userVisible)
{
    // Hide Virtual Joystick setting — we have our own manual-control layer
    if (settingsGroup == QStringLiteral("App") && metaData.name() == QStringLiteral("virtualJoystick")) {
        userVisible = false;
    }
    // Hide Autoconnect Pixhawk (we always connect via UDP)
    if (settingsGroup == QStringLiteral("App") && metaData.name() == QStringLiteral("autoConnectPixhawk")) {
        userVisible = false;
    }
}

//=============================================================================
// Emergency palette: deep navy background + alert orange accent + electric blue
//=============================================================================
void CustomPlugin::paletteOverride(const QString &colorName, QGCPalette::PaletteColorInfo_t &colorInfo)
{
    // Primary window background — deep navy
    if (colorName == QStringLiteral("window")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#0A1628");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#07101e");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#f0f4f8");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#e0e8f0");
    } else if (colorName == QStringLiteral("windowShade")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#0d1e36");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#0a1628");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#dce8f5");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#ccdaec");
    } else if (colorName == QStringLiteral("windowShadeDark")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#060e1a");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#040b14");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#c5d8eb");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#b0cade");
    } else if (colorName == QStringLiteral("text")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#E8EFF8");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#6a7a8e");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#0A1628");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#4a5a6e");
    } else if (colorName == QStringLiteral("button")) {
        // Alert orange for primary buttons
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF6B2B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a3315");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#FF6B2B");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#f5bda0");
    } else if (colorName == QStringLiteral("buttonText")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FFFFFF");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a7a7a");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#FFFFFF");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#888888");
    } else if (colorName == QStringLiteral("buttonHighlight")) {
        // Electric blue hover highlight
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#00A8FF");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#005580");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#00A8FF");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#80d4ff");
    } else if (colorName == QStringLiteral("colorGreen")) {
        // Success green for armed/connected states
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#00D084");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#005a38");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#00b870");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#70d4aa");
    } else if (colorName == QStringLiteral("colorRed")) {
        // Emergency red for disarmed/alert states
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF3B3B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a1c1c");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#e82020");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#f07070");
    } else if (colorName == QStringLiteral("colorOrange")) {
        // Alert orange = our brand accent
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF6B2B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a3315");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#e55c20");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#f0a080");
    } else if (colorName == QStringLiteral("colorBlue")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#00A8FF");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#005580");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#0080cc");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#80c0e0");
    } else if (colorName == QStringLiteral("alertBackground")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF3B3B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a1c1c");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#fff0f0");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#ffd0d0");
    } else if (colorName == QStringLiteral("alertBorder")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF6B2B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#7a3315");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#FF6B2B");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#f0a080");
    } else if (colorName == QStringLiteral("alertText")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FFFFFF");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#cccccc");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#0A1628");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#4a5a6e");
    } else if (colorName == QStringLiteral("hoverColor")) {
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#1a3558");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#0d1e36");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#cce0f5");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#b0cce0");
    } else if (colorName == QStringLiteral("brandingPurple")) {
        // Repurpose brandingPurple as our deep navy brand color
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#0A1628");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#0A1628");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#0A1628");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#0A1628");
    } else if (colorName == QStringLiteral("brandingBlue")) {
        // Repurpose brandingBlue as our alert orange brand accent
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupEnabled]   = QColor("#FF6B2B");
        colorInfo[QGCPalette::Dark][QGCPalette::ColorGroupDisabled]  = QColor("#00A8FF");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupEnabled]  = QColor("#FF6B2B");
        colorInfo[QGCPalette::Light][QGCPalette::ColorGroupDisabled] = QColor("#00A8FF");
    }
}

//=============================================================================
// QML Engine Setup — register custom QML modules + URL override interceptor
//=============================================================================
QQmlApplicationEngine *CustomPlugin::createQmlApplicationEngine(QObject *parent)
{
    _qmlEngine = QGCCorePlugin::createQmlApplicationEngine(parent);
    _qmlEngine->addImportPath("qrc:/qml/Custom/Widgets");
    _qmlEngine->addImportPath("qrc:/qml/Custom/Plan");

    _urlInterceptor = new CustomOverrideInterceptor();
    _qmlEngine->addUrlInterceptor(_urlInterceptor);

    return _qmlEngine;
}

void CustomPlugin::destroyQmlApplicationEngine(QQmlApplicationEngine *qmlEngine)
{
    if (qmlEngine && (qmlEngine == _qmlEngine)) {
        qmlEngine->removeUrlInterceptor(_urlInterceptor);
        delete _urlInterceptor;
        _urlInterceptor = nullptr;
        _qmlEngine      = nullptr;
    }
    QGCCorePlugin::destroyQmlApplicationEngine(qmlEngine);
}

//=============================================================================
// Custom mission items — Relay Node Deployment (uses PerimeterScanComplexItem as base)
//=============================================================================
QVariantList CustomPlugin::complexMissionItemNames(Vehicle *vehicle)
{
    QVariantList items = QGCCorePlugin::complexMissionItemNames(vehicle);

    QVariantMap entry;
    entry[QStringLiteral("canonicalName")]  = QString(PerimeterScanComplexItem::canonicalName);
    entry[QStringLiteral("translatedName")] = PerimeterScanComplexItem::tr("RF Network Survey");
    items.append(entry);

    return items;
}

ComplexMissionItem *CustomPlugin::createComplexMissionItem(const QString &complexItemType,
                                                            PlanMasterController *masterController,
                                                            bool flyView,
                                                            const QString &kmlOrShpFile)
{
    if (complexItemType == PerimeterScanComplexItem::canonicalName
            || complexItemType == PerimeterScanComplexItem::jsonComplexItemTypeValue) {
        return new PerimeterScanComplexItem(masterController, flyView, kmlOrShpFile);
    }
    return QGCCorePlugin::createComplexMissionItem(complexItemType, masterController, flyView, kmlOrShpFile);
}

QList<PlanCreator *> CustomPlugin::planCreators(PlanMasterController *planMasterController)
{
    QList<PlanCreator *> creators = QGCCorePlugin::planCreators(planMasterController);
    creators.append(new PerimeterScanPlanCreator(planMasterController));
    return creators;
}

void CustomPlugin::registerCustomSettings(SettingsManager *settingsManager)
{
    settingsManager->registerCustomSettings(new CustomSettings(settingsManager));
}

//=============================================================================
// CustomOverrideInterceptor — redirect qrc:/.../X.qml to qrc:/Custom/.../X.qml
//=============================================================================
CustomOverrideInterceptor::CustomOverrideInterceptor()
    : QQmlAbstractUrlInterceptor()
{
}

QUrl CustomOverrideInterceptor::intercept(const QUrl &url, QQmlAbstractUrlInterceptor::DataType type)
{
    switch (type) {
    case QQmlAbstractUrlInterceptor::QmlFile:
    case QQmlAbstractUrlInterceptor::UrlString:
        if (url.scheme() == QStringLiteral("qrc")) {
            const QString origPath    = url.path();
            const QString overrideRes = QStringLiteral(":/Custom%1").arg(origPath);
            if (QFile::exists(overrideRes)) {
                const QString relPath = overrideRes.mid(2);
                QUrl result;
                result.setScheme(QStringLiteral("qrc"));
                result.setPath('/' + relPath);
                return result;
            }
        }
        break;
    default:
        break;
    }
    return url;
}
