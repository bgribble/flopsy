from typing import Optional
import asyncio

from flopsy.store import SyncedStore
from flopsy.reducer import reducer
from flopsy.saga import saga


class StateObject(SyncedStore):
    store_attrs = ["xpos", "ypos"]
    store_type = "StateObject"
    store_id_attr = "id"

    _next_id = 1

    # store attributes
    xpos: Optional[int] = None
    ypos: Optional[int] = None

    def __init__(self):
        self.id = StateObject._next_id
        StateObject._next_id += 1

        super().__init__()

    @reducer
    def clear_pos(self, action, state, oldval):
        return 0

    @reducer('xpos')
    def incr_xpos(self, action, state, oldval):
        return oldval + 1

    @reducer('ypos')
    def incr_ypos(self, action, state, oldval):
        return oldval + 1

    @saga('xpos')
    async def drip_incr_x(self, action, state_diff):
        for _ in range(5):
            await asyncio.sleep(1)
            yield self.action(StateObject.INCR_YPOS)


ss = StateObject()
inspector = ss.show_inspector()

await ss.action(StateObject.CLEAR_POS).dispatch()

for i in range(20):
    await asyncio.sleep(1)
    await ss.action(StateObject.INCR_YPOS).dispatch()

