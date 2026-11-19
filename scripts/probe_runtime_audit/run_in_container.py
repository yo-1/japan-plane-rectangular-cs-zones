import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/work');out=ROOT/'results'
if out.exists() and any(out.iterdir()):raise FileExistsError('Use an empty results directory; earlier runs are preserved')
out.mkdir(exist_ok=True)
env=dict(os.environ);env.update(DISPLAY=':97',QT_QPA_PLATFORM='xcb',XDG_RUNTIME_DIR='/tmp/qgis-probe-runtime',QGIS_DEV_PROBE_HOME='/work/results/probe-home',QGIS_DEV_PROBE_AUTOSTART='0',QGIS_DEV_PROBE_ALLOW_EXEC='1',PYTHONPATH='/mcp-site:/work/probe-source/src')
Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700,exist_ok=True)
x=q=None
try:
    with (out/'xvfb.log').open('w') as log:x=subprocess.Popen(['Xvfb',':97','-screen','0','1600x1100x24','-nolisten','tcp'],stdout=log,stderr=subprocess.STDOUT)
    time.sleep(1)
    with (out/'qgis.log').open('w') as log:q=subprocess.Popen(['qgis','--nologo','--noversioncheck','--noplugins','--profiles-path','/work/results/profile','--profile','probe-current','--code','/work/bootstrap.py'],env=env,stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+180
    capture_after=time.monotonic()+8
    captured=False
    while not (out/'startup.json').exists():
        if not captured and time.monotonic()>capture_after:
            subprocess.run(['/usr/bin/python3','-c',"from PyQt5.QtWidgets import QApplication; app=QApplication([]); app.primaryScreen().grabWindow(0).save('/work/results/startup-screen.png')"],env=env,timeout=10)
            captured=True
        if q.poll() is not None or time.monotonic()>deadline:raise RuntimeError('QGIS startup failed; inspect results/qgis.log')
        time.sleep(.2)
    j=json.loads((out/'startup.json').read_text());assert j['ok'],j
    print('QGIS ready:',j,flush=True)
    subprocess.run(['/usr/bin/python3','/work/check_live.py'],env=env,check=True,timeout=1000)
finally:
    if q and q.poll() is None:
        (out/'stop').touch()
        try:q.wait(timeout=15)
        except subprocess.TimeoutExpired:q.terminate();q.wait(timeout=5)
    if x and x.poll() is None:x.terminate();x.wait(timeout=5)
    lifecycle={'qgis_exit_code':q.returncode if q else None,'xvfb_stopped':x is None or x.poll() is not None,'endpoint_removed':not(out/'probe-home/endpoint.json').exists()}
    (out/'lifecycle.json').write_text(json.dumps(lifecycle,indent=2)+'\n')
    print('Shutdown:',lifecycle,flush=True)
