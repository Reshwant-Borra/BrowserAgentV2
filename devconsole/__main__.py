"""`python -m devconsole [--port N]` -- launch the local Developer Console."""

import argparse

from .server import make_server

parser = argparse.ArgumentParser(prog="devconsole")
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()

server = make_server(args.port)
print(f"ComputerAgent Developer Console: http://127.0.0.1:{server.server_port}/  (Ctrl-C to stop)", flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
