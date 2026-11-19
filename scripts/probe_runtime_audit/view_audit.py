"""Inspect and render unmodified published styles; make only a synthetic Processing seed."""
def run(ctx,args):
    from qgis.core import QgsCoordinateReferenceSystem,QgsRectangle,QgsVectorLayer,QgsFeature,QgsGeometry
    from qgis.PyQt.QtGui import QColor
    action=args['action']
    if action=='action_inventory':
        from qgis.PyQt.QtWidgets import QAction
        before=ctx.call('list_actions',window='QgisApp',text='Zoom',include_hidden=True)
        actions=ctx.iface.mainWindow().findChildren(QAction)
        zooms=[{'object_name':a.objectName(),'text':a.text(),'enabled':a.isEnabled()} for a in actions if 'zoom' in a.text().lower() or 'zoom' in a.objectName().lower()]
        after=ctx.call('list_actions',window='QgisApp',text='Zoom',include_hidden=True)
        return {'probe_before':before,'qt_zoom_actions':zooms,'qt_total_count':len(actions),'probe_with_qt_refs_held':after}
    if action=='window_state':
        return {'fullscreen':ctx.iface.mainWindow().isFullScreen()}
    if action=='seed':
        layer=QgsVectorLayer('Point?crs=EPSG:3857&field=name:string','buffer_seed','memory')
        f=QgsFeature(layer.fields());f['name']='synthetic';f.setGeometry(QgsGeometry.fromWkt('POINT(0 0)'))
        assert layer.dataProvider().addFeatures([f])[0]
        ctx.project.addMapLayer(layer)
        return {'id':layer.id()}
    layer=ctx.project.mapLayer(args['layer'])
    assert layer is not None
    canvas=ctx.iface.mapCanvas()
    if action=='resize_table':
        from qgis.PyQt.QtWidgets import QApplication
        matches=[w for w in QApplication.topLevelWidgets() if w.isVisible() and w.windowTitle()==args['title']]
        assert len(matches)==1
        matches[0].resize(1350,650)
        return {'title':matches[0].windowTitle()}
    if action=='table':
        view=ctx.iface.showAttributeTable(layer)
        view.resize(1350,650)
        return {'window':view.objectName(),'title':view.windowTitle()}
    if action=='labels':
        layer.setLabelsEnabled(args['enabled']);layer.triggerRepaint();canvas.refresh()
    if action=='show':
        root=ctx.project.layerTreeRoot()
        for lyr in ctx.project.mapLayers().values():
            node=root.findLayer(lyr.id())
            if node:node.setItemVisibilityChecked(lyr.id()==layer.id())
        canvas.setLayers([layer]);canvas.setDestinationCrs(layer.crs());canvas.setCanvasColor(QColor('white'))
        extent=layer.extent() if args['view']=='national' else QgsRectangle(135,33,141,38)
        extent.scale(1.08);canvas.setExtent(extent);canvas.refresh()
    if action=='area':
        return {'areas':[f.geometry().area() for f in layer.getFeatures()]}
    renderer=layer.renderer()
    labels=canvas.labelingResults()
    texts=[p.labelText for p in labels.allLabels() if p.layerID==layer.id()] if labels else []
    return {'layer':layer.id(),'count':layer.featureCount(),'crs':layer.crs().authid(),
            'renderer':renderer.type(),'category_field':renderer.classAttribute() if hasattr(renderer,'classAttribute') else None,
            'category_count':len(renderer.categories()) if hasattr(renderer,'categories') else None,
            'labels_enabled':layer.labelsEnabled(),'label_field':layer.labeling().settings().fieldName if layer.labeling() else None,
            'rendered_label_count':len(texts),'rendered_texts':sorted(set(texts)),
            'is_drawing':canvas.isDrawing(),'valid':layer.isValid()}
