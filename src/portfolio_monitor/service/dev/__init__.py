__all__ = ["run_dev_service"]


def __getattr__(name: str) -> object:
    if name == "run_dev_service":
        from .service import run_dev_service
        return run_dev_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
