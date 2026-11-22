# Doors

A financial twin that computes policies, not plans. Built for the UBS AI Financial Twin Challenge (LauzHack 2026).

This repository is being prepared for publication: the full README and the documentation arrive in the next commits.

The interface is in English by default; add `?lang=fr` to the address for French. The figures are the same in both languages.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests     # every test, including the cent-for-cent equality with the starter kit
.venv/bin/python -m api                            # then open http://127.0.0.1:8000/
```

See [DISCLAIMER.md](DISCLAIMER.md) and [NOTICE](NOTICE) for credits.
