import importlib.util, io, contextlib, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # capsule root
def load():
    """Imports data/ENERGY_R3.py unchanged. Its start-up code is skipped because it runs only as __main__."""
    spec = importlib.util.spec_from_file_location("energy_r3", os.path.join(ROOT, "data", "ENERGY_R3.py"))
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(m)
    return m
