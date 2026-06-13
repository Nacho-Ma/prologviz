"""Tests de integración del trace engine (`engine/tracer.py`).

Requieren SWI-Prolog (`swipl` en el PATH) y pyswip; si faltan, se saltean.
Corren la query de verdad sobre `examples/family.pl`.

Nota: pyswip usa una única instancia global de Prolog por proceso, así que
estos tests comparten esa instancia (no hay aislamiento entre ellos, pero el
`family.pl` se vuelve a consultar en cada `run()`).
"""

from __future__ import annotations

from .conftest import requires_prolog


@requires_prolog
def test_run_ancestor_captura_eventos(family_pl):
    from prologviz.engine.tracer import Tracer

    tree = Tracer(str(family_pl), "ancestor(tom, X)").run()

    assert tree.event_count > 0
    assert len(tree) > 0
    assert tree.roots, "debería haber al menos un frame de tope"


@requires_prolog
def test_run_normaliza_profundidad_a_cero(family_pl):
    from prologviz.engine.tracer import Tracer

    tree = Tracer(str(family_pl), "ancestor(tom, X)").run()
    # El goal de tope del usuario debe quedar en profundidad 0, sin el offset
    # de los frames internos del toplevel / pyrun.
    assert all(root.depth == 0 for root in tree.roots)


@requires_prolog
def test_run_filtra_wrapper_pyrun(family_pl):
    from prologviz.engine.tracer import Tracer

    tree = Tracer(str(family_pl), "ancestor(tom, X)").run()
    predicados = {n.predicate for n in tree.walk()}
    assert "pyrun" not in predicados
    assert predicados <= {"ancestor", "parent"}


@requires_prolog
def test_run_encuentra_soluciones_con_exit(family_pl):
    from prologviz.engine.tracer import Tracer

    tree = Tracer(str(family_pl), "ancestor(tom, X)").run()
    exits = [n for n in tree.walk() if n.success]
    # ancestor(tom, X) tiene soluciones (bob, liz, ann) -> hay nodos en exit.
    assert exits, "esperaba al menos un nodo en exit"


@requires_prolog
def test_run_query_que_falla(family_pl):
    from prologviz.engine.tracer import Tracer

    # nadie es ancestro de tom -> la query falla, pero igual hay trace.
    tree = Tracer(str(family_pl), "ancestor(X, tom)").run()
    assert tree.event_count > 0
    assert any(n.event == "fail" for n in tree.walk())


@requires_prolog
def test_max_depth_acota_la_profundidad(family_pl):
    from prologviz.engine.tracer import Tracer

    tree = Tracer(str(family_pl), "ancestor(tom, X)", max_depth=1).run()
    assert all(n.depth <= 1 for n in tree.walk())


@requires_prolog
def test_max_solutions_corta_la_enumeracion(family_pl):
    from prologviz.engine.tracer import Tracer

    una = Tracer(str(family_pl), "ancestor(tom, X)", max_solutions=1).run()
    todas = Tracer(str(family_pl), "ancestor(tom, X)").run()
    # Cortar en la primera solución debe producir (estrictamente) menos eventos.
    assert una.event_count < todas.event_count


@requires_prolog
def test_archivo_inexistente_lanza(tmp_path):
    from prologviz.engine.tracer import Tracer

    falta = tmp_path / "no_existe.pl"
    try:
        Tracer(str(falta), "foo(X)").run()
    except FileNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("esperaba FileNotFoundError")
