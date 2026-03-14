import inspect

from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.detectors import DetectorRegistry


async def list_detectors(request: Request) -> JSONResponse:
    """Return all registered detector kinds with their constructor arg specs."""
    infos = DetectorRegistry.list_detector_infos()
    result = []
    for info in infos:
        args = []
        for arg in info.args:
            entry: dict = {"name": arg.name, "type": arg.type}
            if not arg.required:
                entry["default"] = arg.default
            args.append(entry)
        result.append({"name": info.name, "args": args})
    return JSONResponse(result)
