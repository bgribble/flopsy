import asyncio

from flopsy.store import SyncedStore
from flopsy.reducer import reducer


class StateObject(SyncedStore):
    store_attrs = ["xpos", "ypos"]
    store_type = "StateObject"
    store_id_attr = "id"

    _next_id = 1

    def __init__(self):
        self.id = StateObject._next_id
        StateObject._next_id += 1

        self.xpos = None
        self.ypos = None

        super().__init__()

    @reducer
    def CLEAR_POS(self, action, state, oldval):
        return 0

    @reducer
    def INCR_XPOS(self, action, state, oldval):
        return oldval + 1

    @reducer
    def INCR_YPOS(self, action, state, oldval):
        return oldval + 1


action_history = []
app_state = {}


async def track_state(target, action, state_diff):
    action_history.append((target, action, state_diff))

    state_key = f"{type(target).__name__}"
    state_subkey = f"{target.id}"

    type_objects = app_state.setdefault(state_key, {})
    previous_state = type_objects.setdefault(state_subkey, {})

    if previous_state:
        state_update = {
            key: value[1]
            for key, value in state_diff.items()
        }
        previous_state.update(state_update)
    else:
        previous_state.update(target.state())

    yield None


async def drip_incr_x(target, action, state_diff):
    print("drip: enter")
    for _ in range(5):
        await asyncio.sleep(1)
        print("drip: yielding INCR_YPOS")
        yield target.action(StateObject.INCR_YPOS)


StateObject.on_dispatch(StateObject.CLEAR_POS, [StateObject.XPOS, StateObject.YPOS])
StateObject.on_dispatch(StateObject.INCR_XPOS, [StateObject.XPOS])
StateObject.on_dispatch(StateObject.INCR_YPOS, [StateObject.YPOS])

StateObject.after_dispatch(
    drip_incr_x, [StateObject.XPOS]
)
StateObject.after_dispatch(track_state)
