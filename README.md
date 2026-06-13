# prologviz

Visualiza el árbol de resolución (backtracking) de programas Prolog de forma
legible. En lugar del trace nativo de SWI-Prolog —difícil de leer para
estudiantes— `prologviz` reconstruye los eventos `Call/Exit/Fail/Redo` en un
árbol y lo renderiza con colores en la terminal (y, más adelante, como HTML
interactivo).

```
CALL ancestor(tom, X)
├── CALL parent(tom, X)
│   └── EXIT parent(tom, bob) ✓
└── EXIT ancestor(tom, bob) ✓
```

## Requisitos

- Python 3.11+
- **SWI-Prolog** instalado en el sistema (`pyswip` carga su shared library vía
  ctypes; no compila nada). Verificá con `swipl --version`.

## Instalación

```bash
pip install -e .
```

## Uso

```bash
# Trace en la terminal
prologviz run examples/family.pl "ancestor(tom, X)"

# Export a HTML interactivo (árbol colapsable, con búsqueda en vivo)
prologviz run examples/family.pl "ancestor(tom, X)" --export trace.html

# Limitar la profundidad del árbol (default: 20)
prologviz run examples/family.pl "ancestor(tom, X)" --max-depth 10

# Query larga desde archivo (o '-' para stdin), sin pelear con el quoting
prologviz run examples/family.pl --query-file consulta.pl
echo "ancestor(tom, X)" | prologviz run examples/family.pl -

# Goals de preparación SIN tracear (asserts, consult, flags). Repetible con -s
prologviz run examples/dynamic.pl -s "assertz(edge(c, d))" "path(a, d)"

# Cargar muchos asserts desde un archivo (una base de conocimiento)
prologviz run examples/dynamic.pl --setup-file examples/kb.pl "path(a, e)"
```

### Sesión interactiva

Para correr **varias queries reusando el mismo estado** (sin re-asertar cada
vez), abrí una sesión. Consulta el programa y el setup una sola vez; los asserts
persisten entre queries:

```bash
prologviz session examples/dynamic.pl --setup-file examples/kb.pl
```

```
?- path(a, X)              # tracea la query
?- assertz(edge(e, f))     # muta el estado; persiste para las próximas
?- path(a, f)              # ya ve la arista nueva
?- :export ultima.html     # exporta el último árbol a HTML
?- :reset                  # recarga el programa (descarta asserts en vivo)
?- :quit                   # (o Ctrl-D) termina la sesión
```

> **Asserts**: para asertar/retraer un predicado en runtime (desde `--setup` o
> desde la propia query), el programa debe declararlo `:- dynamic`. Si no, SWI
> da `No permission to modify static procedure`. Ver `examples/dynamic.pl`.

## Arquitectura

```
prologviz/
├── cli.py              # Entry point click
├── engine/
│   ├── tracer.py       # Hook en SWI-Prolog, captura eventos
│   └── tree.py         # Modelo de datos: TraceNode, TraceTree
├── renderers/
│   ├── terminal.py     # Renderizado con rich
│   └── html.py         # Export HTML con jinja2 (TODO)
└── templates/
    └── trace.html.j2   # Template Jinja2 (TODO)
```

## Notas de implementación (SWI-Prolog + pyswip)

Captar el trace tuvo varias sutilezas que conviene documentar:

- El hook `prolog_trace_interception/4` debe definirse en el módulo **`user`**
  (no `prolog`), si no SWI usa su tracer interactivo por defecto.
- pyswip abre las queries con `PL_Q_NODEBUG` cuando `catcherrors=True` (el
  default), lo que **apaga el debugger**. Hay que pasar `catcherrors=False`.
- Se configura `leash(-all)` + `visible(+all)` para que el tracer no se detenga
  a pedir input interactivo (si no, el proceso muere con EOF).
- El wrapper `pyrun/2` de pyswip se filtra en el glue para que no aparezca.
- Las variables sin ligar se muestran como `A, B, C…` (numbervars): los nombres
  del fuente no están disponibles en runtime.

## Licencia

MIT
