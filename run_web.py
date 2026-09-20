import argparse
import os
import sys
import uvicorn
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
def main() -> None:
    parser = argparse.ArgumentParser(description="Deep-Live-Cam local web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("web.app:app", host=args.host, port=args.port)
if __name__ == "__main__":
    main()
