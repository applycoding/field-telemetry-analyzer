# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from field_telemetry_analyzer.generate import generate

SEED = 20261110


@pytest.fixture(scope="session")
def standard_log():
    log, events = generate("standard", SEED)
    return log, events


@pytest.fixture(scope="session")
def clean_log():
    log, events = generate("clean", SEED)
    return log, events
