"""Export del árbol de resolución a un HTML estático interactivo.

Genera un único archivo `.html` autocontenido (CSS y JS embebidos, sin
dependencias externas) con:

- el árbol de resolución colapsable (cada nodo se expande/colapsa),
- búsqueda en vivo que resalta y filtra nodos por goal,
- las soluciones de la query,
- los mismos colores que el renderer de terminal.

Usa Jinja2 con el template `templates/trace.html.j2`.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from prologviz.engine.tree import TraceNode, TraceTree

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_NAME = "trace.html.j2"


def _node_to_dict(node: TraceNode) -> dict:
    """Serializa un `TraceNode` (y sus hijos) a un dict simple para el template."""
    return {
        "event": node.event,
        "goal": node.goal,
        "success": node.success,
        "is_retry": node.is_retry,
        "depth": node.depth,
        "children": [_node_to_dict(child) for child in node.children],
    }


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(
    tree: TraceTree,
    query: str | None = None,
    solutions: list[dict[str, str]] | None = None,
) -> str:
    """Devuelve el HTML del trace como string."""
    env = _environment()
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(
        query=query or "trace",
        roots=[_node_to_dict(root) for root in tree.roots],
        solutions=solutions,
        node_count=len(tree),
        event_count=tree.event_count,
    )


def export_html(
    tree: TraceTree,
    path: str | Path,
    query: str | None = None,
    solutions: list[dict[str, str]] | None = None,
) -> Path:
    """Escribe el HTML del trace en ``path`` y devuelve la ruta resultante."""
    out = Path(path)
    out.write_text(
        render_html(tree, query=query, solutions=solutions),
        encoding="utf-8",
    )
    return out
