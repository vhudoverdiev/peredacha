import time

from app import create_app


class SlowDesktopStyles:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") in {
            "/static/style.css",
            "/static/desktop-only.css",
        }:
            time.sleep(1.5)
        return self.app(environ, start_response)


app = create_app()
app.wsgi_app = SlowDesktopStyles(app.wsgi_app)
app.run(port=5032, debug=False, threaded=True)
