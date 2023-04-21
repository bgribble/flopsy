I like Redux and I cannot lie.

Flopsy is a state management library for Python that is heavily
inspired by Redux. It’s not a direct mapping, but the bones are
the same:

* State is represented by a *store* that has a known shape

* state changes happen through the *dispatch* of *actions* through *reducers*

* reducers don’t manipulate the store, they just compute the next
  value of a single slice of state from the action and the
  previous value of that slice

* A post-action phase allows *sagas* to view the full store after it
  is updated and dispatch more actions

My very favorite thing about Redux is the redux-dev-tools state
inspector for Chrome. This is maybe my favorite developer tool of
all time. In flopsy, the inspector is implemented using dear
imgui and allows for viewing the timeline, state-as-of time
travel, and direct dispatch of state changes from the UI. It
should be pretty easy to integrate into any gui or console app.

My least favorite thing about Redux is the boilerplate and
profusion of type definitions, constants, action creators, and
interfaces needed to just add an action or a state variable. To
minimize this, I am leaning heavily into Python magic. Sorry if
that bothers you, I definitely understand that magic is a bad
thing, but I am mostly building this tool for my own use and
enjoyment so my experience is what really matters!

Here's how you define a simple state store with all the action
creators, reducers, and interfaces needed to use it:

```
from flopsy.store import Store
from flopsy.reducer import reducer
from flopsy.saga import saga

class MyStore(Store):
    # actions + reducers for SET_VAR_1 etc are automatically created
    store_attrs = ['var_1', 'var_2', 'var_3']

    def __init__(self):
        self.var_1 = None
        self.var_2 = None
        self.var_3 = None

    @reducer
    def clear_state(self, action, state_name, oldval):
        # with no args to @reducer, called for every state element
        return None

    @saga
    async def post_update(self, action, state_diff):
        # with no args to @saga, called after every action dispatch
        yield None

```
That's it. With no other supporting code you can do stuff like this:

```
store = MyStore()

# store.var_1 == 1 after this
await store.action(MyStore.SET_VAR_1, value=1).dispatch()

# all store vars are None after this
await store.action(MyStore.CLEAR_STATE).dispatch()
```
