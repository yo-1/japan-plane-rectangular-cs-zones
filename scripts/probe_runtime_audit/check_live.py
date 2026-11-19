"""Live MCP tests against QGIS 3.44.13 and the unchanged probe 0.1.4."""
import asyncio,base64,json,math,os
from pathlib import Path
import sys
from mcp import Client,StdioServerParameters
ROOT=Path('/work');OUT=ROOT/'results';REPORT={'calls':[],'layers':{}}

def save():
    (OUT/'mcp-results.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2)+'\n')

def classify_inventory(inventory):
    expected={a['object_name'] for a in inventory['qt_zoom_actions'] if a['object_name']=='mActionZoomFullExtent'}
    observed={a['object_name'] for a in inventory['probe_before']['actions']}
    return bool(expected) and expected <= observed

async def main():
    params=StdioServerParameters(command=sys.executable,args=['-m','qgis_dev_probe_mcp.server'],env=dict(os.environ))
    async with Client(params) as client:
        async def call(name,args=None,expect_error=False,image_name=None):
            response=await client.call_tool(name,args or {})
            text=[b.text for b in response.content if b.type=='text']
            item={'tool':name,'arguments':args or {},'is_error':response.is_error,'text':text}
            for b in response.content:
                if b.type=='image':
                    path=OUT/(image_name or f'capture-{len(REPORT["calls"])}.png')
                    path.write_bytes(base64.b64decode(b.data));item['image']=path.name
            REPORT['calls'].append(item);save()
            print(name,'expected-denial' if expect_error else 'OK' if not response.is_error else 'FAIL',flush=True)
            assert response.is_error==expect_error,item
            if expect_error:
                assert 'policy_denied' in '\n'.join(text),item
                return text
            try:return json.loads(text[0])
            except (ValueError,IndexError):return text
        ping=await call('ping');assert ping['plugin_version']=='0.1.4' and ping['mode']=='interactive'
        info=await call('get_info');assert info['qgis_version_int']==34413;REPORT['info']=info
        REPORT['exec_permission']='Enabled only for this isolated session to run the trusted local view_audit recipe; denial verified separately'
        save()
        await call('list_algorithms',{'search':'buffer'})
        await call('get_algorithm_params',{'algorithm_id':'native:buffer'})
        manifest=json.loads((ROOT/'input-manifest.json').read_text())
        for kind,count in [('zones',19),('prefectures',392),('municipalities',1911)]:
            path=ROOT/'data'/manifest[kind]['gpkg_name'];table=manifest[kind]['layers'][0][0]
            layer=await call('add_layer',{'path':str(path)+'|layername='+table,'name':kind,'kind':'vector'})
            ident=layer['id'];assert layer['valid'] and layer['crs']=='EPSG:6668'
            inspected=await call('inspect_layer',{'layer':ident,'sample':2});assert inspected['feature_count']==count
            fields={f['name'] for f in inspected['fields']};assert fields==set(manifest[kind]['fields']),fields
            REPORT['layers'][kind]={'id':ident,'inspection':inspected,'views':{}}
            if kind=='zones':
                REPORT['action_inventory']=await call('run_recipe',{'name':'view_audit','args':{'action':'action_inventory'}})
                save()
            for view in ['national','regional']:
                await call('run_recipe',{'name':'view_audit','args':{'action':'show','layer':ident,'view':view}})
                for _ in range(100):
                    await asyncio.sleep(.3)
                    rendered=await call('run_recipe',{'name':'view_audit','args':{'action':'inspect','layer':ident}})
                    if not rendered['is_drawing']:break
                else:raise RuntimeError('Rendering did not finish')
                assert rendered['renderer']=='categorizedSymbol' and rendered['category_field']=='ZONE_ROMAN'
                assert rendered['labels_enabled']==manifest[kind]['style_labels_enabled'] and rendered['label_field']=='ZONE_ROMAN'
                assert (rendered['rendered_label_count']>0)==manifest[kind]['style_labels_enabled'],rendered
                REPORT['layers'][kind]['views'][view]=rendered;save()
                await call('screenshot',{},image_name=f'{kind}-{view}.png')
            if kind=='municipalities':
                await call('run_recipe',{'name':'view_audit','args':{'action':'labels','layer':ident,'enabled':True}})
                for _ in range(100):
                    await asyncio.sleep(.3)
                    rendered=await call('run_recipe',{'name':'view_audit','args':{'action':'inspect','layer':ident}})
                    if not rendered['is_drawing']:break
                assert rendered['rendered_label_count']>0,rendered
                REPORT['layers'][kind]['temporary_label_preview']=rendered
                await call('screenshot',{},image_name='municipalities-labels-temporary.png')
                await call('run_recipe',{'name':'view_audit','args':{'action':'labels','layer':ident,'enabled':False}})
            await call('run_recipe',{'name':'view_audit','args':{'action':'table','layer':ident}})
            await asyncio.sleep(.4)
            windows=await call('list_windows')
            tables=[w for w in windows['windows'] if kind in w['title'] and 'Features Total:' in w['title']]
            assert len(tables)==1,windows
            title=tables[0]['title']
            await call('run_recipe',{'name':'view_audit','args':{'action':'resize_table','title':title,'layer':ident}})
            await asyncio.sleep(.3)
            await call('screenshot',{'window':title},image_name=f'{kind}-attributes.png')
            await call('close_window',{'window':title});await asyncio.sleep(.2)
        seed=await call('run_recipe',{'name':'view_audit','args':{'action':'seed'}})
        buffer=await call('run_algorithm',{'algorithm_id':'native:buffer','parameters':{'INPUT':seed['id'],'DISTANCE':10,'SEGMENTS':8,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':False,'OUTPUT':'/work/results/buffer.gpkg'},'timeout_s':60})
        b=await call('add_layer',{'path':buffer['results']['OUTPUT'],'name':'buffer_result','kind':'vector'})
        bi=await call('inspect_layer',{'layer':b['id']});assert bi['feature_count']==1 and bi['crs']=='EPSG:3857'
        area=await call('run_recipe',{'name':'view_audit','args':{'action':'area','layer':b['id']}})
        assert len(area['areas'])==1 and abs(area['areas'][0]-math.pi*100)/(math.pi*100)<.02,area
        REPORT['buffer']={'result':buffer,'area_m2':area['areas'][0]}
        await call('remove_layer',{'layer':b['id']});await call('remove_layer',{'layer':seed['id']})
        validity_params=await call('get_algorithm_params',{'algorithm_id':'qgis:checkvalidity'})
        REPORT['validity_parameters']=validity_params;save()
        v=await call('run_algorithm',{'algorithm_id':'qgis:checkvalidity','parameters':{'INPUT_LAYER':REPORT['layers']['zones']['id'],'METHOD':2,'IGNORE_RING_SELF_INTERSECTION':False,'VALID_OUTPUT':'/work/results/zones-valid.gpkg','INVALID_OUTPUT':'/work/results/zones-invalid.gpkg','ERROR_OUTPUT':'/work/results/zones-errors.gpkg'},'timeout_s':600})
        REPORT['validity']=v;save()
        assert v['results']['VALID_COUNT']==19 and v['results']['INVALID_COUNT']==0 and v['results']['ERROR_COUNT']==0,v
        remaining=await call('list_layers');assert remaining['count']==3,remaining
        REPORT['display_processing_complete']=True
        REPORT['action_enumeration_passed']=classify_inventory(REPORT['action_inventory'])
        REPORT['overall_status']='passed' if REPORT['action_enumeration_passed'] else 'partial_failure'
        save()
        print('DISPLAY/PROCESSING COMPLETE; overall='+REPORT['overall_status'],flush=True)
        if not REPORT['action_enumeration_passed']:
            raise RuntimeError('Known probe action-enumeration failure recorded; see mcp-results.json')

if __name__=='__main__':
    asyncio.run(main())
