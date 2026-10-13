"""Read source polygons without writing to them."""
import collections
import shapely,pyproj
from pyogrio.raw import read
def groups(path,prefecture):
    m,_,w,a=read(str(path));assert pyproj.CRS(m['crs'])==pyproj.CRS.from_epsg(6668)
    f=dict(zip(m['fields'],a));g=shapely.from_wkb(w)
    assert bool(shapely.is_valid(g).all()) and not bool(shapely.is_empty(g).any())
    groups=collections.defaultdict(list)
    for i,c in enumerate(f['N03_007']):groups[str(c) if prefecture else str(c)[:2]+'000'].append(i)
    assert len(groups)==47
    return m,f,g,groups
