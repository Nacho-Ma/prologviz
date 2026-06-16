"""Tests del modelo de datos (`engine/tree.py`).

Son puros: no requieren SWI-Prolog. Alimentan eventos a mano y verifican cómo
quedan ubicados en el árbol.
"""

from __future__ import annotations

import pytest

from prologviz.engine.tree import CALL, EXIT, FAIL, REDO, TraceNode, TraceTree


# --------------------------------------------------------------- TraceNode

def test_goal_sin_args():
    assert TraceNode(event=CALL, predicate="fail").goal == "fail"


def test_goal_con_args():
    node = TraceNode(event=CALL, predicate="ancestor", args=["tom", "X"])
    assert node.goal == "ancestor(tom, X)"


def test_add_child_setea_parent():
    parent = TraceNode(event=CALL, predicate="p")
    child = TraceNode(event=CALL, predicate="q")
    parent.add_child(child)
    assert child in parent.children
    assert child.parent is parent


# ---------------------------------------------------------- add_event básico

def test_call_simple_es_root():
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], depth=0)
    root = tree.get_root()
    assert root.predicate == "ancestor"
    assert root.depth == 0
    assert tree.event_count == 1


def test_anidamiento_por_profundidad():
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("call", "parent", ["tom", "X"], 1)
    root = tree.get_root()
    assert root.predicate == "ancestor"
    assert len(root.children) == 1
    assert root.children[0].predicate == "parent"


def test_exit_muta_el_nodo_y_actualiza_args():
    tree = TraceTree()
    tree.add_event("call", "parent", ["tom", "X"], 0)
    tree.add_event("exit", "parent", ["tom", "bob"], 0)
    root = tree.get_root()
    # el mismo nodo cambia de estado, no se crea uno nuevo.
    assert len(tree) == 1
    assert root.event == EXIT
    assert root.success is True
    assert root.args == ["tom", "bob"]
    assert root.goal == "parent(tom, bob)"


def test_fail_marca_success_false():
    tree = TraceTree()
    tree.add_event("call", "parent", ["ann", "X"], 0)
    tree.add_event("fail", "parent", ["ann", "X"], 0)
    root = tree.get_root()
    assert root.event == FAIL
    assert root.success is False


# ------------------------------------------------------------- backtracking

def test_redo_crea_hermano_de_reintento():
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("call", "parent", ["tom", "X"], 1)
    tree.add_event("exit", "parent", ["tom", "bob"], 1)
    tree.add_event("exit", "ancestor", ["tom", "bob"], 0)
    # backtrack: se reintenta parent a profundidad 1
    tree.add_event("redo", "parent", ["tom", "X"], 1)
    tree.add_event("exit", "parent", ["tom", "liz"], 1)

    root = tree.get_root()
    assert len(root.children) == 2, "el redo debe agregar un hermano, no anidar"
    first, retry = root.children
    assert first.is_retry is False
    assert retry.is_retry is True
    assert retry.args == ["tom", "liz"]


def test_redo_profundo_tras_exit_no_se_escapa_a_root():
    """Regresión: un `redo` profundo después de que el padre hizo `exit`.

    El frame padre ya cerró (exit) pero en Prolog puede reusarse como padre de
    un reintento más profundo. No debe colgar de la raíz (fragmentando el árbol).
    """
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("call", "parent", ["tom", "X"], 1)
    tree.add_event("exit", "parent", ["tom", "bob"], 1)
    tree.add_event("exit", "ancestor", ["tom", "bob"], 0)  # padre cierra
    # ahora un redo a profundidad 1 (más profundo que el root cerrado)
    tree.add_event("redo", "parent", ["tom", "X"], 1)

    # Sigue habiendo un solo frame de tope: el redo cuelga del ancestor, no de root.
    assert len(tree.roots) == 1
    root = tree.get_root()
    assert all(child.depth == 1 for child in root.children)
    assert len(root.children) == 2


def test_redo_en_nivel_0_genera_multiples_roots():
    """Un redo del goal de tope (otra cláusula) es un nuevo frame de tope."""
    tree = TraceTree()
    tree.add_event("call", "ancestor", ["tom", "X"], 0)
    tree.add_event("exit", "ancestor", ["tom", "bob"], 0)
    tree.add_event("redo", "ancestor", ["tom", "X"], 0)
    tree.add_event("fail", "ancestor", ["tom", "X"], 0)

    assert len(tree.roots) == 2
    # get_root() con varios tope devuelve la raíz sintética <query>.
    assert tree.get_root().predicate == "<query>"


# --------------------------------------------------------- outcome / exit_count

def test_outcome_exit_gana_sobre_fail_posterior():
    """Un goal que exitea y luego falla (al agotar backtracking) sigue siendo exit."""
    tree = TraceTree()
    tree.add_event("call", "arreglo", ["5", "3", "X"], 0)
    tree.add_event("exit", "arreglo", ["5", "3", "60"], 0)
    tree.add_event("fail", "arreglo", ["5", "3", "X"], 0)  # backtracking agotado
    root = tree.get_root()
    assert root.event == "fail"          # el último puerto fue fail
    assert root.exit_count == 1
    assert root.outcome == EXIT          # pero el resultado global es éxito
    # y conserva los argumentos ligados de la solución, no los del fail
    assert root.goal == "arreglo(5, 3, 60)"


def test_outcome_fail_puro():
    tree = TraceTree()
    tree.add_event("call", "p", ["X"], 0)
    tree.add_event("fail", "p", ["X"], 0)
    assert tree.get_root().outcome == FAIL


def test_exit_count_cuenta_soluciones():
    tree = TraceTree()
    tree.add_event("call", "p", ["X"], 0)
    tree.add_event("exit", "p", ["a"], 0)
    tree.add_event("exit", "p", ["b"], 0)  # segunda solución del mismo frame
    root = tree.get_root()
    assert root.exit_count == 2
    assert root.outcome == EXIT


def test_outcome_call_abierto():
    tree = TraceTree()
    tree.add_event("call", "p", ["X"], 0)  # sin cerrar (trace cortado)
    assert tree.get_root().outcome == CALL


# ----------------------------------------------------------------- varios

def test_evento_invalido_lanza():
    tree = TraceTree()
    with pytest.raises(ValueError):
        tree.add_event("boom", "p", [], 0)


def test_eventos_case_insensitive():
    tree = TraceTree()
    tree.add_event("CALL", "p", [], 0)
    tree.add_event("Exit", "p", [], 0)
    assert tree.get_root().event == EXIT


def test_close_sin_call_previo_es_tolerante():
    """Si llega un exit sin su call (trace incompleto) no se pierde el evento."""
    tree = TraceTree()
    tree.add_event("exit", "huerfano", ["x"], 0)
    root = tree.get_root()
    assert root.predicate == "huerfano"
    assert root.success is True


def test_walk_recorre_en_preorden():
    tree = TraceTree()
    tree.add_event("call", "a", [], 0)
    tree.add_event("call", "b", [], 1)
    tree.add_event("exit", "b", [], 1)
    tree.add_event("call", "c", [], 1)
    nombres = [n.predicate for n in tree.walk()]
    assert nombres == ["a", "b", "c"]
    assert len(tree) == 3


def test_constantes_de_evento():
    assert (CALL, EXIT, FAIL, REDO) == ("call", "exit", "fail", "redo")
