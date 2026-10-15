"""Compare N03 parent/hole rings with zoom-18 GSI map and aerial imagery.

Photo dates, tide, positional accuracy and legal ownership are not inferred.
Downloaded original tiles and their identities remain available for review.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='rock-review-mpl-'))
os.environ.setdefault('XDG_CACHE_HOME',tempfile.mkdtemp(prefix='rock-review-font-'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pyproj
from pyogrio.raw import read
import shapely
from shapely.ops import transform
from geometry_audit.common import parts


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    raw=args.output/'tiles';raw.mkdir()
    m,_,w,a=read(str(args.evidence/'source-ring-evidence.gpkg'),layer='evidence')
    attrs=dict(zip(m['fields'],a));geoms=shapely.from_wkb(w)
    by_id={}
    for cid,role,g in zip(attrs['candidate_id'],attrs['role'],geoms):by_id.setdefault(cid,{})[role]=g
    project=pyproj.Transformer.from_crs(6668,3857,always_xy=True).transform
    manifest=[]
    for cid,roles in by_id.items():
        hole=roles['source_hole'];parent=roles['source_feature'];p=hole.representative_point()
        z=18;n=2**z;x=int((p.x+180)/360*n);y=int((1-math.asinh(math.tan(math.radians(p.y)))/math.pi)/2*n)
        mosaics={}
        for kind,ext in [('std','png'),('seamlessphoto','jpg')]:
            mosaic=np.full((768,768,3),255,dtype=np.uint8)
            for dx in [-1,0,1]:
                for dy in [-1,0,1]:
                    tx,ty=x+dx,y+dy
                    url=f'https://cyberjapandata.gsi.go.jp/xyz/{kind}/{z}/{tx}/{ty}.{ext}'
                    file=raw/f'{kind}-{z}-{tx}-{ty}.{ext}'
                    if not file.exists():
                        r=subprocess.run(['curl','-fLsS','--retry','1','--max-time','45',url,'-o',str(file)],capture_output=True,text=True)
                        assert r.returncode==0,(url,r.stderr)
                    rgba=np.asarray(Image.open(file).convert('RGBA'));alpha=rgba[:,:,3:4]/255
                    rgb=(rgba[:,:,:3]*alpha+255*(1-alpha)).astype(np.uint8)
                    assert rgb.shape==(256,256,3)
                    mosaic[(dy+1)*256:(dy+2)*256,(dx+1)*256:(dx+2)*256]=rgb
                    manifest.append(dict(candidate_id=cid,layer=kind,url=url,
                        sha256=hashlib.file_digest(file.open('rb'),'sha256').hexdigest(),
                        downloaded_jst=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
                        acquisition_date='not established',attribution='地理院タイル（標準地図／全国最新写真）'))
            mosaics[kind]=mosaic
        half=math.pi*6378137.;step=2*half/n
        extent=[-half+(x-1)*step,-half+(x+2)*step,half-(y+2)*step,half-(y-1)*step]
        pm=transform(project,parent);hm=transform(project,hole)
        x0,y0,x1,y1=pm.bounds;pad=max(x1-x0,y1-y0)*.12
        assert extent[0]<=x0-pad and extent[1]>=x1+pad and extent[2]<=y0-pad and extent[3]>=y1+pad
        fig,axes=plt.subplots(1,3,figsize=(15,6),constrained_layout=True)
        for ax,kind,title in zip(axes,['std','seamlessphoto','seamlessphoto'],['GSI standard map (z18)','GSI aerial imagery (z18)','Aerial + N03 rings']):
            ax.imshow(mosaics[kind],extent=extent,origin='upper')
            ax.set_xlim(x0-pad,x1+pad);ax.set_ylim(y0-pad,y1+pad);ax.set_aspect('equal')
            ax.set_title(title);ax.ticklabel_format(useOffset=False)
            ax.set_xlabel('EPSG:3857 easting');ax.set_ylabel('EPSG:3857 northing')
        for poly in parts(pm):
            c=np.asarray(poly.exterior.coords);axes[2].plot(c[:,0],c[:,1],color='cyan',lw=1,label='N03 exterior')
        for poly in parts(hm):
            c=np.asarray(poly.exterior.coords);axes[2].plot(c[:,0],c[:,1],color='red',lw=1,label='N03 interior')
        axes[2].legend(loc='lower right',fontsize=8)
        fig.suptitle(f'{cid}  ({p.x:.9f}, {p.y:.9f})\n'
            'Source: GSI tiles (standard map / seamless photo). Imagery date and tide unknown.\n'
            'Red is the existing N03 hole; cyan is its parent exterior. No repair or coordinate shift.')
        fig.savefig(args.output/(cid+'-detail.png'),dpi=170);plt.close(fig)
    (args.output/'tile-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
