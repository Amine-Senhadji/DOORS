"""No test calls the model. This module is imported first by every test module that touches the AI layer or the API.

- It forces the recorded mode, whatever the terminal the tests are run from: with a key exported there, a test could
  otherwise send a real request and spend real money.
- It replaces the one function that builds the SDK's client by one that fails. A test that reaches it fails, loudly.

A test that needs the SDK itself gives `Live` a client of its own, with a transport that answers on this machine.
"""
from __future__ import annotations

import os

from ai import model

os.environ["DOORS_AI"] = "recorded"


def forbidden():
    raise AssertionError("A test tried to build the SDK's client. No test may call the model: give `Live` a local client, or a scripted model.")


model.build_client = forbidden
model.Live._shared = None
