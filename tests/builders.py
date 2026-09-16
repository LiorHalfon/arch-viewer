"""Small model builders shared by the unit tests."""

from archview.model.graph import Import, Model, Node


def model(*imports: tuple[str, str]) -> Model:
    """A model whose tree is implied by the dotted names in `imports`."""
    ids: set[str] = set()
    for pair in imports:
        for name in pair:
            parts = name.split(".")
            ids.update(".".join(parts[: i + 1]) for i in range(len(parts)))
    leaves = {name for pair in imports for name in pair}
    nodes = tuple(
        Node(
            id=i,
            parent=i.rpartition(".")[0] or None,
            kind="module" if i in leaves else "package",
            file=f"{i.replace('.', '/')}.py" if i in leaves else None,
        )
        for i in sorted(ids)
    )
    return Model(
        project=sorted(ids)[0].split(".")[0],
        nodes=nodes,
        imports=tuple(
            Import(
                importer=a,
                imported=b,
                file=f"{a.replace('.', '/')}.py",
                line=n + 1,
                text=f"import {b}",
            )
            for n, (a, b) in enumerate(imports)
        ),
    )
