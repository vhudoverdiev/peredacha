import time

from app import create_app


class SlowUncachedDesktopStyles:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        is_desktop_css = environ.get("PATH_INFO") in {
            "/static/style.css",
            "/static/desktop-only.css",
        }
        if is_desktop_css:
            time.sleep(0.65)

        def no_store_start_response(status, headers, exc_info=None):
            if is_desktop_css:
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() not in {"cache-control", "expires", "etag"}
                ]
                headers.append(("Cache-Control", "no-store"))
            return start_response(status, headers, exc_info)

        return self.app(environ, no_store_start_response)


app = create_app()
app.wsgi_app = SlowUncachedDesktopStyles(app.wsgi_app)
app.run(port=5034, debug=False, threaded=True)
