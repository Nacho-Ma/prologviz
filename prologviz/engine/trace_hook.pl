% Glue de trace para prologviz.
%
% Define el hook `prolog:prolog_trace_interception/4`, que SWI-Prolog invoca en
% cada puerto del trace cuando el thread está en modo trace. Extrae el goal, su
% profundidad y el puerto, y se los pasa ya normalizados (strings) a la función
% Python `pyviz_event/4` (registrada vía pyswip con registerForeign).
%
% Devolvemos siempre la acción `continue` para que la ejecución no se detenga a
% pedir input interactivo.

:- multifile user:prolog_trace_interception/4.

user:prolog_trace_interception(Port, Frame, _Choice, continue) :-
    ignore(user:'$pyviz_capture'(Port, Frame)).

% Captura un evento de un puerto que nos interesa, perteneciente a un predicado
% definido por el usuario (módulo `user`, no built-in). El resto se ignora.
'$pyviz_capture'(Port0, Frame) :-
    '$pyviz_port_name'(Port0, Port),
    '$pyviz_wanted_port'(Port),
    prolog_frame_attribute(Frame, goal, Goal0),
    strip_module(Goal0, Module, Goal),
    Module == user,
    \+ predicate_property(Goal, built_in),
    \+ '$pyviz_internal'(Goal),
    prolog_frame_attribute(Frame, level, Depth),
    '$pyviz_render'(Goal, Pred, Packed),
    pyviz_event(Port, Pred, Packed, Depth).

% El puerto puede venir como átomo (call) o como término compuesto (redo(PC)).
'$pyviz_port_name'(Port, Name) :-
    ( atom(Port) -> Name = Port ; functor(Port, Name, _) ).

'$pyviz_wanted_port'(call).
'$pyviz_wanted_port'(exit).
'$pyviz_wanted_port'(fail).
'$pyviz_wanted_port'(redo).

% Goals internos que NO queremos en el árbol: el wrapper `pyrun/2` con que
% pyswip ejecuta cada query, y cualquier predicado propio del glue ($pyviz_*).
'$pyviz_internal'(pyrun(_, _)).
'$pyviz_internal'(Goal) :-
    functor(Goal, Name, _),
    sub_atom(Name, 0, _, _, '$pyviz').

% Renderiza el goal a (Predicado, ArgsEmpaquetados). Los argumentos se separan
% con el carácter de control US (0x1F) para reconstruirlos del lado de Python.
% numbervars sobre una copia convierte las variables sin ligar en A, B, C...,
% más legibles que los _G123 internos de Prolog.
'$pyviz_render'(Goal, Pred, Packed) :-
    copy_term(Goal, G),
    numbervars(G, 0, _),
    ( compound(G)
    -> G =.. [Pred|Args]
    ;  Pred = G, Args = []
    ),
    maplist('$pyviz_arg_string', Args, ArgStrs),
    ( ArgStrs == []
    -> Packed = ''
    ;  atomic_list_concat(ArgStrs, '\x1f\', Packed)
    ).

'$pyviz_arg_string'(Arg, S) :-
    term_string(Arg, S, [numbervars(true)]).
