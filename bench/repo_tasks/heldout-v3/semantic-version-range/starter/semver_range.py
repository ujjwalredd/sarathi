"""Small semantic version range helper."""


class Version:
    def __init__(self, major, minor, patch, prerelease=(), build=()):
        self.major, self.minor, self.patch = major, minor, patch
        self.prerelease, self.build = tuple(prerelease), tuple(build)

    @classmethod
    def parse(cls, text):
        core = text.split("-", 1)[0].split("+", 1)[0]
        return cls(*(int(part) for part in core.split(".")))

    def __lt__(self, other):
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other):
        return isinstance(other, Version) and not (self < other or other < self)


class Range:
    def __init__(self, expression):
        self.expression = expression

    @classmethod
    def parse(cls, expression):
        return cls(expression)

    def contains(self, version):
        return Version.parse(version) == Version.parse(self.expression)


def satisfies(version, expression):
    return Range.parse(expression).contains(version)
