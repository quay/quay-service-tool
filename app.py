from flask import Flask, render_template

from tasks.banner import HelloWorld

app = Flask(__name__)


@app.route("/")
def main():
    return "Quay Service Tool Backend"

app.add_resource(HelloWorld, '/hello')


if __name__ == '__main__':
    app.run(debug=True)
