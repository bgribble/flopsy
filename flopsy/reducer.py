"""
reducer.py -- @reducer and @mutates decorators for Store methods

@mutates declares that a method will mutate certain state elements.
The default SET_ reducer will be used.

@reducer declares that a method is a reducer
"""

import inspect


class mutates:
    """
    class to be used as a decorator for methods that
    directly change state. I'm not sure if I like this
    concept but I'm going to give it a try

    @mutates('myattr')
    def make_some_changes(self):
        self.myattr = newvalue

    will dispatch a SET_MYATTR action with newvalue
    IF newvalue is different from the old value
    """

    def __init__(self, *states):
        self.states = states

    async def _async_wrapper(self, target, prev_values, func_awaitable):
        retval = await func_awaitable
        for state in self.states:
            new_value = getattr(target, state)
            prev_value = prev_values.get(state, None)
            action = f'SET_{state.upper()}'
            if new_value != prev_value:
                await target.dispatch(
                    target.action(action, value=new_value),
                    previous=prev_values
                )

        return retval

    async def _async_completion_helper(self, awaitables):
        for a in awaitables:
            await a

    def _sync_wrapper(self, target, prev_values, retval):
        update_awaitables = []
        for state in self.states:
            new_value = getattr(target, state)
            prev_value = prev_values.get(state, None)
            action = f'SET_{state.upper()}'
            if new_value != prev_value:
                update_awaitables.append(
                    target.dispatch(
                        target.action(action, value=new_value),
                        previous=prev_values
                    )
                )
        target._launch_task(
            self._async_completion_helper(update_awaitables)
        )
        return retval

    def __call__(self, func):
        def wrapper(instance, *args, **kwargs):
            prev_states = {
                s: getattr(instance, s)
                for s in self.states
            }
            retval = func(instance, *args, **kwargs)
            if any(getattr(instance, s) != prev_states[s] for s in self.states):
                if inspect.isawaitable(retval):
                    return self._async_wrapper(instance, prev_states, retval)
                return self._sync_wrapper(instance, prev_states, retval)
            return retval
        return wrapper


class reducer:
    """
    class to be used as a decorator for reducer methods.
    the name of the method is used as the action name, and the
    method is reassigned to a new name with a preceding _

    @reducer
    def MY_ACTION(self, action, state, previous_value):
        # this is a reducer for MY_ACTION, the method is now
        # present on cls._MY_ACTION(), cls.MY_ACTION is now
        # the string "MY_ACTION" (the action type name)
        pass

    if the reducer has args, they are interpreted as the
    state elements to run this reducer for. If there are
    no args it will get run for any state change.
    """
    def __init__(self, *args):
        self.owning_class = None
        self.func = None
        self.states = None
        self.action_name = None
        self.method_name = None

        # if no args to @reducer
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
        else:
            self.states = args

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
            return self
        else:
            return self.func(*args, **kwargs)

    def _assign_func(self, func):
        self.func = func
        self.action_name = func.__name__.upper()
        self.method_name = '_' + self.action_name

    # __set_name__ gets called because @reducer is a "descriptor",
    # at the right time in the init process
    def __set_name__(self, owner, name):
        self.owning_class = owner
        setattr(owner, self.method_name, self.func)
        setattr(owner, self.action_name, self.action_name)

        handlers = owner._store_reducers.setdefault(self.action_name, [])

        if self.states is None:
            self.states = self.owning_class.store_attrs

        reducer_id = self.owning_class._next_reducer_id
        self.owning_class._next_reducer_id += 1
        for state in self.states:
            handlers.append((reducer_id, state, self))
