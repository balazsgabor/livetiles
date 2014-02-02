#!/usr/bin/env python

import mapnik
import os
import math

from flask import Flask, Response, redirect
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Lock

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
            map_file = os.path.basename(self.mapfile)
            self.map = mapnik.Map(256, 256)
            
            mapnik.load_map(self.map, map_file, False)
            self.map.resize(self.render_size, self.render_size)
        except Exception as e:
            self.load_exception = e
        finally:
            self.lock.release()
    
    def num2deg(self, xtile, ytile, zoom):
        n = 2.0 ** zoom
        lon_deg = xtile / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
        lat_deg = math.degrees(lat_rad)
        return (lon_deg, lat_deg)

    def generate_tile(self, z, x, y):
        self.lock.acquire()
        
        resp = "general error"
        
        try:
            if self.load_exception is None:
                # Convert to LatLong (EPSG:4326)
                l0 = self.num2deg(x, y, z)
                l1 = self.num2deg(x + 1, y + 1, z)
                
                # Convert to map projection (e.g. mercator co-ords EPSG:900913)
                prj = mapnik.Projection(self.map.srs)
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

class LivetilesApp():
    try:
        mapfile = os.environ['MAPNIK_MAP_FILE']
    except KeyError:
        mapfile = "osm.xml"
        
    print "using mapfile", mapfile
        
    livetiles = Livetiles(mapfile, 256)
    event_handler = ChangeEventHandler(livetiles)
    observer = Observer()
    
    # go live
    directory = os.path.dirname(mapfile)
    observer.schedule(event_handler, path=directory, recursive=True)
    os.chdir(directory)
    livetiles.load_map()
    observer.start()

app = Flask(__name__)
app.debug = True
lt = LivetilesApp()

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def render_tile(z, x, y):
    return lt.livetiles.generate_tile(z, x, y)

@app.route('/')
def home():
    return redirect('static/index.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
    
