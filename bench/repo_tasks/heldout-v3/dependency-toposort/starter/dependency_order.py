"""Order nodes after their dependencies."""


class DependencyCycleError(ValueError):
    pass


def topological_order(graph):
    visited = set()
    result = []
    def visit(node):
        if node in visited:
            return
        visited.add(node)
        for dependency in graph.get(node, ()):
            visit(dependency)
        result.append(node)
    for node in sorted(graph):
        visit(node)
    return tuple(result)
