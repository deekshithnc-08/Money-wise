"""Vercel Python function entrypoint. The database remains in Turso Cloud."""
import threading
from urllib.parse import parse_qs, urlparse
from server import Handler, init_db

_ready = False
_lock = threading.Lock()


class handler(Handler):
    def prepare(self):
        global _ready
        route = parse_qs(urlparse(self.path).query).get('route', [None])[0]
        if route is not None:
            self.path = '/' + route.lstrip('/')
        if not _ready:
            with _lock:
                if not _ready:
                    init_db()
                    _ready = True

    def do_GET(self):
        try:
            self.prepare()
        except Exception:
            self.send(503, {'error': 'The programme is being set up. Please try again shortly.'})
            return
        super().do_GET()

    def do_POST(self):
        try:
            self.prepare()
        except Exception:
            self.send(503, {'error': 'The programme is being set up. Please try again shortly.'})
            return
        super().do_POST()
