#!/usr/bin/env python

from math import pi,sin,log,exp,atan
from flask import Flask, Response, redirect

import sys
sys.path.append("..")
from upgrade_map_xml import upgrade

import mapnik

DEG_TO_RAD = pi/180
RAD_TO_DEG = 180/pi

class GoogleProjection:
    def __init__(self,levels=18):
        self.Bc = []
        self.Cc = []
        self.zc = []
        self.Ac = []
        c = 256
        for _ in range(0,levels):
            e = c/2;
            self.Bc.append(c/360.0)
            self.Cc.append(c/(2 * pi))
            self.zc.append((e,e))
            self.Ac.append(c)
            c *= 2

    def fromLLtoPixel(self,ll,zoom):
        d = self.zc[zoom]
        e = round(d[0] + ll[0] * self.Bc[zoom])
        f = minmax(sin(DEG_TO_RAD * ll[1]),-0.9999,0.9999)
        g = round(d[1] + 0.5*log((1+f)/(1-f))*-self.Cc[zoom])
        return (e,g)
    
    def fromPixelToLL(self,px,zoom):
        e = self.zc[zoom]
        f = (px[0] - e[0])/self.Bc[zoom]
        g = (px[1] - e[1])/-self.Cc[zoom]
        h = RAD_TO_DEG * ( 2 * atan(exp(g)) - 0.5 * pi)
        return (f,h)




app = Flask(__name__)
app.debug = True
mapfile = "../osm.xml"
newmapfile = "../osm-live.xml"

m = None
prj = None
tileproj = None

@app.route('/')
def home():
    return redirect('static/index.html')

@app.route('/reload')
def load_map():
    global m, prj, tileproj
    
    print "upgrading", mapfile
    
    upgrade(mapfile, newmapfile, True)
    
    print "loading map"
    m = mapnik.Map(256, 256)
    
    # Load style XML
    mapnik.load_map(m, newmapfile, True)
    # Obtain <Map> projection
    prj = mapnik.Projection(m.srs)
    # Projects between tile pixel co-ordinates and LatLong (EPSG:4326)
    maxZoom = 18
    tileproj = GoogleProjection(maxZoom+1)	
    
    return "Map reloaded"

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def generate_tile(z, x, y):
    global m, prj, tileproj
    
    # Calculate pixel positions of bottom-left & top-right
    p0 = (x * 256, (y + 1) * 256)
    p1 = ((x + 1) * 256, y * 256)
    
    # Convert to LatLong (EPSG:4326)
    l0 = tileproj.fromPixelToLL(p0, z);
    l1 = tileproj.fromPixelToLL(p1, z);
    
    # Convert to map projection (e.g. mercator co-ords EPSG:900913)
    c0 = prj.forward(mapnik.Coord(l0[0],l0[1]))
    c1 = prj.forward(mapnik.Coord(l1[0],l1[1]))
    
    # Bounding box for the tile
    bbox = mapnik.Envelope(c0.x,c0.y, c1.x,c1.y)
    render_size = 256
    
    m.resize(render_size, render_size)
    m.zoom_to_box(bbox)
    
    # Render image with default Agg renderer
    im = mapnik.Image(render_size, render_size)
    mapnik.render(m, im)
    
    output = im.tostring('png')
    
    return Response(output, mimetype='image/png')


load_map()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
