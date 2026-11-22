import asyncio
import aioconsole
from flopsy.store import Store
from flopsy.reducer import reducer
from flopsy.saga import saga


"""
Undo implemented across a multiple-store-type app

This requires a "third party" state holder that can track
actions across multiple other state repositories
"""


class UndoableStore (Store):
    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.install_reducer(UndoableStore.RESTORE_STATE, cls.store_attrs)

    @reducer
    def restore_state(self, action, state, previous):
        # INIT and DELETE will be handled in the saga
        if action.type_name in (Store.STORE_INIT, Store.STORE_DELETE):
            return previous

        trigger_type = action.payload.get("trigger").type_name
        diff = action.payload.get('state_diff')
        if state in diff:
            return diff.get(state)[0 if trigger_type == "UNDO" else 1]
        return previous



class UndoHistory(UndoableStore):
    store_attrs = ['position', 'history', 'atoms_open']

    # actions without reducers
    ERROR = "ERROR"
    UNDO = "UNDO"
    REDO = "REDO"

    def __init__(self):
        self.position = None
        self.history = []
        self.atoms_open = 0

        self.sagas = {}
        self.store_types = {}
        self.store_factories = {}

        super().__init__()

    def monitor(self, store_type, factory=None):
        self.store_types[store_type.store_type] = store_type
        self.store_factories[store_type.store_type] = factory or store_type
        self.sagas[store_type.store_type] = store_type.install_saga(
            self.store_action, on_store_init=True
        )

    async def store_action(self, store, action, state_diff, previous):
        if (
            action.type_name not in (
                UndoableStore.RESTORE_STATE, UndoHistory.UNDO, UndoHistory.REDO
            ) and action.payload.get("undoable") is not False
        ):
            yield self.action(
                self.REPLACE_HISTORY,
                value=[
                    store.store_id(), action, state_diff
                ],
                position=self.position,
                undoable=False
            )

            yield self.action(
                self.SET_POSITION,
                value=0,
                undoable=False
            )

    @saga
    async def undoable_action(self, action, state_diff, previous):
        from contextlib import aclosing
        async with aclosing(self.store_action(self, action, state_diff, previous)) as gen:
            try:
                async for item in gen:
                    yield item
            finally:
                pass

    @reducer('atoms_open')
    def atom_start(self, action, state, previous):
        return previous + 1

    @reducer('atoms_open')
    def atom_end(self, action, state, previous):
        return max(0, previous - 1)

    """
    @reducer('position')
    def undo(self, action, state, previous):
        if previous is None:
            return 1
        else:
            return previous + 1

    @reducer('position')
    def redo(self, action, state, previous):
        if previous == 0:
            return None
        else:
            return previous - 1
    """
    @reducer('history')
    def prepend_history(self, action, state, previous):
        value = action.payload.get("value")
        return [value] + previous

    @reducer('history')
    def replace_history(self, action, state, previous):
        value = action.payload.get("value")
        position = action.payload.get("position")
        return [value] + previous[position:]

    @saga
    async def undo_atom(self, action, state_diff, previous):
        from contextlib import aclosing
        if action.type_name != UndoHistory.UNDO:
            return

        actions_count = 1
        position = self.position
        atoms_open = self.atoms_open

        for hist_item in self.history[position:]:
            hist_store, hist_action, hist_diff = hist_item
            if hist_action.type_name == UndoHistory.ATOM_END:
                atoms_open += 1
            elif hist_action.type_name == UndoHistory.ATOM_START:
                atoms_open -= 1
            if atoms_open == 0:
                break
            actions_count += 1

        for loopnum in range(actions_count):
            state_diff = {'position': (position, position+1)}
            position += 1

            async with aclosing(self.undo_redo_action(action, state_diff, previous)) as gen:
                try:
                    async for item in gen:
                        yield item
                finally:
                    pass
                
            if self.atoms_open <= 0:
                keep_going = False

    @saga
    async def redo_atom(self, action, state_diff, previous):
        from contextlib import aclosing
        if action.type_name != UndoHistory.REDO:
            return

        actions_count = 1
        position = self.position - 1
        atoms_open = self.atoms_open

        for hist_item in self.history[position:0:-1]:
            hist_store, hist_action, hist_diff = hist_item
            if hist_action.type_name == UndoHistory.ATOM_END:
                atoms_open -= 1
            elif hist_action.type_name == UndoHistory.ATOM_START:
                atoms_open += 1
            if atoms_open == 0:
                break
            actions_count += 1

        for loopnum in range(actions_count):
            state_diff = {
                'position': (position-1, position)
            }
            position -= 1

            async with aclosing(self.undo_redo_action(action, state_diff, previous)) as gen:
                try:
                    async for item in gen:
                        yield item
                finally:
                    pass
                
            if self.atoms_open <= 0:
                keep_going = False

    async def undo_redo_action(self, action, state_diff, previous):
        old_position, new_position = state_diff[UndoHistory.POSITION]

        if new_position is None or new_position > len(self.history):
            return

        if action.type_name == UndoHistory.UNDO:
            hist_item = self.history[old_position]
        else:
            hist_item = self.history[new_position]

        xdo_target_id = hist_item[0]
        xdo_action = hist_item[1]
        xdo_state_diff = hist_item[2]

        xdo_target = Store.find_store(xdo_target_id)

        if action.type_name == UndoHistory.UNDO and xdo_action.type_name == Store.STORE_INIT:
            xdo_target.delete(undoable=False)
            return
        elif action.type_name == UndoHistory.REDO and xdo_action.type_name == Store.STORE_DELETE:
            xdo_target.delete(undoable=False)
            return

        if not xdo_target:
            type_id, obj_id = xdo_target_id.split(":")
            type_ctor = self.store_factories.get(type_id)
            if not type_ctor:
                return
            xdo_target = type_ctor(id=int(obj_id))
            if xdo_action.type_name == Store.STORE_DELETE:
                xdo_state_diff = xdo_action.payload.get("state_diff")

        yield xdo_target.action(
            UndoableStore.RESTORE_STATE,
            trigger=action,
            action=xdo_action,
            state_diff=xdo_state_diff
        )

        if new_position == 0 and action.type_name == UndoHistory.UNDO:
            yield self.action(
                UndoHistory.PREPEND_HISTORY,
                value=hist_item,
                undoable=False
            )
            yield self.action(
                UndoHistory.SET_POSITION,
                value=1,
                undoable=False
            )
        else:
            yield self.action(
                UndoHistory.SET_POSITION,
                value=new_position,
                undoable=False
            )

    @saga
    async def mk_error(self, action, state_diff, previous):
        if action.type_name == UndoHistory.ERROR:
            raise ValueError
        yield


