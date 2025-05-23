# save as test_flask.py
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello from Raspberry Pi!"

app.run(host='0.0.0.0', port=5000)
