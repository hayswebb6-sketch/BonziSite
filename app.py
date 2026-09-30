import hashlib
import os

from flask import Flask, jsonify, render_template, request, send_from_directory

app=Flask(__name__)

DOWNLOAD_DIR=os.path.join(app.root_path, "downloads")

WINDOWS_ARTIFACT="bonzi_buddy_v2.zip"
MAC_ARTIFACT="bonzi_buddy_mac.zip"
VERSION_FILE=os.path.join(DOWNLOAD_DIR, "version.txt")

_artifact_cache={}

def app_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as handle:
            text=handle.read().strip()
        return text or None
    except OSError:
        return None

def artifact_digest(filename):
    """sha256 + size for a build artifact, computed once and cached."""
    cached=_artifact_cache.get(filename)
    if cached is not None:
        return cached

    path=os.path.join(DOWNLOAD_DIR, filename)
    try:
        size=os.path.getsize(path)
    except OSError:
        return None

    digest=hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    result={"sha256": digest.hexdigest(), "size": size}
    _artifact_cache[filename]=result
    return result

def absolute_url(endpoint):
    # request.url_root keeps the manifest correct behind any host or proxy.
    return request.url_root.rstrip("/") + "/" + endpoint.lstrip("/")

@app.after_request
def no_store_manifest(response):
    # An updater that reads a cached manifest will never notice a new build.
    if request.path in ("/version.json", "/version-mac.json"):
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
    return response

@app.route('/')
def bonzi():
    return render_template("index.html")

@app.route('/download')
def download():
    return send_from_directory("downloads", WINDOWS_ARTIFACT, as_attachment=True)

@app.route('/download-mac')
def download_mac():
    if not os.path.exists(os.path.join(DOWNLOAD_DIR, MAC_ARTIFACT)):
        return (
            "<h1>macOS build is not ready yet</h1>"
            "<p>Check back once the build has run. "
            "<a href='/'>Return to Bonzi Buddy</a></p>",
            404,
        )
    return send_from_directory("downloads", MAC_ARTIFACT, as_attachment=True)

def _manifest(filename, endpoint):
    version=app_version()
    if version is None:
        return jsonify({"error": "no release published yet"}), 503

    info=artifact_digest(filename)
    if info is None:
        return jsonify({"error": "no build available"}), 503
    return jsonify({
        "version": version,
        "url": absolute_url(endpoint),
        "sha256": info["sha256"],
        "size": info["size"],
    })

@app.route('/version.json')
def version_json():
    return _manifest(WINDOWS_ARTIFACT, "download")

@app.route('/version-mac.json')
def version_mac_json():
    return _manifest(MAC_ARTIFACT, "download-mac")

@app.route('/site.webmanifest')
def webmanifest():
    return jsonify({
        "name": "Bonzi Buddy",
        "short_name": "Bonzi",
        "description": "The greatest digital friend ever created.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1c1029",
        "theme_color": "#1c1029",
        "icons": [
            {"src": "/static/favicon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })

if __name__=="__main__":
    app.run(debug=False)
