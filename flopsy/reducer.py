
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

    The reducer will need to be connected to dispatch by
    specifying which state elements it affects.

    store.on_dispatch(store.MY_ACTION, [<state_element>, ...])
    """
    def __init__(self, func):
        self.func = func
        self.owning_class = None
        self.action_name = func.__name__
        self.method_name = '_' + self.action_name

    def __set_name__(self, owner, name):
        self.owning_class = owner
        setattr(owner, self.method_name, self.func)
        setattr(owner, self.action_name, self.action_name)
