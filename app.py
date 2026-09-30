import hashlib
import os
import zipfile

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for

app=Flask(__name__)

DOWNLOAD_DIR=os.path.join(app.root_path, "downloads")

# These names are what .github/workflows/build.yml publishes. Renaming one here
# without renaming it there turns every download into a 404, which is exactly
# what happened: the constants below used to say bonzi_buddy_v2.zip and
# bonzi_buddy_mac.zip, neither of which the workflow has ever produced.
WINDOWS_ARTIFACT="bonzi_buddy_1.21.zip"
MAC_ARTIFACTS={
    "x86_64": "bonzi_buddy_mac_x86_64.zip",
    "arm64": "bonzi_buddy_mac_arm64.zip",
}
# Apple Silicon still runs the Intel build under Rosetta 2, so it is the one the
# "Download for Mac" button hands out.
DEFAULT_MAC_ARCH="x86_64"

SHARE_IMAGE_SIZE=(1200, 630)

_artifact_cache={}
_version_cache={}


def artifact_path(filename):
    return os.path.join(DOWNLOAD_DIR, filename)


def artifact_ready(filename):
    return os.path.exists(artifact_path(filename))


def app_version(filename):
    """The version stamp lives inside the zip, next to the binary it describes.

    It used to be read from downloads/version.txt, which nothing writes: the
    publish job deliberately dropped that step, so the lookup always missed and
    the site answered 503 to every updater and every page load.
    """
    if filename in _version_cache:
        return _version_cache[filename]

    version=None
    try:
        with zipfile.ZipFile(artifact_path(filename)) as archive:
            with archive.open("version.txt") as handle:
                version=handle.read().decode("utf-8").strip() or None
    except (OSError, KeyError, zipfile.BadZipFile):
        version=None

    _version_cache[filename]=version
    return version


def artifact_digest(filename):
    """sha256 + size for a build artifact, computed once and cached."""
    cached=_artifact_cache.get(filename)
    if cached is not None:
        return cached

    try:
        size=os.path.getsize(artifact_path(filename))
    except OSError:
        return None

    digest=hashlib.sha256()
    with open(artifact_path(filename), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    result={"sha256": digest.hexdigest(), "size": size}
    _artifact_cache[filename]=result
    return result


def absolute_url(endpoint):
    # request.url_root keeps the manifest correct behind any host or proxy.
    return request.url_root.rstrip("/") + "/" + endpoint.lstrip("/")


def is_manifest_request():
    # An updater that reads a cached manifest will never notice a new build.
    path=request.path
    return path=="/version.json" or path=="/version-mac.json" or path.startswith("/version-mac/")


@app.after_request
def no_store_manifest(response):
    if is_manifest_request():
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
    return response


@app.route('/')
def bonzi():
    # The template reads version, structured and the three *_ready flags, and
    # never did so with a fallback. Rendering without them raised Undefined and
    # took the whole homepage down with a 500.
    version=app_version(WINDOWS_ARTIFACT)
    if version is None:
        version=app_version(MAC_ARTIFACTS[DEFAULT_MAC_ARCH])
    if version is None:
        version="-"

    windows_ready=artifact_ready(WINDOWS_ARTIFACT)
    mac_ready=artifact_ready(MAC_ARTIFACTS[DEFAULT_MAC_ARCH])
    mac_arm_ready=artifact_ready(MAC_ARTIFACTS["arm64"])

    canonical=request.url_root.rstrip("/") + "/"
    share_image=url_for("static", filename="og.png", _external=True)

    return render_template(
        "index.html",
        version=version,
        canonical=canonical,
        share_image=share_image,
        share_image_width=SHARE_IMAGE_SIZE[0],
        share_image_height=SHARE_IMAGE_SIZE[1],
        windows_ready=windows_ready,
        mac_ready=mac_ready,
        mac_arm_ready=mac_arm_ready,
        structured={
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": "Bonzi Buddy",
            "description": "The greatest digital friend ever created.",
            "url": canonical,
            "image": share_image,
            "applicationCategory": "UtilitiesApplication",
            "operatingSystem": "Windows, macOS",
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "softwareVersion": version,
        },
    )


def _missing_artifact(platform_label):
    return (
        f"<h1>{platform_label} build is not ready yet</h1>"
        "<p>Check back once the build has run. "
        "<a href='/'>Return to Bonzi Buddy</a></p>",
        404,
    )


@app.route('/download')
def download():
    if not artifact_ready(WINDOWS_ARTIFACT):
        return _missing_artifact("Windows")
    return send_from_directory("downloads", WINDOWS_ARTIFACT, as_attachment=True)


@app.route('/download-mac')
def download_mac():
    return download_mac_arch(DEFAULT_MAC_ARCH)


@app.route('/download-mac/<arch>')
def download_mac_arch(arch):
    # Rejecting the arch outright rather than interpolating it keeps a request
    # for /download-mac/../../something from reaching the filesystem.
    filename=MAC_ARTIFACTS.get(arch)
    if filename is None:
        return _missing_artifact("macOS")
    if not artifact_ready(filename):
        return _missing_artifact("macOS")
    return send_from_directory("downloads", filename, as_attachment=True)


def _manifest(filename, endpoint):
    version=app_version(filename)
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
    return _manifest(MAC_ARTIFACTS[DEFAULT_MAC_ARCH], "download-mac")


# The desktop app's updater asks per architecture, because one build cannot
# serve both. The site JS reads the flat /version-mac.json above.
@app.route('/version-mac/<arch>.json')
def version_mac_arch_json(arch):
    filename=MAC_ARTIFACTS.get(arch)
    if filename is None:
        return jsonify({"error": "unknown architecture"}), 404
    return _manifest(filename, f"download-mac/{arch}")


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
            # The 192px icon is icon-192.png. Nothing here is ever named
            # favicon-192.png, so the old manifest pointed at a 404.
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


if __name__=="__main__":
    app.run(debug=False)
