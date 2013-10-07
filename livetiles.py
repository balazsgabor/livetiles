#!/usr/bin/env python

import sys
sys.path.insert(0, "..")

import mapnik
import os

from math import pi,sin,log,exp,atan
from flask import Flask, Response, redirect
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
from tempfile import mkstemp
from threading import Lock
from upgrade_map_xml import upgrade

RAD_TO_DEG = 180/pi
DEG_TO_RAD = pi/180

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
    def __init__(self, livetiles):
        self.livetiles = livetiles
        
    def on_any_event(self, event):
        print ">>>>> modified:", event
        self.livetiles.load_map()

class Livetiles():
    def __init__(self, mapfile, render_size):
        self.mapfile = mapfile
        self.render_size = render_size
        
        self.load_exception = None
        self.lock = Lock()
        
    def load_map(self):
        self.lock.acquire()
        
        self.map = None
        self.load_exception = None
        
        try:
            map_string = upgrade(os.path.basename(self.mapfile), None, False, True)
            self.map = mapnik.Map(256, 256)
            
            mapnik.load_map_from_string(self.map, map_string, True)
            self.map.resize(self.render_size, self.render_size)
        except Exception as e:
            self.load_exception = e
        finally:
            self.lock.release()

    def generate_tile(self, z, x, y):
        self.lock.acquire()
        
        resp = "general error"
        
        try:
            if self.load_exception is None:
                prj = mapnik.Projection(self.map.srs)
                # Projects between tile pixel co-ordinates and LatLong (EPSG:4326)
                maxZoom = 18
                tileproj = GoogleProjection(maxZoom+1)
                
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
                
                self.map.zoom_to_box(bbox)
            
                # Render image with default Agg renderer
                im = mapnik.Image(self.render_size, self.render_size)
                mapnik.render(self.map, im)
            
                output = im.tostring('png')
                resp = Response(output, mimetype='image/png')

            else:
                resp = self.load_exception.message
        except Exception as e:
            resp = e.message
        finally:
            self.lock.release()
        
        return resp

# init
map_file = "../osm.xml"
livetiles = Livetiles(map_file, 256)
event_handler = ChangeEventHandler(livetiles)
observer = Observer()

# go live
dir = os.path.dirname(map_file)
observer.schedule(event_handler, path=dir, recursive=True)
os.chdir(dir)
livetiles.load_map()
observer.start()

app = Flask(__name__)
app.debug = True

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def render_tile(z, x, y):
    return livetiles.generate_tile(z, x, y)

@app.route('/')
def home():
    return redirect('static/index.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
