"""Modelo de datos del árbol de resolución.

Un programa Prolog se ejecuta produciendo una secuencia de *eventos* de trace
(`call`, `exit`, `fail`, `redo`), cada uno con una profundidad asociada. Este
módulo reconstruye esa secuencia en un árbol navegable (`TraceTree`) compuesto
por nodos (`TraceNode`).

El modelo es independiente de pyswip / SWI-Prolog: recibe eventos ya
normalizados (strings) y los ubica en el árbol. Eso lo hace fácil de testear
sin necesidad de tener Prolog instalado.

## Cómo se ubica cada evento

Cada `call` abre un *frame* (un intento de resolver un objetivo) que se cuelga
del frame abierto en la profundidad inmediatamente superior. Los eventos
`exit` / `fail` cierran el frame abierto en su profundidad, marcando si tuvo
éxito y actualizando sus argumentos a los valores ya unificados. Un `redo`
reabre el objetivo: crea un nuevo frame hermano (un reintento con otra
cláusula), que es exactamente el backtracking que queremos visualizar.

    call  depth=0  ancestor(tom, X)      -> frame raíz
      call  depth=1  parent(tom, X)      -> hijo del frame raíz
      exit  depth=1  parent(tom, bob)    -> cierra el hijo (success)
    exit  depth=0  ancestor(tom, bob)    -> cierra la raíz (success)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Eventos válidos del trace de SWI-Prolog que modelamos.
CALL = "call"
EXIT = "exit"
FAIL = "fail"
REDO = "redo"

VALID_EVENTS = frozenset({CALL, EXIT, FAIL, REDO})


@dataclass
class TraceNode:
    """Un nodo del árbol de resolución: un objetivo (goal) y su resultado.

    Un nodo nace con un evento ``call`` y va mutando a medida que llegan los
    eventos que lo cierran: ``exit`` (éxito), ``fail`` (fallo) o ``redo``
    (reintento, que en realidad genera un nodo hermano nuevo).
    """

    event: str                              # "call" | "exit" | "fail" | "redo"
    predicate: str                          # nombre del predicado, ej: "ancestor"
    args: list[str] = field(default_factory=list)   # args como strings legibles
    depth: int = 0                          # profundidad en el árbol
    children: list[TraceNode] = field(default_factory=list)
    success: bool = False                   # True si el ÚLTIMO evento fue `exit`
    is_retry: bool = False                  # True si nació de un `redo` (backtrack)
    exit_count: int = 0                     # cuántas veces el goal hizo `exit` (soluciones)
    # Referencia al nodo padre, útil para navegar hacia arriba. Se excluye de
    # repr/compare para no entrar en recursión infinita (el padre apunta a sus
    # hijos y viceversa).
    parent: TraceNode | None = field(default=None, repr=False, compare=False)

    @property
    def goal(self) -> str:
        """Representación legible del objetivo, ej: ``ancestor(tom, X)``."""
        if not self.args:
            return self.predicate
        return f"{self.predicate}({', '.join(self.args)})"

    @property
    def outcome(self) -> str:
        """Resultado *global* del goal, no solo su último puerto.

        Un goal que tuvo al menos un `exit` se considera ``exit`` (tuvo éxito),
        aunque después haya fallado al backtrackear buscando más soluciones. Esto
        evita pintar de rojo un goal que en realidad sí encontró una respuesta.
        """
        if self.exit_count > 0:
            return EXIT
        if self.event == FAIL:
            return FAIL
        return self.event  # `call` o `redo`: todavía abierto / sin cerrar

    def add_child(self, node: TraceNode) -> TraceNode:
        node.parent = self
        self.children.append(node)
        return node

    def __repr__(self) -> str:  # pragma: no cover - solo debugging
        return (
            f"TraceNode({self.event}, {self.goal!r}, depth={self.depth}, "
            f"success={self.success}, children={len(self.children)})"
        )


class TraceTree:
    """Construye y contiene el árbol de resolución a partir de eventos.

    Uso típico::

        tree = TraceTree()
        tree.add_event("call", "ancestor", ["tom", "X"], depth=0)
        tree.add_event("call", "parent",   ["tom", "X"], depth=1)
        tree.add_event("exit", "parent",   ["tom", "bob"], depth=1)
        tree.add_event("exit", "ancestor", ["tom", "bob"], depth=0)
        root = tree.get_root()
    """

    def __init__(self) -> None:
        # Raíz sintética: contiene los goals de nivel 0 como hijos. Esto permite
        # que una query produzca varios frames de tope (p. ej. por backtracking
        # entre cláusulas del predicado de la query).
        self._root = TraceNode(event=CALL, predicate="<query>", depth=-1)
        # Nodo más reciente por profundidad. NO se borra en exit/fail: en Prolog
        # un frame que ya hizo `exit` puede volver a usarse como padre cuando un
        # objetivo más profundo hace `redo` (backtracking). Solo se limpian las
        # profundidades más hondas cuando llega un evento a un nivel más superficial.
        self._current: dict[int, TraceNode] = {}
        self._event_count = 0

    # ------------------------------------------------------------------ API

    def add_event(
        self,
        event: str,
        predicate: str,
        args: list[str] | None = None,
        depth: int = 0,
    ) -> TraceNode:
        """Agrega un evento y lo ubica en el árbol. Devuelve el nodo afectado.

        - ``call``: crea un frame nuevo colgado del frame padre (profundidad
          ``depth - 1``) y lo marca como abierto en ``depth``.
        - ``exit`` / ``fail``: cierra el frame abierto en ``depth`` (o crea uno
          si no existe, para ser tolerante a traces incompletos).
        - ``redo``: reabre el objetivo creando un frame hermano de reintento.
        """
        event = event.lower()
        if event not in VALID_EVENTS:
            raise ValueError(
                f"Evento desconocido: {event!r}. Esperado uno de {sorted(VALID_EVENTS)}."
            )

        args = list(args) if args else []
        self._event_count += 1

        if event == CALL:
            return self._handle_call(predicate, args, depth, is_retry=False)
        if event == REDO:
            return self._handle_call(predicate, args, depth, is_retry=True)
        # exit / fail
        return self._handle_close(event, predicate, args, depth)

    def get_root(self) -> TraceNode:
        """Devuelve la raíz del árbol.

        Si la query produjo un único frame de tope, devuelve ese frame
        directamente; si produjo varios (backtracking de nivel 0), devuelve la
        raíz sintética ``<query>`` que los agrupa.
        """
        if len(self._root.children) == 1:
            return self._root.children[0]
        return self._root

    @property
    def roots(self) -> list[TraceNode]:
        """Los frames de tope (hijos directos de la raíz sintética)."""
        return list(self._root.children)

    @property
    def event_count(self) -> int:
        """Cantidad total de eventos procesados."""
        return self._event_count

    def __len__(self) -> int:
        """Cantidad de nodos en el árbol (sin contar la raíz sintética)."""
        return sum(1 for _ in self.walk())

    def walk(self):
        """Recorre el árbol en pre-orden (DFS), sin incluir la raíz sintética."""
        stack = list(reversed(self._root.children))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    # ------------------------------------------------------------- internos

    def _parent_for(self, depth: int) -> TraceNode:
        """Frame padre para un nodo a profundidad ``depth``.

        Es el nodo más reciente a ``depth - 1``; si no hay ninguno (porque
        ``depth`` es 0 o el trace está incompleto), cuelga de la raíz sintética.
        """
        for d in range(depth - 1, -1, -1):
            if d in self._current:
                return self._current[d]
        return self._root

    def _clear_deeper(self, depth: int) -> None:
        """Olvida los nodos a profundidad mayor: pertenecen a un intento previo."""
        for d in [d for d in self._current if d > depth]:
            del self._current[d]

    def _handle_call(
        self, predicate: str, args: list[str], depth: int, is_retry: bool
    ) -> TraceNode:
        # Un `redo` crea un nodo de reintento hermano (otro intento del objetivo);
        # un `call` crea el primer intento. En ambos casos el padre es el nodo
        # más reciente del nivel superior.
        node = TraceNode(
            event=CALL,
            predicate=predicate,
            args=args,
            depth=depth,
            is_retry=is_retry,
        )
        self._parent_for(depth).add_child(node)
        self._clear_deeper(depth)
        self._current[depth] = node
        return node

    def _handle_close(
        self, event: str, predicate: str, args: list[str], depth: int
    ) -> TraceNode:
        node = self._current.get(depth)
        if node is None:
            # Trace incompleto: no vimos el `call`. Creamos el nodo igual para no
            # perder el evento.
            node = TraceNode(event=CALL, predicate=predicate, depth=depth)
            self._parent_for(depth).add_child(node)
            self._current[depth] = node

        node.event = event
        node.success = event == EXIT
        if event == EXIT:
            node.exit_count += 1
            # En el exit los argumentos ya están unificados: preferimos esos valores.
            if args:
                node.args = args
        else:
            # En un `fail` solo actualizamos los args si el goal nunca tuvo éxito;
            # si ya había exiteado, conservamos los valores ligados de la solución.
            if args and node.exit_count == 0:
                node.args = args

        # El nodo sigue siendo el "más reciente" a su nivel (un `redo` posterior
        # más profundo aún puede colgar de él), pero todo lo que estaba por debajo
        # pertenecía a este intento ya terminado.
        self._clear_deeper(depth)
        return node
