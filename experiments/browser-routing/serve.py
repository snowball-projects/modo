"""Serve the browser-routing experiment with explicit static headers."""

from argparse import ArgumentParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, cors=False, **kwargs):
        self.cors = cors
        super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Timing-Allow-Origin", "*")
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()


def main():
    parser = ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cors", action="store_true")
    args = parser.parse_args()
    factory = partial(Handler, directory=args.directory, cors=args.cors)
    ThreadingHTTPServer(("127.0.0.1", args.port), factory).serve_forever()


if __name__ == "__main__":
    main()
