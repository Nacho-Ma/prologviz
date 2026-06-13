"""Entry point de la CLI de prologviz (click)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import click

from prologviz import __version__

if TYPE_CHECKING:
    from prologviz.engine.tree import TraceTree


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="prologviz")
def cli() -> None:
    """prologviz — visualiza el árbol de resolución de programas Prolog."""


def _resolve_query(query: str | None, query_file) -> str:
    """Resuelve la query desde el argumento posicional o desde --query-file.

    Exige exactamente una de las dos fuentes y que la query no quede vacía.
    """
    if query is not None and query_file is not None:
        raise click.UsageError(
            "Indicá la query como argumento O con --query-file, no ambos."
        )
    if query is None and query_file is None:
        raise click.UsageError(
            "Falta la query: pasala como argumento o con --query-file/'-' (stdin)."
        )

    if query == "-":
        # '-' como argumento posicional también significa "leer de stdin".
        text = sys.stdin.read()
    elif query is not None:
        text = query
    else:
        text = query_file.read()
    text = text.strip()
    if not text:
        raise click.UsageError("La query está vacía.")
    return text


def _collect_setup(setup_goals: tuple[str, ...], setup_file: str | None) -> list[str]:
    """Combina los goals de `-s` con los del archivo `--setup-file` (en ese orden)."""
    goals = list(setup_goals)
    if setup_file:
        from prologviz.engine.tracer import parse_setup_file

        goals.extend(parse_setup_file(setup_file))
    return goals


# Decorador compartido por `run` y `session` para las opciones de setup.
def _setup_options(func):
    func = click.option(
        "-s", "--setup",
        "setup_goals",
        multiple=True,
        metavar="GOAL",
        help="Goal de preparación a correr ANTES y SIN tracear (asserts, consult, "
             "flags). Repetible. Para asertar, el predicado debe ser ':- dynamic'.",
    )(func)
    func = click.option(
        "--setup-file",
        type=click.Path(exists=True, dir_okay=False),
        metavar="ARCHIVO",
        help="Archivo con goals de preparación (uno por línea). Cómodo para "
             "cargar muchos asserts de una base de conocimiento.",
    )(func)
    return func


@cli.command()
@click.argument("program", type=click.Path(exists=True, dir_okay=False))
@click.argument("query", required=False)
@click.option(
    "-q", "--query-file",
    type=click.File("r", encoding="utf-8"),
    metavar="ARCHIVO",
    help="Lee la query desde un archivo (o '-' para stdin). Útil para queries "
         "largas o multilínea, sin pelear con el quoting del shell.",
)
@_setup_options
@click.option(
    "-e", "--export",
    type=click.Path(dir_okay=False),
    metavar="ARCHIVO.html",
    help="Exporta el trace a un HTML interactivo (colapsable, con búsqueda).",
)
@click.option(
    "--max-depth",
    type=int,
    default=20,
    show_default=True,
    help="Profundidad máxima de eventos a capturar.",
)
@click.option(
    "--max-solutions",
    type=int,
    default=None,
    help="Tope de soluciones a enumerar (default: todas).",
)
def run(
    program: str,
    query: str | None,
    query_file,
    setup_goals: tuple[str, ...],
    setup_file: str | None,
    export: str | None,
    max_depth: int,
    max_solutions: int | None,
) -> None:
    """Corre QUERY sobre PROGRAM y muestra su árbol de resolución.

    QUERY puede darse como argumento posicional o, para queries largas, con
    --query-file (o '-' para leer de stdin).

    \b
    Ejemplos:
      prologviz run family.pl "ancestor(tom, X)"
      prologviz run family.pl "ancestor(tom, X)" --export trace.html
      prologviz run family.pl --query-file consulta.pl
      prologviz run family.pl -s "assertz(parent(bob,kid))" "ancestor(tom,kid)"
    """
    # Imports diferidos: así `--help` y `--version` no requieren SWI-Prolog.
    from prologviz.engine.tracer import Tracer
    from prologviz.renderers import terminal

    query = _resolve_query(query, query_file)
    setup = _collect_setup(setup_goals, setup_file)

    try:
        tracer = Tracer(
            program,
            query,
            max_depth=max_depth,
            max_solutions=max_solutions,
            setup_goals=setup,
        )
        tree = tracer.run()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - feedback amigable ante errores de Prolog
        raise click.ClickException(
            f"Error al ejecutar la query en SWI-Prolog: {exc}"
        ) from exc

    terminal.render(tree, query=query, solutions=tracer.solutions)

    if export:
        from prologviz.renderers import html

        out = html.export_html(
            tree, export, query=query, solutions=tracer.solutions
        )
        click.echo(
            click.style(f"\nHTML exportado a {out}", fg="green")
        )


_SESSION_HELP = """\
  Comandos de la sesión:
    <query>            tracea una query contra el estado actual
    assertz(...)/...   muta el estado (persiste para las próximas queries)
    :export ARCHIVO    exporta el último árbol traceado a HTML
    :reset             recarga el programa (descarta los asserts en vivo)
    :help              muestra esta ayuda
    :quit  (o Ctrl-D)  termina la sesión"""


@dataclass
class _LastTrace:
    """Último trace de la sesión, para el comando :export."""

    tree: "TraceTree | None" = None
    query: str | None = None
    solutions: "list[dict[str, str]] | None" = None


def _handle_session_command(line, session, console, last: _LastTrace) -> bool:
    """Procesa un comando ':...'. Devuelve True si hay que terminar la sesión."""
    parts = line.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in (":quit", ":q", ":exit"):
        return True
    if cmd in (":help", ":h"):
        console.print(_SESSION_HELP, style="dim")
    elif cmd == ":reset":
        session.reset()
        console.print("  estado recargado (asserts en vivo descartados)", style="yellow")
    elif cmd == ":export":
        if not arg:
            console.print("  uso: :export archivo.html", style="red")
        elif last.tree is None:
            console.print("  todavía no traceaste ninguna query", style="red")
        else:
            from prologviz.renderers import html

            out = html.export_html(
                last.tree, arg, query=last.query, solutions=last.solutions
            )
            console.print(f"  HTML exportado a {out}", style="green")
    else:
        console.print(f"  comando desconocido: {cmd}  (:help para la lista)", style="red")
    return False


def _run_session_repl(session, console) -> None:
    """Loop principal de la sesión: lee líneas, tracea queries, ejecuta comandos."""
    from prologviz.renderers import terminal

    # Marca ASCII-safe en consolas que no soportan Unicode (cp1252 en Windows).
    done = "✓ hecho" if terminal._supports_unicode() else "[OK] hecho"
    last = _LastTrace()  # último árbol traceado (para :export)
    while True:
        console.print("?- ", end="", style="bold magenta")
        line = sys.stdin.readline()
        if not line:  # EOF (Ctrl-D)
            break
        line = line.strip()
        if not line:
            continue

        if line.startswith(":"):
            try:
                if _handle_session_command(line, session, console, last):
                    break
            except Exception as exc:  # noqa: BLE001 - un comando que falla no corta la sesión
                console.print(f"  error: {exc}", style="red")
            continue

        # Es una query (o una mutación tipo assertz).
        try:
            tree, solutions = session.trace_query(line)
        except KeyboardInterrupt:
            console.print("  (cancelada)", style="yellow")
            continue
        except Exception as exc:  # noqa: BLE001 - errores de Prolog vuelven al prompt
            console.print(f"  error: {exc}", style="red")
            continue

        if not tree.roots:
            # Sin goals de usuario (p. ej. un assertz): fue una mutación del estado.
            if solutions:
                console.print(f"  {done} (estado actualizado)", style="green")
            else:
                console.print("  false.", style="red")
        else:
            # query=None: el goal ya está en el prompt, no repetir el título.
            terminal.render(tree, query=None, solutions=solutions, console=console)
            last.tree, last.query, last.solutions = tree, line, solutions

    console.print("\nSesión terminada.", style="dim")


@cli.command()
@click.argument("program", type=click.Path(exists=True, dir_okay=False))
@_setup_options
@click.option(
    "--max-depth",
    type=int,
    default=20,
    show_default=True,
    help="Profundidad máxima de eventos a capturar por query.",
)
def session(
    program: str,
    setup_goals: tuple[str, ...],
    setup_file: str | None,
    max_depth: int,
) -> None:
    """Abre una sesión interactiva sobre PROGRAM.

    Consulta el programa y los goals de preparación UNA vez, y deja un prompt
    para tracear varias queries reusando el mismo estado (los asserts persisten
    entre queries). Ideal para una base de conocimiento con muchos asserts.

    \b
    Ejemplo:
      prologviz session examples/dynamic.pl --setup-file kb.pl
      ?- path(a, X)
      ?- :export ultima.html
      ?- :quit
    """
    from rich.console import Console

    from prologviz.engine.tracer import Session

    setup = _collect_setup(setup_goals, setup_file)
    sess = Session(program, max_depth=max_depth, setup_goals=setup)
    try:
        sess.start()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - feedback amigable
        raise click.ClickException(f"Error al iniciar la sesión: {exc}") from exc

    console = Console()
    n = len(setup)
    detalle = f" · {n} goal{'s' if n != 1 else ''} de setup" if n else ""
    console.print(
        f"[bold magenta]prologviz[/] · sesión sobre [cyan]{program}[/]{detalle}"
    )
    console.print("Escribí una query (sin punto final). [dim]:help[/] para los comandos.\n")
    _run_session_repl(sess, console)


def main() -> None:  # pragma: no cover - thin wrapper
    """Permite ejecutar `python -m prologviz` además del script `prologviz`."""
    cli()


if __name__ == "__main__":
    sys.exit(cli())
