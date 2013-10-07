#!/usr/bin/env python

from math import pi,sin,log,exp,atan
from flask import Flask, Response, redirect

import mapnik
import os

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

import sys
from tempfile import mkstemp
from threading import Lock
sys.path.append("..")
from upgrade_map_xml import upgrade

app = Flask(__name__)
app.debug = True
mapfile = "../osm.xml"
upgradedmapfile = None

m = None
prj = None
tileproj = None
render_size = 256
lock = Lock()

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

class ChangeEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        print ">>>>>>>>>>> modified:", event
        
        if isinstance(event, FileModifiedEvent) and "osm-live" not in event.src_path:
            load_map()


@app.route('/')
def home():
    return redirect('static/index.html')

def load_map():
    global m, prj, tileproj, render_size, upgradedmapfile
    
    lock.acquire()
    
    try:
        if not upgradedmapfile is None and os.path.exists(upgradedmapfile):
            os.unlink(upgradedmapfile)
        
        t = mkstemp('.xml', 'osm-live', os.path.dirname(mapfile))
        upgradedmapfile = t[1]
        
        upgrade(mapfile, upgradedmapfile, True)
        
        m = mapnik.Map(256, 256)
        
        # Load style XML
        mapnik.load_map(m, upgradedmapfile, True)
        
        # Cleaning up
        os.unlink(upgradedmapfile)
        upgradedmapfile = None
    
        m.resize(render_size, render_size)
    
        # Obtain <Map> projection
        prj = mapnik.Projection(m.srs)
        # Projects between tile pixel co-ordinates and LatLong (EPSG:4326)
        maxZoom = 18
        tileproj = GoogleProjection(maxZoom+1)
    finally:
        lock.release()
    
    return "Map reloaded"

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def generate_tile(z, x, y):
    global m, prj, tileproj, render_size
    
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
    
    output = None
    
    lock.acquire()
    
    try:
        m.zoom_to_box(bbox)
        
        # Render image with default Agg renderer
        im = mapnik.Image(render_size, render_size)
        mapnik.render(m, im)
        
        output = im.tostring('png')
    finally:
        lock.release()
    
    return Response(output, mimetype='image/png')

event_handler = ChangeEventHandler()
observer = Observer()
observer.schedule(event_handler, path=os.path.dirname(mapfile), recursive=False)
observer.start()

load_map()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
