import asyncio
import aioconsole
from flopsy.store import Store
from flopsy.reducer import reducer
from flopsy.saga import saga


class UndoableState(Store):
    store_attrs = ['val', 'undo_position', 'undo_history']

    # actions without reducers
    ERROR = "ERROR"

    def __init__(self):
        self.val = ""
        self.undo_position = None
        self.undo_history = []

        super().__init__()

    @reducer('undo_position')
    def undo(self, action, state, oldval):
        if oldval is None:
            return 1
        else:
            return oldval + 1

    @reducer('undo_position')
    def redo(self, action, state, oldval):
        if oldval == 0:
            return None
        else:
            return oldval - 1

    @reducer('val')
    def set_silently(self, action, state, oldval):
        return action.payload.get('value')

    @reducer('undo_history')
    def prepend_undo_history(self, action, state, oldval):
        value = action.payload.get("value")
        return [value] + oldval

    @reducer('undo_history')
    def prune_undo_history(self, action, state, oldval):
        value = action.payload.get("value")
        position = action.payload.get("position")
        return [value] + oldval[position:]

    @saga('val')
    async def update_history(self, action, state_diff):
        if action.type_name != UndoableState.SET_SILENTLY:
            if self.undo_position is None:
                yield self.action(
                    UndoableState.PREPEND_UNDO_HISTORY,
                    value=state_diff[UndoableState.VAL][1]
                )
            else:
                yield self.action(
                    UndoableState.PRUNE_UNDO_HISTORY,
                    position=self.undo_position,
                    value=state_diff[UndoableState.VAL][1]
                )
                yield self.action(
                    UndoableState.SET_UNDO_POSITION,
                    value=None
                )

    @saga('undo_position')
    async def handle_undo_redo(self, action, state_diff):
        if action.type_name in (UndoableState.UNDO, UndoableState.REDO):
            new_position = state_diff[UndoableState.UNDO_POSITION][1]

            if new_position is None or new_position > len(self.undo_history):
                return

            yield self.action(
                UndoableState.SET_SILENTLY,
                value=self.undo_history[new_position]
            )

            if new_position == 0 and action.type_name == UndoableState.UNDO:
                yield self.action(
                    UndoableState.PREPEND_UNDO_HISTORY,
                    value=self.val
                )
                yield self.action(
                    UndoableState.SET_UNDO_POSITION,
                    value=1
                )

    @saga
    async def mk_error(self, action, state_diff):
        if action.type_name == UndoableState.ERROR:
            raise ValueError
        yield

async def main():
    Store.show_inspector()
    await asyncio.sleep(0.5)
    store = UndoableState()

    time_to_quit = False

    print()
    print("Enter a value to change the stored state")
    print("Enter '!error' to generate an error, '!undo' to undo, '!redo' to redo, '!i' to show inspector, '!q' to quit\n")

    while not time_to_quit:
        print(f"current state: '{store.val}'")

        line = await aioconsole.ainput(">>> ")
        line = line.strip()

        if line == '':
            continue
        elif line == "!q":
            time_to_quit = True
        elif line == "!i":
            Store.show_inspector()
        elif line == "!undo":
            await store.action(UndoableState.UNDO).dispatch()
        elif line == "!redo":
            await store.action(UndoableState.REDO).dispatch()
        elif line == "!error":
            await store.action(UndoableState.ERROR).dispatch()
        else:
            await store.action(UndoableState.SET_VAL, value=line).dispatch()

        await asyncio.sleep(0.1)

    print("Got quit, good bye!")

if __name__ == "__main__":
    asyncio.run(main())




