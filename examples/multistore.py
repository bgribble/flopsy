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

class UndoHistory(Store):
    store_attrs = ['position', 'history']

    # actions without reducers
    ERROR = "ERROR"

    def __init__(self):
        self.position = None
        self.history = []

        self.sagas = {}
        self.store_types = {}
        super().__init__()

    def monitor(self, store_type):
        self.store_types[store_type.store_type] = store_type
        self.sagas[store_type.store_type] = store_type.install_saga(
            self.undoable_action, on_store_init=True
        )

    async def undoable_action(self, store, action, state_diff, previous):
        if (
            action.type_name != UndoableStore.RESTORE_STATE
            and action.payload.get("undoable") != False
        ):
            self.history[:self.position] = [[
                store.store_id(), action, state_diff
            ]]
            self.position = 0

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

    @reducer('history')
    def prepend_history(self, action, state, previous):
        value = action.payload.get("value")
        return [value] + previous

    @reducer('history')
    def prune_history(self, action, state, previous):
        value = action.payload.get("value")
        position = action.payload.get("position")
        return [value] + previous[position:]

    @saga('position')
    async def handle_undo_redo(self, action, state_diff, previous):
        if action.type_name in (UndoHistory.UNDO, UndoHistory.REDO):
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
                type_ctor = self.store_types.get(type_id)
                if not type_ctor:
                    return
                xdo_target = type_ctor(id=int(obj_id))
                if xdo_action.type_name == Store.STORE_DELETE:
                    xdo_state_diff = xdo_action.payload.get("state_diff")

            yield xdo_target.action(
                UndoableStore.RESTORE_STATE,
                action=xdo_action,
                state_diff=xdo_state_diff
            )

            if new_position == 0 and action.type_name == UndoHistory.UNDO:
                yield self.action(
                    UndoHistory.PREPEND_HISTORY,
                    value=hist_item
                )
                yield self.action(
                    UndoHistory.SET_POSITION,
                    value=1
                )

    @saga
    async def mk_error(self, action, state_diff, previous):
        if action.type_name == UndoHistory.ERROR:
            raise ValueError
        yield


class UndoableStore (Store):
    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.install_reducer(UndoableStore.RESTORE_STATE, cls.store_attrs)

    @reducer
    def restore_state(self, action, state, previous):
        if action.type_name == Store.STORE_INIT:
            pass
        elif action.type_name == Store.STORE_DELETE:
            pass
        else:
            diff = action.payload.get('state_diff')
            if state in diff:
                return diff.get(state)[0]
        return previous


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
    history.monitor(Address)
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
