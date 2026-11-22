"""Lance Doors : `python -m api`, puis ouvrir http://127.0.0.1:8000/"""
import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Doors : les routes de calcul et l'interface, sur un seul serveur")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Doors : http://{args.host}:{args.port}/   (Ctrl+C pour arrêter)")
    uvicorn.run("api.main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
