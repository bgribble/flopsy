from typing import Optional
import json
import asyncio

from flopsy.store import SyncedStore
from flopsy.reducer import reducer
from flopsy.saga import saga


class StateObject(SyncedStore):
    store_attrs = ["x", "y", "count"]
    store_type = "StateObject"

    _next_id = 1

    # store attributes
    x: Optional[int] = 0
    y: Optional[int] = 0
    count: Optional[int] = 0

    def __init__(self):
        self.id = StateObject._next_id
        StateObject._next_id += 1

        super().__init__()

    @reducer('count')
    def incr_count(self, action, state, oldval):
        return oldval + 1

    @saga('x', 'y')
    async def update_count(self, action, state_diff):
        for state_changed in state_diff.keys():
            yield self.action(StateObject.INCR_COUNT)

ss = StateObject()
inspector = ss.show_inspector()

await ss.action(StateObject.SET_X, value=1).dispatch()
await ss.action(StateObject.SET_Y, value=2).dispatch()
await asyncio.sleep(1)

print(json.dumps(ss.store(), indent=4))

