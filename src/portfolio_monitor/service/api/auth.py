class AuthRegistry:
    """Registry of public (unauthenticated) paths.

    Sub-apps register their public paths during construction.
    The auth middleware queries this registry at dispatch time.
    """

    def __init__(self):
        self._public_paths: set[str] = set()

    def add_public_path(self, path: str) -> None:
        self._public_paths.add(path)

    def is_public(self, path: str) -> bool:
        return path in self._public_paths
