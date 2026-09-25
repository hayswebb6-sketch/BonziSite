from flask import Flask, render_template, send_from_directory

app=Flask(__name__)

@app.route('/')
def bonzi():
    return render_template("index.html")

@app.route('/download')
def download():
    return send_from_directory("downloads", "bonzi_buddy_v2.zip", as_attachment=True)

if __name__=="__main__":
    app.run(debug=False)
