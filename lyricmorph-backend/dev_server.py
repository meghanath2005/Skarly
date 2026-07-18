import sys
import os
from pathlib import Path
import importlib.util


backend_root = Path(__file__).resolve().parent
dependency_paths = [backend_root / ".pydeps"]
for dependency_path in reversed(dependency_paths):
    if dependency_path.exists():
        dependency_path_text = str(dependency_path)
        sys.path = [path for path in sys.path if path != dependency_path_text]
        sys.path.insert(0, dependency_path_text)

existing_pythonpath = os.environ.get("PYTHONPATH", "")
pythonpath_parts = [part for part in existing_pythonpath.split(os.pathsep) if part]
for dependency_path in dependency_paths:
    if dependency_path.exists():
        dependency_path_text = str(dependency_path)
        if dependency_path_text not in pythonpath_parts:
            pythonpath_parts.insert(0, dependency_path_text)
if pythonpath_parts:
    os.environ["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

pydeps = backend_root / ".pydeps"

uvicorn_init = pydeps / "uvicorn" / "__init__.py"
if uvicorn_init.exists():
    spec = importlib.util.spec_from_file_location(
        "uvicorn",
        uvicorn_init,
        submodule_search_locations=[str(uvicorn_init.parent)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load local uvicorn package")
    uvicorn = importlib.util.module_from_spec(spec)
    sys.modules["uvicorn"] = uvicorn
    spec.loader.exec_module(uvicorn)
    run = uvicorn.run
else:
    from uvicorn import run  # noqa: E402


if __name__ == "__main__":
    run("app.main:app", host="127.0.0.1", port=8090)
