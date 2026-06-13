% Ejemplo con un predicado dinámico, para probar `--setup` con asserts.
% `edge/2` se declara `:- dynamic`, así se puede modificar en runtime
% (assertz/retract) desde los goals de preparación.
%
% Usa nombres propios (edge/path) que no chocan con family.pl, porque pyswip
% comparte una única instancia de Prolog por proceso.

:- dynamic edge/2.

edge(a, b).
edge(b, c).

path(X, Y) :- edge(X, Y).
path(X, Y) :- edge(X, Z), path(Z, Y).
