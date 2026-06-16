"""Renderizado del árbol de resolución en la terminal con `rich`.

Toma un `TraceTree` y lo imprime como un árbol coloreado y navegable
visualmente, con un color por tipo de evento:

    CALL  -> azul      EXIT -> verde
    REDO  -> amarillo  FAIL -> rojo

Los nodos que terminaron en `exit` llevan ``✓`` y los que fallaron ``✗``. Los
nodos nacidos de un `redo` (backtracking) se marcan con ``[backtrack]``.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from prologviz.engine.tree import CALL, EXIT, FAIL, REDO, TraceNode, TraceTree

# Estilo (color rich) por evento.
_EVENT_STYLE = {
    CALL: "blue",
    EXIT: "green",
    FAIL: "red",
    REDO: "yellow",
}


def _supports_unicode() -> bool:
    """True si la consola puede codificar los símbolos ✓/✗ sin romperse.

    En consolas legacy de Windows (cp1252) no se pueden, así que caemos a ASCII.
    """
    enc = getattr(sys.stdout, "encoding", None) or ""
    try:
        "✓✗".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# Símbolos (Unicode si la consola lo soporta; si no, ASCII).
if _supports_unicode():
    _RESULT_MARK = {EXIT: " ✓", FAIL: " ✗"}
    _SEP = "·"
else:
    _RESULT_MARK = {EXIT: " [OK]", FAIL: " [X]"}
    _SEP = "-"


def _node_label(node: TraceNode) -> Text:
    """Construye la etiqueta coloreada de un nodo según su *resultado global*.

    Usa ``node.outcome`` (no el último puerto), así un goal que tuvo éxito y
    luego falló al backtrackear se muestra en verde con ✓, no en rojo.
    """
    outcome = node.outcome
    style = _EVENT_STYLE.get(outcome, "white")
    label = Text()
    label.append(f"{outcome.upper()} ", style=f"bold {style}")
    label.append(node.goal, style=style)
    label.append(_RESULT_MARK.get(outcome, ""), style=f"bold {style}")
    # Si el goal tuvo varias soluciones, lo indicamos.
    if node.exit_count > 1:
        label.append(f" ({node.exit_count} sol.)", style=f"dim {style}")
    if node.is_retry:
        label.append("  [backtrack]", style="dim yellow")
    return label


def _attach(parent_tree: Tree, node: TraceNode) -> None:
    """Agrega ``node`` (y sus hijos, recursivamente) a un árbol de rich."""
    branch = parent_tree.add(_node_label(node))
    for child in node.children:
        _attach(branch, child)


def build_rich_tree(tree: TraceTree, query: str | None = None) -> Tree:
    """Convierte un `TraceTree` en un `rich.tree.Tree` con título ``?- query``."""
    title = Text("?- ", style="bold magenta")
    title.append(query or "trace", style="magenta")
    root = Tree(title, guide_style="dim")
    for top in tree.roots:
        _attach(root, top)
    return root


def _build_forest(tree: TraceTree) -> list[Tree]:
    """Convierte cada frame de tope en su propio `Tree`, sin título envolvente."""
    forest = []
    for top in tree.roots:
        t = Tree(_node_label(top), guide_style="dim")
        for child in top.children:
            _attach(t, child)
        forest.append(t)
    return forest


def render(
    tree: TraceTree,
    query: str | None = None,
    console: Console | None = None,
    solutions: list[dict[str, str]] | None = None,
) -> None:
    """Imprime el árbol de resolución (y las soluciones) en la terminal.

    Args:
        tree: el `TraceTree` a renderizar.
        query: la query original, para mostrarla como título (opcional).
        console: una `rich.Console` a reusar (opcional; se crea una si falta).
        solutions: lista de bindings {Var: valor} de la query. ``None`` la omite;
            una lista vacía se muestra como ``false`` (la query no tuvo solución).
    """
    console = console or Console()
    if not tree.roots:
        console.print(
            "[yellow]Sin eventos de trace.[/] "
            "¿La query no produjo soluciones o falló al consultar el programa?"
        )
        return

    if query is None:
        # Modo sesión: el goal ya está en el prompt, imprimimos el bosque sin título.
        for t in _build_forest(tree):
            console.print(t)
    else:
        console.print(build_rich_tree(tree, query))
    _print_legend(console, tree)
    if solutions is not None:
        _print_solutions(console, solutions)


def _print_solutions(console: Console, solutions: list[dict[str, str]]) -> None:
    """Imprime las soluciones de la query, al estilo del toplevel de SWI."""
    console.print(Text("\nSoluciones:", style="bold magenta"))

    if not solutions:
        # Sin soluciones: la query falló.
        console.print(Text("  false.", style="bold red"))
        return

    for sol in solutions:
        line = Text("  ")
        if not sol:
            # Query ground que tuvo éxito (sin variables que mostrar).
            line.append("true", style="bold green")
        else:
            bindings = [
                Text.assemble((var, "cyan"), " = ", (val, "bold green"))
                for var, val in sol.items()
            ]
            line.append(Text(", ").join(bindings))
        console.print(line)

    n = len(solutions)
    palabra = "solución" if n == 1 else "soluciones"
    console.print(Text(f"  ({n} {palabra})", style="dim"))


def _print_legend(console: Console, tree: TraceTree) -> None:
    """Imprime una leyenda de colores y un resumen breve."""
    legend = Text("\n")
    for event, style in _EVENT_STYLE.items():
        legend.append(f"  {event.upper()} ", style=f"bold {style}")
    legend.append(
        f"   {_SEP}   {len(tree)} nodos {_SEP} {tree.event_count} eventos", style="dim"
    )
    console.print(legend)