class Address (UndoableStore):
    store_attrs = ['street', 'city', 'addr_state', 'zipcode']

    def __init__(self, *args, **kwargs):
        self.street = None
        self.city = None
        self.addr_state = None
        self.zipcode = None

        super().__init__(*args, **kwargs)


class Phone (UndoableStore):
    store_attrs = ['phone']

    def __init__(self, *args, **kwargs):
        self.phone = None
        super().__init__(*args, **kwargs)

def create_address(*args, **kwargs):
    return Address(*args, **kwargs)


async def main():
    Store.setup_asyncio()
    Store.show_inspector()
    await asyncio.sleep(0.5)

    store_types = {
        "UndoHistory": UndoHistory,
        "Address": Address,
        "Phone": Phone
    }

    time_to_quit = False

    history = UndoHistory()
    history.monitor(Address, factory=create_address)
    history.monitor(Phone)

    while not time_to_quit:
        line = await aioconsole.ainput(">>> ")
        line = line.strip()

        if line == '':
            continue
        elif line == "q":
            time_to_quit = True
        elif line == "i":
            Store.show_inspector()
        elif line.startswith("create"):
            clsobj = store_types.get(line.split(' ')[1])
            if clsobj:
                new_store = clsobj()
                print(new_store.store_id())
        elif line.startswith("delete"):
            store_id = line.split(' ')[1]
            store = Store.find_store(store_id)
            store.delete()
        elif line.startswith("set"):
            store_id, field, value = line.split(" ", 3)[1:]
            store = Store.find_store(store_id)
            await store.dispatch_setter(field, value)
        elif line.startswith("get"):
            store_id, field = line.split(" ", 2)[1:]
            store = Store.find_store(store_id)
            svars = ', '.join(f"{a}: {getattr(store, a)}" for a in store.store_attrs)
            print(f"id={store_id} field={field} store={{{svars}}}")
            print(f"{getattr(store, field)}")
        elif line.startswith("show") and " " in line:
            store_type = line.split(" ")[1]
            if ":" in store_type:
                store_objs = {
                    store_type: Store.find_store(store_type)
                }
            else:
                store_objs = Store._store_registry.get(store_type)

            for store_id, val in store_objs.items():
                svars = ', '.join(f"{a}: {getattr(val, a)}" for a in val.store_attrs)
                print(f"  {store_id} --> {{{svars}}}")
        elif line.startswith("atom"):
            parts = line.split(' ')
            if len(parts) == 1 or (len(parts) > 1 and parts[1] == "start"):
                print("atom: starting block")
                await history.action(UndoHistory.ATOM_START).dispatch()
            elif len(parts) > 1 and parts[1] == "end":
                print("atom: ending block")
                await history.action(UndoHistory.ATOM_END).dispatch()
        elif line == "undo":
            await history.action(UndoHistory.UNDO).dispatch()
        elif line == "redo":
            await history.action(UndoHistory.REDO).dispatch()
        elif line == "error":
            await history.action(UndoHistory.ERROR).dispatch()
        else:
            print(f"Can't find command in '{line}'")
        await asyncio.sleep(0.1)

    print("Got quit, good bye!")

if __name__ == "__main__":
    asyncio.run(main())
