"""Tests del CLI (`cli.py`).

La resolución de la query (argumento / --query-file / stdin) y la validación se
testean sin Prolog usando el `CliRunner` de click; los flujos que ejecutan
Prolog de verdad van marcados con @requires_prolog.
"""

from __future__ import annotations

from click.testing import CliRunner

from prologviz.cli import cli

from .conftest import FAMILY_PL, requires_prolog

FAMILY = str(FAMILY_PL)


# --------------------------------------------- validación (sin Prolog)

def test_falta_query_es_error():
    result = CliRunner().invoke(cli, ["run", FAMILY])
    assert result.exit_code != 0
    assert "Falta la query" in result.output


def test_query_y_query_file_juntas_es_error(tmp_path):
    qf = tmp_path / "q.pl"
    qf.write_text("foo(X).", encoding="utf-8")
    result = CliRunner().invoke(cli, ["run", FAMILY, "foo(X)", "-q", str(qf)])
    assert result.exit_code != 0
    assert "no ambos" in result.output


def test_query_vacia_es_error(tmp_path):
    qf = tmp_path / "vacio.pl"
    qf.write_text("   \n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["run", FAMILY, "-q", str(qf)])
    assert result.exit_code != 0
    assert "vacía" in result.output


def test_programa_inexistente_es_error():
    result = CliRunner().invoke(cli, ["run", "no_existe.pl", "foo(X)"])
    assert result.exit_code != 0


# --------------------------------------------- ejecución real (con Prolog)

@requires_prolog
def test_run_basico():
    result = CliRunner().invoke(cli, ["run", FAMILY, "ancestor(tom, X)"])
    assert result.exit_code == 0, result.output
    assert "Soluciones" in result.output
    assert "X = bob" in result.output


@requires_prolog
def test_query_desde_archivo(tmp_path):
    qf = tmp_path / "q.pl"
    qf.write_text("parent(tom, X)", encoding="utf-8")
    result = CliRunner().invoke(cli, ["run", FAMILY, "--query-file", str(qf)])
    assert result.exit_code == 0, result.output
    assert "X = bob" in result.output


@requires_prolog
def test_query_desde_stdin():
    result = CliRunner().invoke(
        cli, ["run", FAMILY, "-"], input="parent(tom, X)\n"
    )
    assert result.exit_code == 0, result.output
    assert "X = bob" in result.output


@requires_prolog
def test_setup_con_assert():
    # dynamic.pl declara edge/2 dinámico -> se puede asertar en --setup.
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    result = CliRunner().invoke(
        cli,
        ["run", dynamic_pl, "-s", "assertz(edge(c, d))", "path(a, d)"],
    )
    assert result.exit_code == 0, result.output
    # la query ground tuvo éxito gracias a la arista asertada (a->b->c->d)
    assert "true" in result.output


@requires_prolog
def test_export_genera_html(tmp_path):
    out = tmp_path / "t.html"
    result = CliRunner().invoke(
        cli, ["run", FAMILY, "ancestor(tom, X)", "-e", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "HTML exportado" in result.output


@requires_prolog
def test_run_setup_file(tmp_path):
    kb = tmp_path / "kb.pl"
    kb.write_text("assertz(edge(c, d)).\n", encoding="utf-8")
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    result = CliRunner().invoke(
        cli, ["run", dynamic_pl, "--setup-file", str(kb), "path(a, d)"]
    )
    assert result.exit_code == 0, result.output
    assert "true" in result.output


# --------------------------------------------- sesión (REPL, con Prolog)

@requires_prolog
def test_session_varias_queries_comparten_estado():
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    # Aserto edge(c,d) en vivo; la query siguiente debe verla (estado persiste).
    entrada = "assertz(edge(c, d))\npath(a, d)\n:quit\n"
    result = CliRunner().invoke(cli, ["session", dynamic_pl], input=entrada)
    assert result.exit_code == 0, result.output
    assert "hecho" in result.output      # confirmación del assert
    assert "true" in result.output       # path(a, d) tuvo éxito gracias al assert
    assert "Sesión terminada" in result.output


@requires_prolog
def test_session_setup_file_se_carga_una_vez(tmp_path):
    kb = tmp_path / "kb.pl"
    kb.write_text("assertz(edge(c, d)).\nassertz(edge(d, e)).\n", encoding="utf-8")
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    # Sin re-asertar nada, la query usa los hechos del setup-file.
    result = CliRunner().invoke(
        cli, ["session", dynamic_pl, "--setup-file", str(kb)], input="path(a, X)\n:quit\n"
    )
    assert result.exit_code == 0, result.output
    assert "goals de setup" in result.output  # el banner reporta el setup cargado
    assert "X = e" in result.output      # a->b->c->d->e alcanzable


@requires_prolog
def test_session_export(tmp_path):
    out = tmp_path / "s.html"
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    entrada = f"path(a, b)\n:export {out}\n:quit\n"
    result = CliRunner().invoke(cli, ["session", dynamic_pl], input=entrada)
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "HTML exportado" in result.output


@requires_prolog
def test_session_comando_invalido_no_corta():
    dynamic_pl = str(FAMILY_PL.parent / "dynamic.pl")
    result = CliRunner().invoke(
        cli, ["session", dynamic_pl], input=":nope\npath(a, b)\n:quit\n"
    )
    assert result.exit_code == 0, result.output
    assert "comando desconocido" in result.output
    # tras el comando inválido la sesión sigue y procesa la query
    assert "Soluciones" in result.output
