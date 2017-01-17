#!/usr/bin/env python

from gevent import monkey
monkey.patch_all()  # Patch everything
import gevent
import gevent.subprocess
import time
import shutil
import os
from threading import Lock
import json
import redis

queueSetKey = "image-dreamer-queued-set"
queueMessageKey = "image-dreamer-queue-new-image"
processingPath = os.path.join(os.getcwd(), "processing")
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
CONVERTED_FOLDER = os.path.join(os.getcwd(), 'static', 'converted')

class Hub(object):
    """A simple reactor hub... In async!"""

    def __init__(self, name=None):
        self.name = name
        self.handlers = {}

    def on(self, event_name, handler):
        """Binds an event to a function."""
        handlers = self.handlers.get(event_name, [])
        if not handler in handlers:
            handlers.append(handler)
            self.handlers[event_name] = handlers

    def off(self, event_name, handler):
        """Unbinds an event to a function."""
        handlers = self.handlers.get(event_name, [])
        handlers.remove(handler)

    def emit(self, event_name, *args, **kwargs):
        """Calls an event. You can also pass arguments."""
        handlers = self.handlers.get(event_name, [])
        for handler in handlers:
            # XXX: If spawned within a greenlet, there's no need to join
            # the greenlet. It is automatically executed.
            gevent.spawn(handler, *args, **kwargs)

    def start(self, *entry_points):
        """Run entry point."""
        gevent.joinall([gevent.spawn(ep) for ep in entry_points])

# Create an instance of the hub.
hub = Hub(name='myhub')
# Create a redis instance
r = redis.Redis()
lock = Lock()

def InsertZeroIntoFileName(name):
    return "{}_{}.jpg".format(name, 0)

def processImageQueue(string):
    if not lock.acquire(False):
        print "Processing run in progress!"
        return
    else:
        try:
            while len(r.smembers(queueSetKey)) > 0:
                imageName = r.spop(queueSetKey)
                print "Running on:", imageName
                imageState = json.loads(r.get(imageName))
                imageState["ProcessingState"] = "Processing"
                r.set(imageName, json.dumps(imageState))
                shutil.copyfile(os.path.join(UPLOAD_FOLDER, imageName), os.path.join(processingPath, imageName))
                gevent.subprocess.check_call(["python", "./deepdreamer/deepdreamer.py", "--layers", "inception_3a/3x3", "--dreams", "1", os.path.join("./processing", imageName)])
                shutil.copyfile(os.path.join(processingPath, InsertZeroIntoFileName(imageName)), os.path.join(CONVERTED_FOLDER, imageName))
                imageState["ProcessingState"] = "Done"
                r.set(imageName, json.dumps(imageState))
        finally:
            lock.release()

hub.on('new.image', processImageQueue)

def entry_point():
    ps = r.pubsub()
    ps.subscribe([queueMessageKey])
    for message in ps.listen():
        if message['type'] == 'message':
            hub.emit('new.image', "")

if __name__ == '__main__':
    hub.start(entry_point)
