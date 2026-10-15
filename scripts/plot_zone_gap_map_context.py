"""Context at candidate representative points using GSI standard map tiles.

Map depiction is contextual evidence only: it is not an administrative-boundary
or historical-water-surface determination. Raw tile bytes and URLs are retained.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

if 'MPLCONFIGDIR' not in os.environ:
    os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp(prefix='zone-gap-map-mpl-')
if 'XDG_CACHE_HOME' not in os.environ:
    os.environ['XDG_CACHE_HOME'] = tempfile.mkdtemp(prefix='zone-gap-map-font-cache-')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyproj


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audit', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.audit/'candidates.csv').open() as f:
        rows = [r for r in csv.DictReader(f) if float(r['area_m2']) >= 1 and r['void_empty'] == 'False']
    if not rows:
        return
    fig, axes = plt.subplots(math.ceil(len(rows)/3), 3, figsize=(12, math.ceil(len(rows)/3)*4.8+1), squeeze=False)
    mercator = pyproj.Transformer.from_crs(6668, 3857, always_xy=True)
    manifest = []
    for ax, r in zip(axes.flat, rows):
        lon, lat = float(r['longitude']), float(r['latitude']);z=16;n=2**z
        x=int((lon+180)/360*n)
        y=int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
        url=f'https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png'
        tile=args.output/(r['candidate_id']+'-gsi-std.png')
        subprocess.run(['curl','-fLsS','--retry','2','--max-time','45',url,'-o',str(tile)],check=True)
        half_world=math.pi*6378137.;step=2*half_world/n
        extent=[-half_world+x*step,-half_world+(x+1)*step,half_world-(y+1)*step,half_world-y*step]
        ax.imshow(plt.imread(tile),extent=extent)
        px,py=mercator.transform(lon,lat)
        ax.plot(px,py,'r+',markersize=12,markeredgewidth=1.5)
        ax.set_title(f"{r['candidate_id']}\nzone={r['zone']}  ({lon:.7f}, {lat:.7f})",fontsize=9)
        ax.set_xticks([]);ax.set_yticks([])
        manifest.append(dict(candidate_id=r['candidate_id'],url=url,zoom=z,x=x,y=y,
            sha256=hashlib.file_digest(tile.open('rb'),'sha256').hexdigest(),
            attribution='地理院タイル（標準地図）',retrieved_jst_date=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat(),
            interpretation='Context at representative point; no claim of historical, legal, or full-candidate coverage'))
    for ax in list(axes.flat)[len(rows):]:ax.axis('off')
    fig.suptitle('GSI standard map / representative point context (red +)\nMap date differs from N03 input date; no repair decision implied.')
    fig.subplots_adjust(top=.92, bottom=.03, hspace=.30, wspace=.08)
    fig.savefig(args.output/'gsi-point-context.png',dpi=150);plt.close(fig)
    (args.output/'map-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
