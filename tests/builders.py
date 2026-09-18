"""Small model builders shared by the unit tests."""

from archview.model.graph import Import, Model, Node
from archview.model.names import ancestors, parent


def model(*imports: tuple[str, str], sep: str = ".") -> Model:
    """A model whose tree is implied by the names in `imports`, split by `sep`."""
    ids: set[str] = set()
    for pair in imports:
        for name in pair:
            ids.update(ancestors(name, sep))
    leaves = {name for pair in imports for name in pair}
    suffix = ".py" if sep == "." else ""
    nodes = tuple(
        Node(
            id=i,
            parent=parent(i, sep),
            kind="module" if i in leaves else "package",
            file=f"{i.replace(sep, '/')}{suffix}" if i in leaves else None,
        )
        for i in sorted(ids)
    )
    return Model(
        project=sorted(ids)[0].split(sep)[0],
        nodes=nodes,
        imports=tuple(
            Import(
                importer=a,
                imported=b,
                file=f"{a.replace(sep, '/')}{suffix}",
                line=n + 1,
                text=f"import {b}",
            )
            for n, (a, b) in enumerate(imports)
        ),
        language="python" if sep == "." else "typescript",
        separator=sep,
    )
