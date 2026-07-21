class CleanupError(Exception):
    def __init__(self, errors, primary=None):
        self.errors = tuple(errors)
        self.primary = primary
        super().__init__(f"{len(self.errors)} cleanup callback(s) failed")


class CleanupScope:
    def __init__(self):
        self._entries = []
        self._closed = False

    def defer(self, callback, *args, **kwargs):
        token = object()
        self._entries.append((token, callback, args, kwargs))
        return token

    def cancel(self, token):
        for index, entry in enumerate(self._entries):
            if entry[0] is token:
                del self._entries[index]
                return True
        return False

    def close(self):
        if self._closed:
            return False
        for _, callback, args, kwargs in self._entries:
            callback(*args, **kwargs)
        self._closed = True
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False
