"""Las pruebas marcadas @pytest.mark.network llaman a EDGAR real.

Se saltan por defecto (no dependemos de internet para correr la suite) y se
activan con RUN_NETWORK_TESTS=1, por ejemplo para confirmar en CI de vez en
cuando que el acceso real sigue funcionando.
"""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_NETWORK_TESTS") == "1":
        return
    skip_network = pytest.mark.skip(reason="RUN_NETWORK_TESTS != 1 (prueba contra EDGAR real)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
