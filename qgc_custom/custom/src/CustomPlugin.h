/****************************************************************************
 * UAV Emergency GCS — Custom QGC Plugin
 * Inherits QGCCorePlugin to provide branding, emergency palette, and domain-
 * specific features: Relay Node Deployment, RF Network Survey, Disaster Scenario.
 ****************************************************************************/

#pragma once

#include <QtCore/QTranslator>
#include <QtQml/QQmlAbstractUrlInterceptor>

#include "QGCCorePlugin.h"
#include "QGCOptions.h"

class ComplexMissionItem;
class PlanCreator;

class CustomOptions;
class CustomPlugin;
class QQmlApplicationEngine;

Q_DECLARE_LOGGING_CATEGORY(CustomLog)

//-----------------------------------------------------------------------------
// FlyView options: hide stock instrument panel (we provide our own emergency panel)
class CustomFlyViewOptions : public QGCFlyViewOptions
{
    Q_OBJECT

public:
    explicit CustomFlyViewOptions(CustomOptions *options, QObject *parent = nullptr);

    // Hide QGC default instrument panel — our FlyViewCustomLayer provides the emergency one
    bool showInstrumentPanel() const final { return false; }
    // Single-vehicle emergency deployment — hide multi-vehicle list
    bool showMultiVehicleList() const final { return false; }
};

//-----------------------------------------------------------------------------
class CustomOptions : public QGCOptions
{
    Q_OBJECT

public:
    explicit CustomOptions(CustomPlugin *plugin, QObject *parent = nullptr);

    bool showFirmwareUpgrade() const final { return _plugin->showAdvancedUI(); }
    QGCFlyViewOptions *flyViewOptions() const final { return _flyViewOptions; }

private:
    QGCCorePlugin        *_plugin         = nullptr;
    CustomFlyViewOptions *_flyViewOptions = nullptr;
};

//-----------------------------------------------------------------------------
class CustomPlugin : public QGCCorePlugin
{
    Q_OBJECT

public:
    explicit CustomPlugin(QObject *parent = nullptr);

    static QGCCorePlugin *instance();

    // QGCCorePlugin overrides
    QGCOptions       *options() final { return _options; }
    void              adjustSettingMetaData(const QString &settingsGroup, FactMetaData &metaData, bool &userVisible) final;
    void              paletteOverride(const QString &colorName, QGCPalette::PaletteColorInfo_t &colorInfo) final;
    QQmlApplicationEngine *createQmlApplicationEngine(QObject *parent) final;
    void              destroyQmlApplicationEngine(QQmlApplicationEngine *qmlEngine) final;

    // Custom mission items: Relay Node Deployment + RF Survey
    QVariantList      complexMissionItemNames(Vehicle *vehicle) final;
    ComplexMissionItem *createComplexMissionItem(const QString &complexItemType,
                                                 PlanMasterController *masterController,
                                                 bool flyView,
                                                 const QString &kmlOrShpFile = QString()) final;
    QList<PlanCreator *> planCreators(PlanMasterController *planMasterController) final;
    void              registerCustomSettings(SettingsManager *settingsManager) final;

private slots:
    void _advancedChanged(bool advanced);

private:
    CustomOptions              *_options      = nullptr;
    QQmlApplicationEngine      *_qmlEngine    = nullptr;
    class CustomOverrideInterceptor *_urlInterceptor = nullptr;
};

//-----------------------------------------------------------------------------
// QML URL interceptor: redirect qrc:/... to qrc:/Custom/... overrides
class CustomOverrideInterceptor : public QQmlAbstractUrlInterceptor
{
public:
    CustomOverrideInterceptor();
    QUrl intercept(const QUrl &url, QQmlAbstractUrlInterceptor::DataType type) final;
};
