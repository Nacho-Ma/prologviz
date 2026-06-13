"""Trace engine: corre queries Prolog capturando sus eventos de trace.

Dos niveles de uso:

- `Tracer`: one-shot. Consulta un programa, corre **una** query y devuelve su
  `TraceTree`. Es lo que usa `prologviz run`.
- `Session`: persistente. Consulta el programa y los goals de preparación **una
  vez**, y permite tracear **muchas** queries reusando el mismo estado de Prolog
  (los asserts persisten entre queries). Es lo que usa `prologviz session`.

Ambos comparten el mismo motor de captura (`_run_traced_query`).

Limitaciones conocidas (ver README):
- pyswip no soporta varias instancias de Prolog por proceso: usamos una única
  instancia global y un único registro de la función foránea. Por eso el estado
  (programas consultados, asserts) es global al proceso.
- Las variables sin ligar se muestran como ``A, B, C...`` (numbervars), no con
  los nombres originales del fuente, que no están disponibles en runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

from prologviz.engine.tree import TraceTree

# Separador con que el glue de Prolog empaqueta los argumentos (carácter US).
_ARG_SEP = "\x1f"

# --- Estado global de proceso (pyswip = una sola instancia de Prolog) --------

_PROLOG = None              # instancia pyswip.Prolog (lazy)
_HOOK_REGISTERED = False    # si ya consultamos trace_hook.pl + registerForeign
_ACTIVE_RECEIVER = None     # objeto con _on_event que recibe los eventos en curso

_HOOK_FILE = Path(__file__).with_name("trace_hook.pl")


def _get_prolog():
    """Devuelve la instancia global de Prolog, creándola la primera vez."""
    global _PROLOG
    if _PROLOG is None:
        from pyswip import Prolog  # import diferido: requiere SWI-Prolog instalado

        _PROLOG = Prolog()
    return _PROLOG


def _pyviz_event(port, pred, packed, depth) -> bool:
    """Función foránea invocada desde Prolog por cada evento del trace.

    Reenvía el evento al receptor activo. Firma fijada en arity 4 para pyswip.
    Siempre devuelve True para que el predicado Prolog tenga éxito.
    """
    if _ACTIVE_RECEIVER is not None:
        _ACTIVE_RECEIVER._on_event(str(port), str(pred), str(packed), int(depth))
    return True


_pyviz_event.arity = 4


def _ensure_hook_registered() -> None:
    """Registra la función foránea y consulta el glue de trace (una sola vez)."""
    global _HOOK_REGISTERED
    if _HOOK_REGISTERED:
        return
    from pyswip import registerForeign

    prolog = _get_prolog()
    # El foráneo debe existir antes de consultar el glue que lo referencia.
    registerForeign(_pyviz_event, name="pyviz_event", arity=4)
    hook_path = _HOOK_FILE.as_posix()
    list(prolog.query(f"consult('{hook_path}')"))
    _HOOK_REGISTERED = True


def parse_setup_file(path: str | os.PathLike[str]) -> list[str]:
    """Lee un archivo de goals de preparación (uno por línea).

    Ignora líneas vacías y comentarios (``%``). El punto final de cada goal es
    opcional. Pensado para cargar muchos asserts cómodamente::

        % kb.pl
        assertz(edge(a, b)).
        assertz(edge(b, c)).
    """
    text = Path(path).read_text(encoding="utf-8")
    goals: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%"):
            continue
        goals.append(line.rstrip(".").strip())
    return goals


class _QueryTrace:
    """Receptor de eventos para **una** query: acumula el árbol y normaliza depth."""

    def __init__(self, max_depth: int) -> None:
        self.max_depth = max_depth
        self.tree = TraceTree()
        self._base_depth: int | None = None

    def _on_event(self, port: str, pred: str, packed: str, depth: int) -> None:
        # Normalizamos la profundidad para que el primer goal del usuario sea 0.
        if self._base_depth is None:
            self._base_depth = depth
        norm_depth = max(0, depth - self._base_depth)
        if norm_depth > self.max_depth:
            return
        args = packed.split(_ARG_SEP) if packed else []
        self.tree.add_event(port, pred, args, norm_depth)


def _run_traced_query(
    query: str,
    max_depth: int,
    max_solutions: int | None,
) -> tuple[TraceTree, list[dict[str, str]]]:
    """Corre ``query`` con trace activo sobre la instancia global ya consultada.

    Devuelve (árbol, soluciones). Asume que el programa y el setup ya se cargaron.
    """
    global _ACTIVE_RECEIVER
    prolog = _get_prolog()
    receiver = _QueryTrace(max_depth)
    solutions: list[dict[str, str]] = []

    _ACTIVE_RECEIVER = receiver
    try:
        # leash(-all): el tracer nunca se detiene a pedir input interactivo.
        # visible(+all): nos llegan todos los puertos. catcherrors=False evita
        # que pyswip abra la query con PL_Q_NODEBUG (que apagaría el debugger).
        list(prolog.query("leash(-all)", catcherrors=False))
        list(prolog.query("visible(+all)", catcherrors=False))
        list(prolog.query("trace", catcherrors=False))
        try:
            count = 0
            for sol in prolog.query(query, catcherrors=False):
                # pyswip entrega un dict de bindings {Var: valor} por solución
                # (vacío si la query es ground/sin variables, pero tuvo éxito).
                solutions.append({str(k): str(v) for k, v in sol.items()})
                count += 1
                if max_solutions is not None and count >= max_solutions:
                    break
        finally:
            # Apagamos el trace pase lo que pase, para no dejar el engine sucio.
            list(prolog.query("notrace", catcherrors=False))
    finally:
        _ACTIVE_RECEIVER = None

    return receiver.tree, solutions


class Session:
    """Estado Prolog persistente para tracear varias queries reusando los asserts.

    Consulta el programa y corre los goals de preparación **una vez** (en
    `start`). Después, cada `trace_query` corre contra ese estado compartido, así
    los asserts (de setup o hechos en vivo) persisten entre queries.

    Args:
        program_file: ruta al ``.pl`` a consultar.
        max_depth: profundidad máxima de eventos a capturar por query.
        setup_goals: goals a ejecutar (sin tracear) al arrancar, p. ej. asserts.
    """

    def __init__(
        self,
        program_file: str | os.PathLike[str],
        max_depth: int = 20,
        setup_goals: list[str] | None = None,
    ) -> None:
        self.program_file = Path(program_file)
        self.max_depth = max_depth
        self.setup_goals = [g.strip().rstrip(".").strip() for g in (setup_goals or [])]
        self._started = False

    # --------------------------------------------------------------- ciclo

    def start(self) -> None:
        """Consulta el programa y corre los goals de preparación (una vez)."""
        if not self.program_file.exists():
            raise FileNotFoundError(f"No existe el archivo Prolog: {self.program_file}")
        _ensure_hook_registered()
        self._consult_program()
        self._apply_setup()
        self._started = True

    def reset(self) -> None:
        """Recarga el programa y reaplica el setup, descartando asserts en vivo."""
        self._consult_program()
        self._apply_setup()

    def _apply_setup(self) -> None:
        """Corre los goals de setup; lanza si alguno falla."""
        for goal in self.setup_goals:
            if not self.run_goal_untraced(goal):
                raise RuntimeError(f"El goal de setup falló: {goal}")

    def _consult_program(self) -> None:
        prolog = _get_prolog()
        list(prolog.query(f"consult('{self.program_file.as_posix()}')"))

    # -------------------------------------------------------------- queries

    def trace_query(
        self, query: str, max_solutions: int | None = None
    ) -> tuple[TraceTree, list[dict[str, str]]]:
        """Tracea una query contra el estado actual. Devuelve (árbol, soluciones)."""
        query = query.strip().rstrip(".").strip()
        return _run_traced_query(query, self.max_depth, max_solutions)

    def run_goal_untraced(self, goal: str) -> bool:
        """Corre un goal SIN tracear (asserts, consult, flags). True si tuvo éxito.

        Lanza la excepción de Prolog si el goal da error (sintaxis, permisos…).
        """
        prolog = _get_prolog()
        goal = goal.strip().rstrip(".").strip()
        solutions = list(prolog.query(goal, catcherrors=False, maxresult=1))
        return bool(solutions)


class Tracer:
    """Ejecuta UNA query Prolog y reconstruye su árbol de resolución (one-shot).

    Args:
        program_file: ruta al archivo ``.pl`` a consultar.
        query: la query como string, ej. ``"ancestor(tom, X)"`` (sin punto final).
        max_depth: profundidad máxima de eventos a capturar (default: 20). Los
            eventos más profundos se descartan para acotar traces explosivos.
        max_solutions: tope de soluciones a enumerar (default: None = todas).
        setup_goals: goals de preparación que se ejecutan **antes** de la query y
            **sin tracear** (asserts, ``consult``, flags, etc.). No aparecen en el
            árbol. Recordá que para asertar un predicado debe estar declarado
            ``:- dynamic`` en el programa.
    """

    def __init__(
        self,
        program_file: str | os.PathLike[str],
        query: str,
        max_depth: int = 20,
        max_solutions: int | None = None,
        setup_goals: list[str] | None = None,
    ) -> None:
        self.program_file = Path(program_file)
        self.query = query.strip().rstrip(".").strip()
        self.max_depth = max_depth
        self.max_solutions = max_solutions
        self.setup_goals = setup_goals or []
        # Soluciones de la query: lista de bindings {Var: valor}. Una lista vacía
        # significa que la query falló (no hay soluciones).
        self.solutions: list[dict[str, str]] = []

    def run(self) -> TraceTree:
        """Corre la query con trace activo y devuelve el `TraceTree` resultante."""
        session = Session(
            self.program_file,
            max_depth=self.max_depth,
            setup_goals=self.setup_goals,
        )
        session.start()
        tree, self.solutions = session.trace_query(
            self.query, max_solutions=self.max_solutions
        )
        return tree
