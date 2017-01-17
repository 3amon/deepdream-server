from flask import Flask, jsonify, render_template, request
from os import walk, getcwd, path
from itertools import izip_longest
from werkzeug import secure_filename
import json
import redis
from PIL import Image

app = Flask(__name__)

UPLOAD_FOLDER = path.join(getcwd(), 'static', 'uploads')
CONVERTED_FOLDER = path.join(getcwd(), 'static', 'converted')
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
queueSetKey = "image-dreamer-queued-set"
queueMessageKey = "image-dreamer-queue-new-image"
listSetKey = "image-dreamer-image-set"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

r = redis.Redis()

def chunks(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/processing-status')
def getProcessingState():
    results = []
    for (dirpath, dirnames, filenames) in walk('static/uploads'):
        for name in filenames:
            state = "Unknown"
            imgString = r.get(name)
            if imgString:
                imageState = json.loads(imgString)
                state = imageState["ProcessingState"]
            results.append({ "name" : name,
                             "state" : state})

    return json.dumps(results)


@app.route('/upload', methods=["POST"])
def upload():
    uploaded_files = request.files.getlist("files[]")
    for file in uploaded_files:
        if file and allowed_file(file.filename):
            size = 512,512
        try:

            # downsize
            im = Image.open(file.stream)
            im.thumbnail(size, Image.ANTIALIAS)
            sec_filename = secure_filename(file.filename)
            im.save(path.join(app.config['UPLOAD_FOLDER'], sec_filename), "JPEG")

            
            # write to the redis
            imageState = {};
            imageState["name"] = sec_filename;
            imageState["origionalName"] = file.filename;
            imageState["ProcessingState"] = "Queued";

            r.set(imageState["name"], json.dumps(imageState))
            r.sadd(queueSetKey, imageState["name"])
            r.sadd(listSetKey, imageState["name"])
            r.publish(queueMessageKey, "")

        except IOError:
            print "cannot create thumbnail for '%s'" % infile

    return ""

@app.route('/')
def index():
    pictureGrid = []
    for (dirpath, dirnames, filenames) in walk('static/uploads'):
        for row in chunks(filenames, 2):
            pictureRow = []
            for name in row:
                if name:
                    description = "Unknown"
                    imgString = r.get(name)

                    if imgString:
                        imageState = json.loads(imgString)
                        description = imageState["ProcessingState"]

                    linkData = {
                        'convertedPath' : 'static/converted/' + name,
                        'origionalPath' : 'static/uploads/' + name,
                        'filename' : name,
                        'description' : description
                    }
                    pictureRow.append(linkData)

            pictureGrid.append(pictureRow)

    return render_template("index.template", pictureGrid=pictureGrid)

if __name__ == '__main__':
    app.run(port=8000, debug=True)