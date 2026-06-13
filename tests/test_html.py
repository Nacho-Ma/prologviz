"""Tests del export HTML (`renderers/html.py`).

No requieren Prolog: se arma un `TraceTree` a mano y se inspecciona el HTML
generado como string.
"""

from __future__ import annotations

from html.parser import HTMLParser

from prologviz.engine.tree import TraceTree
from prologviz.renderers import html


def _arbol_demo() -> TraceTree:
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("call", "parent", ["tom", "X"], 1)
    tree.add_event("exit", "parent", ["tom", "bob"], 1)
    tree.add_event("exit", "ancestor", ["tom", "bob"], 0)
    tree.add_event("redo", "parent", ["tom", "X"], 1)
    tree.add_event("fail", "parent", ["tom", "X"], 1)
    return tree


def test_render_html_contiene_estructura_basica():
    out = html.render_html(_arbol_demo(), query="ancestor(tom, X)")
    assert "<!DOCTYPE html>" in out
    assert "?- ancestor(tom, X)" in out
    assert 'class="tree"' in out
    assert "parent(tom, bob)" in out
    # eventos presentes
    assert "EXIT" in out and "FAIL" in out
    # marca de backtrack para el retry
    assert "backtrack" in out


def test_render_html_es_bien_formado():
    out = html.render_html(_arbol_demo(), query="q(X)")

    class _P(HTMLParser):
        pass

    _P().feed(out)  # no debe lanzar


def test_render_html_soluciones_con_bindings():
    out = html.render_html(
        _arbol_demo(),
        query="ancestor(tom, X)",
        solutions=[{"X": "bob"}, {"X": "liz"}],
    )
    assert "Soluciones" in out
    assert ">bob<" in out
    assert "2 soluciones" in out


def test_render_html_sin_soluciones_muestra_false():
    out = html.render_html(_arbol_demo(), solutions=[])
    assert "false." in out


def test_render_html_escapa_contenido():
    # autoescape de Jinja: un goal con < o & no debe romper el HTML.
    tree = TraceTree()
    tree.add_event("call", "pred", ["a < b & c"], 0)
    out = html.render_html(tree, query="pred(a < b & c)")
    assert "a < b & c" not in out  # debe venir escapado
    assert "&lt;" in out and "&amp;" in out


def test_export_html_escribe_archivo(tmp_path):
    out_path = tmp_path / "t.html"
    result = html.export_html(
        _arbol_demo(),
        out_path,
        query="ancestor(tom, X)",
        solutions=[{"X": "bob"}],
    )
    assert result == out_path
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "ancestor(tom, X)" in content
