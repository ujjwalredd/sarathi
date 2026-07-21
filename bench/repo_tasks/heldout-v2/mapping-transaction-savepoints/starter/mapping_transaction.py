class MappingTransaction:
    def __init__(self, mapping):
        self._mapping = mapping
        self._originals = {}
        self._closed = False

    def _check_open(self):
        if self._closed:
            raise RuntimeError("transaction is closed")

    def set(self, key, value):
        self._check_open()
        if key not in self._originals:
            self._originals[key] = (key in self._mapping, self._mapping.get(key))
        self._mapping[key] = value

    def delete(self, key):
        self._check_open()
        if key not in self._mapping:
            raise KeyError(key)
        if key not in self._originals:
            self._originals[key] = (True, self._mapping[key])
        del self._mapping[key]

    def savepoint(self):
        self._check_open()
        return dict(self._mapping)

    def rollback_to(self, token):
        self._check_open()
        self._mapping.clear()
        self._mapping.update(token)

    def commit(self):
        self._check_open()
        self._closed = True

    def rollback(self):
        self._check_open()
        for key, (existed, value) in self._originals.items():
            if existed:
                self._mapping[key] = value
            else:
                self._mapping.pop(key, None)
        self._closed = True

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False
