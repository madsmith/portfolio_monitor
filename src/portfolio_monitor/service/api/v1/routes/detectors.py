import inspect

import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.detectors import DetectorRegistry


@logfire.instrument("api.detectors.list")
async def list_detectors(request: Request) -> JSONResponse:
    """Return all registered detector kinds with their constructor arg specs."""
    infos = DetectorRegistry.list_detector_infos()
    result = []
    for info in infos:
        args = []
        for arg in info.args:
            entry: dict = {"name": arg.name, "type": arg.type, "description": arg.description}
            if not arg.required:
                entry["default"] = arg.default
            if arg.options is not None:
                entry["options"] = arg.options
            args.append(entry)
        result.append({"name": info.name, "display_name": info.display_name, "description": info.description, "args": args})
    return JSONResponse(result)
