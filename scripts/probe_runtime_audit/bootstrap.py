import json
from pathlib import Path
import sys
import traceback
from qgis import utils
from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.PyQt.QtCore import QTimer
ROOT=Path('/work')
(ROOT/'results/bootstrap-entered').touch()
sys.path.insert(0,str(ROOT/'probe-source/plugin'))
sys.path.append('/usr/share/qgis/python/plugins')

def start():
    try:
        assert Qgis.QGIS_VERSION_INT>=34400, Qgis.QGIS_VERSION
        from processing.core.Processing import Processing
        Processing.initialize()
        assert utils.loadPlugin('qgis_dev_probe')
        assert utils.startPlugin('qgis_dev_probe')
        probe=utils.plugins['qgis_dev_probe']
        assert not probe.running
        probe.config.mode='interactive'
        probe.config.allow_exec=True
        probe.config.recipe_dir=str(ROOT/'recipes')
        probe.start_server()
        utils.iface.mainWindow().resize(1400,950)
        utils.iface.mainWindow().setWindowTitle('QGIS v2026.3 / probe 0.1.4 verification')
        (ROOT/'results/startup.json').write_text(json.dumps({'ok':True,'qgis':Qgis.QGIS_VERSION,'mode':probe.config.mode,'allow_exec':True,'processing_algorithms':len(QgsApplication.processingRegistry().algorithms())},indent=2))
    except Exception:
        (ROOT/'results/startup.json').write_text(json.dumps({'ok':False,'error':traceback.format_exc()},indent=2))

def end():
    if 'qgis_dev_probe' in utils.plugins:utils.unloadPlugin('qgis_dev_probe')
    QgsProject.instance().clear()
    QgsApplication.quit()

def poll():
    if (ROOT/'results/stop').exists():end()

timer=QTimer();timer.timeout.connect(poll);timer.start(250)
QTimer.singleShot(1200,start)
QTimer.singleShot(1200000,end)
