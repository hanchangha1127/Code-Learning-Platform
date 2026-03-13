__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from server_runtime.webapp import app
        return app
    raise AttributeError(name)