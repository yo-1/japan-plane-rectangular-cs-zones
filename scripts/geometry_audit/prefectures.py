"""Complete all 47 prefectures, with durable per-prefecture caches.

Four independent processes at most. Original files and earlier partial outputs
remain unchanged. No snapping, buffering, simplification or area threshold.
Completed old rows are checked against regenerated results; missing geometry
outputs require regeneration of the original eight prefectures too.
"""
import argparse
import concurrent.futures
import json
import multiprocessing
import time
from pathlib import Path
import numpy as np
import pyogrio
import pyproj
import shapely
from .n03_io import groups
from .common import Audit,hashfile,area,parts

SG=PG=SF=PF=SI=PI=ST=PT=None

def initialize(source,prefecture):
    global SG,PG,SF,PF,SI,PI,ST,PT
    _,SF,SG,SI=groups(Path(source),False)
    _,PF,PG,PI=groups(Path(prefecture),True)
    assert set(SI)==set(PI)
    ST=shapely.STRtree(SG);PT=shapely.STRtree(PG)

def work(code,cache):
    started=time.time();directory=Path(cache)/code;directory.mkdir(exist_ok=True)
    expected=shapely.union_all(SG[SI[code]]);actual=shapely.union_all(PG[PI[code]])
    assert expected.is_valid and actual.is_valid
    exact=bool(shapely.equals_exact(expected,actual,0,normalize=True))
    lost=expected.difference(actual);added=actual.difference(expected)
    row=dict(stage='N03_municipality_to_N03_prefecture',key=code,normalized_exact=exact,
             lost_empty=bool(lost.is_empty),added_empty=bool(added.is_empty),lost_m2=area(lost),added_m2=area(added),
             expected_holes=sum(len(p.interiors) for p in parts(expected)),actual_holes=sum(len(p.interiors) for p in parts(actual)),
             prefecture=str(SF['N03_001'][SI[code][0]]),source_features=len(SI[code]),prefecture_features=len(PI[code]))
    samples=[];unavailable_samples=[]
    for direction,g in [('lost',lost),('added',added)]:
        if g.is_empty:continue
        for component in sorted((p for p in parts(g) if not p.is_empty),key=area,reverse=True)[:3]:
            p=component.representative_point()
            if p.is_empty:
                unavailable_samples.append(dict(code=code,direction=direction,component_m2=area(component),reason='Representative point is empty; entire difference geometry retained unchanged'))
                continue
            ss=[int(i) for i in ST.query(p) if SG[int(i)].covers(p)];ps=[int(i) for i in PT.query(p) if PG[int(i)].covers(p)]
            samples.append(dict(code=code,direction=direction,component_m2=area(component),longitude=p.x,latitude=p.y,
                source_union_covers=bool(expected.covers(p)),prefecture_union_covers=bool(actual.covers(p)),
                raw_source_municipality_codes=sorted({str(SF['N03_007'][i]) for i in ss}),
                raw_prefecture_codes=sorted({str(PF['N03_007'][i]) for i in ps})))
    geometry_files={}
    for name,g in [('source_union',expected),('prefecture_union',actual),('lost',lost),('added',added)]:
        p=directory/(name+'.wkb');p.write_bytes(shapely.to_wkb(g));geometry_files[p.name]=hashfile(p)
    result=dict(row=row,samples=samples,unavailable_samples=unavailable_samples,geometry_files=geometry_files,elapsed_seconds=time.time()-started)
    temp=directory/'result.json.partial';temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');temp.replace(directory/'result.json')
    return code

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-shp',type=Path,required=True);ap.add_argument('--prefecture-shp',type=Path,required=True);ap.add_argument('--prior-comparison',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
    assert 1<=args.workers<=4
    out=args.output.resolve()
    if out.exists() and any(out.iterdir()) and not (out/'input-context.json').exists():raise FileExistsError('Nonempty output directory has no audit context: '+str(out))
    out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
    start=time.time();prior=json.loads(args.prior_comparison.read_text()) if args.prior_comparison else [];prior_by={r['key']:r for r in prior}
    inputs=[dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashfile(p)) for path in [args.source_shp,args.prefecture_shp] for p in path.parent.glob(path.stem+'.*') if p.is_file()]
    versions=dict(shapely=shapely.__version__,geos=shapely.geos_version_string,pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version_string__,pyproj=pyproj.__version__,numpy=np.__version__)
    context=dict(inputs=inputs,versions=versions,auditor_code_sha256={name:hashfile(Path(__file__).parent/name) for name in ['prefectures.py','n03_io.py','common.py']},tolerance={'coordinate':0,'area_pass_threshold':None},mode='all comparisons force double-sided overlay; no rounding or repair')
    context_file=out/'input-context.json'
    if context_file.exists():assert json.loads(context_file.read_text())==context,'Input or runtime changed; use a new output directory'
    else:context_file.write_text(json.dumps(context,indent=2)+'\n')
    codes=[str(i).zfill(2)+'000' for i in range(1,48)]
    done=[]
    for code in codes:
        p=cache/code/'result.json'
        if p.exists():
            result=json.loads(p.read_text());assert result['row']['key']==code
            for name,h in result['geometry_files'].items():assert hashfile(p.parent/name)==h
            done.append(code)
    # Remaining 39 first; regenerate eight old results only for missing shapes.
    pending=[c for c in codes if c not in prior_by and c not in done]+[c for c in codes if c in prior_by and c not in done]
    completion=out/'completion.json'
    if len(done)==47 and completion.exists():
        record=json.loads(completion.read_text())
        assert record['input_context_sha256']==hashfile(context_file)
        for name,h in record['output_files'].items():assert hashfile(out/name)==h
        print('Verified complete cached audit: 47 prefectures',flush=True)
        return
    print('verified cached',len(done),'remaining',len(pending),'workers',args.workers,flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn'),initializer=initialize,initargs=(str(args.source_shp),str(args.prefecture_shp))) as pool:
        jobs={pool.submit(work,c,str(cache)):c for c in pending}
        for f in concurrent.futures.as_completed(jobs):
            c=f.result();done.append(c)
            progress=dict(completed=len(done),total=47,codes=sorted(done),elapsed_seconds=time.time()-start)
            (out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
            r=json.loads((cache/c/'result.json').read_text())['row']
            print('completed',len(done),'/47',c,r['prefecture'],'lost_m2',r['lost_m2'],'added_m2',r['added_m2'],'elapsed',round(time.time()-start),flush=True)
    assert set(done)==set(codes)
    audit=Audit(out);samples=[];baseline_changes=[];unavailable_samples=[]
    for code in codes:
        result=json.loads((cache/code/'result.json').read_text());row=result['row'];audit.rows.append(row);samples+=result['samples']
        unavailable_samples+=result.get('unavailable_samples',[])
        if code in prior_by:
            changes={k:dict(previous=prior_by[code][k],current=row[k]) for k in prior_by[code] if prior_by[code][k]!=row[k]}
            if changes:baseline_changes.append(dict(code=code,changes=changes))
        for direction in ['lost','added']:
            g=shapely.from_wkb((cache/code/(direction+'.wkb')).read_bytes())
            # WKB hashes above guarantee unchanged serialized coordinates;
            # reuse the already measured ellipsoidal area, rather than repeat it.
            audit.feature(g,dict(stage=row['stage'],key=code,direction=direction,area_m2=row[direction+'_m2']))
    summary=dict(status='completed',compared=47,source_count=pyogrio.read_info(str(args.source_shp))['features'],prefecture_count=pyogrio.read_info(str(args.prefecture_shp))['features'],source_prefectures=47,target_prefectures=47,source_crs='EPSG:6668',prefecture_crs='EPSG:6668',source_invalid=0,prefecture_invalid=0,
        normalized_exact=sum(r['normalized_exact'] for r in audit.rows),overlay_empty=sum(r['lost_empty'] and r['added_empty'] for r in audit.rows),
        different_codes=[r['key'] for r in audit.rows if not(r['lost_empty'] and r['added_empty'])],lost_m2=sum(r['lost_m2'] for r in audit.rows),added_m2=sum(r['added_m2'] for r in audit.rows),
        errors=0,unrun=0,uncompleted=0,interrupted_codes=[],prior_completed_rows_verified=len(prior_by),prior_result_changes=baseline_changes,inputs=inputs,versions=versions,tolerance=context['tolerance'],area_metric='GRS80 ellipsoidal area',workers=args.workers,elapsed_seconds=time.time()-start)
    audit.write(summary)
    (out/'representative-point-evidence.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n')
    (out/'unavailable-representative-points.json').write_text(json.dumps(unavailable_samples,ensure_ascii=False,indent=2)+'\n')
    assert not baseline_changes,'Regenerated completed results changed; investigate before readiness claim'
    output_names=['comparison.json','comparison.csv','holes.json','holes.csv','summary.json','differences.geojson','differences.gpkg','representative-point-evidence.json','unavailable-representative-points.json']
    (out/'completion.json').write_text(json.dumps(dict(input_context_sha256=hashfile(context_file),output_files={n:hashfile(out/n) for n in output_names}),indent=2)+'\n')
    print('SUMMARY',json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
