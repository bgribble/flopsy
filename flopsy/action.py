
class Action:
    """
    Actions change the state of the target when processed by a reducer
    """
    def __init__(self, target, type_name, payload):
        self.target = target
        self.type_name = type_name
        self.payload = payload

    def __str__(self):
        return f"<Action {self.type_name} {self.payload}>"

    def dispatch(self):
        return self.target.dispatch(self)
