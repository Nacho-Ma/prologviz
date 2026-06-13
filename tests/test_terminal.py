"""Tests del renderer de terminal (`renderers/terminal.py`).

No requieren Prolog: se construye un `TraceTree` a mano y se captura la salida
de rich con una Console en modo `record`.
"""

from __future__ import annotations

from rich.console import Console
from rich.tree import Tree

from prologviz.engine.tree import TraceTree
from prologviz.renderers import terminal


def _arbol_demo() -> TraceTree:
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("call", "parent", ["tom", "X"], 1)
    tree.add_event("exit", "parent", ["tom", "bob"], 1)
    tree.add_event("exit", "ancestor", ["tom", "bob"], 0)
    return tree


def test_build_rich_tree_devuelve_tree():
    rt = terminal.build_rich_tree(_arbol_demo(), query="ancestor(tom, X)")
    assert isinstance(rt, Tree)
    assert len(rt.children) == 1  # un frame de tope


def test_render_incluye_goals_y_estado():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(_arbol_demo(), query="ancestor(tom, X)", console=console)
    out = console.export_text()
    assert "ancestor(tom, bob)" in out
    assert "parent(tom, bob)" in out
    assert "EXIT" in out
    assert "ancestor(tom, X)" in out  # la query en el título


def test_render_arbol_vacio_muestra_aviso():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(TraceTree(), console=console)
    out = console.export_text()
    assert "Sin eventos" in out


def test_node_label_colorea_segun_evento():
    tree = TraceTree()
    tree.add_event("call", "p", ["X"], 0)
    tree.add_event("fail", "p", ["X"], 0)
    label = terminal._node_label(tree.get_root())
    # El estilo de un FAIL debe ser rojo en algún span de la etiqueta.
    estilos = " ".join(str(span.style) for span in label.spans)
    assert "red" in estilos
    assert "FAIL" in label.plain


def test_render_muestra_soluciones_con_bindings():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(
        _arbol_demo(),
        query="ancestor(tom, X)",
        console=console,
        solutions=[{"X": "bob"}, {"X": "liz"}],
    )
    out = console.export_text()
    assert "Soluciones:" in out
    assert "X = bob" in out
    assert "X = liz" in out
    assert "2 soluciones" in out


def test_render_solucion_unica_es_singular():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(
        _arbol_demo(), console=console, solutions=[{"X": "bob"}]
    )
    out = console.export_text()
    assert "1 solución" in out


def test_render_sin_soluciones_muestra_false():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(_arbol_demo(), console=console, solutions=[])
    out = console.export_text()
    assert "false." in out


def test_render_query_ground_muestra_true():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(_arbol_demo(), console=console, solutions=[{}])
    out = console.export_text()
    assert "true" in out


def test_render_sin_solutions_no_imprime_bloque():
    console = Console(record=True, width=100, force_terminal=False)
    terminal.render(_arbol_demo(), console=console)  # solutions=None
    out = console.export_text()
    assert "Soluciones:" not in out


def test_marca_backtrack_en_retry():
    tree = TraceTree()
    tree.add_event("call", "p", [], 0)
    tree.add_event("exit", "p", [], 0)
    tree.add_event("redo", "p", [], 0)
    # el segundo root es el retry
    retry = tree.roots[1]
    label = terminal._node_label(retry)
    assert "backtrack" in label.plain
