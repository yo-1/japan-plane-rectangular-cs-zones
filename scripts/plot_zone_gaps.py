"""Render representative audit voids in local metres; inputs stay read-only."""
import argparse
import csv
import os
import tempfile
from pathlib import Path

if 'MPLCONFIGDIR' not in os.environ:
    os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp(prefix='zone-gap-mpl-')
if 'XDG_CACHE_HOME' not in os.environ:
    os.environ['XDG_CACHE_HOME'] = tempfile.mkdtemp(prefix='zone-gap-font-cache-')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
import numpy as np
from pyogrio.raw import read
import pyproj
import shapely
from shapely.ops import transform, orient

from geometry_audit.common import parts
from audit_zone_gaps import read_layer


def patch(ax, g, project, color, alpha=.45):
    if g.geom_type == 'LineString':
        a = np.asarray(transform(project, g).coords)
        ax.plot(a[:, 0], a[:, 1], color=color, linewidth=1.5, alpha=alpha)
        return
    for polygon in parts(g):
        p = orient(transform(project, polygon), 1)
        vertices, codes = [], []
        for ring in [p.exterior, *p.interiors]:
            a = np.asarray(ring.coords)
            vertices.extend(a)
            codes.extend([MPath.MOVETO] + [MPath.LINETO]*(len(a)-2) + [MPath.CLOSEPOLY])
        ax.add_patch(PathPatch(MPath(vertices, codes), facecolor=color,
                               edgecolor=color, linewidth=.5, alpha=alpha))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audit', type=Path, required=True)
    ap.add_argument('--source-shp', type=Path, required=True)
    ap.add_argument('--municipalities', type=Path, required=True)
    ap.add_argument('--zones', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--exterior-screen', type=Path)
    ap.add_argument('--include-candidates', help='Comma-separated additional closed-void IDs to render')
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.audit/'candidates.csv').open() as f:
        rows = [r for r in csv.DictReader(f) if r['void_empty'] == 'False']
    chosen = []
    def pick(rs, key, reverse=True, n=2):
        for r in sorted(rs, key=key, reverse=reverse)[:n]:
            if r['candidate_id'] not in [x['candidate_id'] for x in chosen]: chosen.append(r)
    pick(rows, lambda r: float(r['area_m2']))
    pick([r for r in rows if float(r['area_m2']) >= 1], lambda r: float(r['obb_aspect']))
    pick([r for r in rows if r['context'] != '同一系内部'], lambda r: float(r['area_m2']), n=1)
    pick([r for r in rows if r['cause'] != '原典由来'], lambda r: float(r['area_m2']), n=2)
    if args.include_candidates:
        extra = set(args.include_candidates.split(','))
        assert extra.issubset({r['candidate_id'] for r in rows}), extra
        for r in rows:
            if r['candidate_id'] in extra and r['candidate_id'] not in {x['candidate_id'] for x in chosen}:
                chosen.append(r)
    source, _ = read_layer(args.source_shp)
    muni, _ = read_layer(args.municipalities)
    zones, _ = read_layer(args.zones)
    layers = [(source, shapely.STRtree(source)), (muni, shapely.STRtree(muni)), (zones, shapely.STRtree(zones))]
    meta, _, wkb, attrs = read(str(args.audit/'candidates.gpkg'), layer='void_candidates')
    fields = dict(zip(meta['fields'], attrs))
    by_id = dict(zip(fields['candidate_id'], shapely.from_wkb(wkb)))
    if args.exterior_screen:
        meta, _, wkb, attrs = read(str(args.exterior_screen/'exterior-screen.gpkg'), layer='connectors')
        ef = dict(zip(meta['fields'], attrs))
        eg = shapely.from_wkb(wkb)
        same = ef['zone_a'] == ef['zone_b']
        for mask in [same, ~same]:
            ids = np.flatnonzero(mask)
            if not len(ids): continue
            i = ids[np.argmax(ef['connector_width_m'][ids])]
            cid = str(ef['candidate_id'][i]);by_id[cid] = eg[i]
            chosen.append(dict(candidate_id=cid, zone=f"{ef['zone_a'][i]};{ef['zone_b'][i]}",
                cause='未確定', context=ef['context'][i], area_m2='',
                obb_length_m=float(ef['connector_width_m'][i]), obb_width_m='', kind='connector'))
    for r in chosen:
        cid = r['candidate_id'];g = by_id[cid];p = g.representative_point()
        crs = f'+proj=aeqd +lat_0={p.y} +lon_0={p.x} +ellps=GRS80 +units=m'
        proj = pyproj.Transformer.from_crs(6668, crs, always_xy=True)
        inv = pyproj.Transformer.from_crs(crs, 6668, always_xy=True)
        gm = transform(proj.transform, g)
        x0, y0, x1, y1 = gm.bounds
        span = max(x1-x0, y1-y0, .2);pad = span*.12
        window_m = shapely.box(x0-pad, y0-pad, x1+pad, y1+pad)
        window = transform(inv.transform, window_m)
        fig, axes = plt.subplots(1, 3, figsize=(15, 6), constrained_layout=True)
        for ax, (geoms, tree), title in zip(axes, layers, ['N03 original features', 'Municipalities v2026.2', '19 zones v2026.2']):
            ids = tree.query(window, predicate='intersects')
            for j, i in enumerate(ids):
                patch(ax, geoms[i].intersection(window), proj.transform, plt.cm.tab20(j%20))
            patch(ax, g, proj.transform, 'red', .75)
            ax.set_xlim(x0-pad, x1+pad);ax.set_ylim(y0-pad, y1+pad)
            ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('East (m)');ax.set_ylabel('North (m)')
            ax.ticklabel_format(useOffset=False)
        detail = (f"Exterior vertex connector: {r['obb_length_m']:.9g} m; no closed area defined"
                  if r.get('kind') == 'connector' else
                  f"area={float(r['area_m2']):.9g} m2; OBB={float(r['obb_length_m']):.7g} x {float(r['obb_width_m']):.7g} m")
        fig.suptitle(f"{cid}  zone={r['zone'] or r.get('adjacent_zones', '')}\n{detail}\n"
            'Red: audit void / connector. Stroke widths are symbolic; geometry is not buffered.')
        fig.savefig(args.output/(cid+'.png'), dpi=160)
        plt.close(fig)
    with (args.output/'index.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['candidate_id','zone','cause','context','area_m2','obb_length_m','obb_width_m'], lineterminator='\n')
        w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in chosen)


if __name__ == '__main__':
    main()
