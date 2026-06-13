% Programa de ejemplo para prologviz.
% Relaciones de parentesco y un predicado recursivo `ancestor/2`.

parent(tom, bob).
parent(tom, liz).
parent(bob, ann).

ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
