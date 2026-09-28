import hashlib
import os
import zipfile

from flask import Flask, jsonify, render_template, request, send_from_directory

app=Flask(__name__)

DOWNLOAD_DIR=os.path.join(app.root_path, "downloads")

WINDOWS_ARTIFACT="bonzi_buddy_v2.zip"

# Mac is published as two builds, because a Mac is not one thing. The Intel
# build is the default: Apple Silicon still runs it under Rosetta 2, so a
# single link covers every machine, and the native arm64 one is there for
# people who would rather not pay the translation.
MAC_ARTIFACTS={
    "x86_64": "bonzi_buddy_mac_x86_64.zip",
    "arm64": "bonzi_buddy_mac_arm64.zip",
}
MAC_DEFAULT_ARCH="x86_64"

# The version is stored *inside* each artifact, not beside it. An earlier
# design read downloads/version.txt, which only CI ever wrote, so one dead
# publish job meant every manifest 503'd and self-update silently did nothing
# forever. Putting the stamp in the zip makes the number and the binary the
# same file: it is impossible to advertise a version that does not match the
# build, and the manifest works with or without CI.
VERSION_MEMBER="version.txt"

_artifact_cache={}
_version_cache={}

def artifact_version(filename):
    """Read the version stamp from inside the artifact zip.

    Returns None when the artifact carries no stamp, which means "do not
    advertise this build". Guessing from the source tree instead would let a
    fresh APP_VERSION sit next to a stale binary, so an older install would
    download an older build and stamp itself backwards into a loop.
    """
    if filename in _version_cache:
        return _version_cache[filename]

    path=os.path.join(DOWNLOAD_DIR, filename)
    version=None
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if os.path.basename(name)!=VERSION_MEMBER:
                    continue
                version=archive.read(name).decode("utf-8", "replace").strip() or None
                break
    except (OSError, zipfile.BadZipFile, KeyError):
        version=None

    _version_cache[filename]=version
    return version

def artifact_available(filename):
    return os.path.isfile(os.path.join(DOWNLOAD_DIR, filename))

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
    # The manifest URL has to come back as https, because the app refuses to
    # update over plain http. Render terminates TLS and forwards with
    # X-Forwarded-Proto, but nothing here applies ProxyFix, so request.url_root
    # can report http even though the browser is on https. Trusting url_root
    # alone therefore disables self-update in production while every local test
    # passes, so the forwarded headers are read directly.
    proto=(request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    host=(request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip()
    if proto not in ("http", "https"):
        proto="https"
    return f"{proto}://{host}".rstrip("/") + "/" + endpoint.lstrip("/")

def not_ready(what):
    # 503, not 404: nothing is wrong with the link, the build just has not
    # landed yet, and it is worth retrying. A 404 read as "this will never
    # exist", which is how the missing macOS artifact went unnoticed.
    return (
        f"<h1>{what} is not ready yet</h1>"
        "<p>No stamped build of this kind has been published yet. "
        "<a href='/'>Return to Bonzi Buddy</a></p>",
        503,
    )

def mac_endpoint(arch):
    return "download-mac" if arch==MAC_DEFAULT_ARCH else f"download-mac/{arch}"

@app.after_request
def no_store_manifest(response):
    # An updater that reads a cached manifest will never notice a new build.
    if request.path=="/version.json" or request.path.startswith("/version-mac"):
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
    return response

@app.route('/')
def bonzi():
    return render_template(
        "index.html",
        windows_ready=artifact_available(WINDOWS_ARTIFACT),
        mac_ready=any(artifact_available(name) for name in MAC_ARTIFACTS.values()),
        mac_arm_ready=artifact_available(MAC_ARTIFACTS["arm64"]),
        # Read from the published artifact rather than hardcoded, so the page
        # cannot claim a version the download does not actually have.
        version=artifact_version(WINDOWS_ARTIFACT) or "unpublished",
    )

@app.route('/download')
def download():
    if not artifact_available(WINDOWS_ARTIFACT):
        return not_ready("The Windows build")
    return send_from_directory(DOWNLOAD_DIR, WINDOWS_ARTIFACT, as_attachment=True)

def _download_mac(arch):
    if arch not in MAC_ARTIFACTS:
        return "Unknown macOS architecture. Try /download-mac.", 404
    filename=MAC_ARTIFACTS[arch]
    if not artifact_available(filename):
        return not_ready("The macOS build")
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

@app.route('/download-mac')
def download_mac():
    return _download_mac(MAC_DEFAULT_ARCH)

@app.route('/download-mac/<arch>')
def download_mac_arch(arch):
    return _download_mac(arch)

def _manifest(filename, endpoint):
    info=artifact_digest(filename)
    if info is None:
        return jsonify({"error": "no build available"}), 503

    version=artifact_version(filename)
    if version is None:
        # The artifact is real but carries no version stamp, so there is no
        # honest way to answer "is this newer?". Saying so beats inventing a
        # number, which is what made this endpoint lie before.
        return jsonify({
            "error": "build carries no version stamp",
            "artifact": filename,
        }), 503

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
    # No arch in the path means the default build, same as /download-mac.
    return _manifest(MAC_ARTIFACTS[MAC_DEFAULT_ARCH], mac_endpoint(MAC_DEFAULT_ARCH))

@app.route('/version-mac/<arch>.json')
def version_mac_arch_json(arch):
    if arch not in MAC_ARTIFACTS:
        return jsonify({"error": "unknown architecture"}), 404
    return _manifest(MAC_ARTIFACTS[arch], mac_endpoint(arch))

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
