## Flopsy: a redux-ish state management lib for Python

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

Flopsy is currently WIP. It works but there are a lot of unexplored
edges and I'm not sure where it's going to go.

### Example

Here's how you define a simple state store with all the action
creators, reducers, and interfaces needed to use it:

```python
from flopsy.store import Store
from flopsy.reducer import reducer
from flopsy.saga import saga

class MyStore(Store):

    # Magic: actions + reducers for SET_VAR_1 etc are automatically
    # created. MyStore.SET_VAR_1 is an action type, there's an
    # action creator for that type that takes a payload of "value=<newval>", and
    # there's a reducer that sets var_1 to that value; MyStore.VAR_1 is a state slice name.
    store_attrs = ['var_1', 'var_2', 'var_3']

    def __init__(self):
        self.var_1 = None
        self.var_2 = None
        self.var_3 = None

    @reducer
    def clear_state(self, action, state_name, oldval):
        # Magic: MyStore.CLEAR_STATE is an action type and a
        # reducer fragment that executes this code for the state slice
        # state_name, returning a new state value of None
        #
        # @reducer takes optional args listing which state's
        # reducers should include this code;
        # @reducer('var_1') would only clear var_1 when the
        # CLEAR_STATE action is dispatched. Default is to apply
        # it to every state var.
        return None

    @saga
    async def post_update(self, action, state_diff):
        # sagas are async generators that yield new Actions.
        # Once they are fired they can continue to yield new actions
        # which will be dispatched as they are yielded.
        #
        # Like @reducer, @saga takes args filtering for when this
        # code should be invoked. With no args, it gets run after
        # every action. With args, it only runs after a named
        # state element is changed.
        #
        # this saga does nothing, but is run after every state
        # change
        yield None

```
That's it. With no other supporting code you can do stuff like this:

```python
store = MyStore()

# store.var_1 == 1 after this
await store.action(MyStore.SET_VAR_1, value=1).dispatch()

# all store vars are None after this
await store.action(MyStore.CLEAR_STATE).dispatch()
```

My least favorite thing about Redux is the boilerplate and
profusion of type definitions, constants, action creators, and
interfaces needed to just add an action or a state variable. To
minimize this, I am leaning heavily into Python magic. Sorry if
that bothers you, I definitely understand that magic is a bad
smell for some. I think it's a fair tradeoff for the improved
developer experience.

### The inspector

My very favorite thing about Redux, maybe my favorite developer
tool of all time, is the redux-devtools state inspector for
Chrome. In flopsy, the inspector is implemented using [dear
imgui](https://github.com/ocornut/imgui/). It should be pretty
easy to integrate into any gui or console app.

You can launch it with `Store.show_inspector()`.

* *Timeline view:* The left panel is the timeline. It shows
  every action with a timestamp.
  * Click an item to time-travel the state display to that point in time.
  * Double-click to open up the action, showing the store it was targeted to, the payload, and
  the state diff that it caused.
* *Store view:* The right panel is the combined store as it was after the
  selected timeline item was dispatched.
  * "Combined store" means all of the instances of Store in the application, grouped by
  type and ID. So stores can be as big as a whole singleton app store, or as small as subclassing
  a normal object type from Store.
  * To edit the store directly: Click to select a value, edit in the input,
    click "Change". The new value will be dispatched with a `SET_FOO` action,
    which will appear in the timeline.

![Inspector screenshot](https://user-images.githubusercontent.com/1790529/233851385-7013287b-a3d1-4847-a8c2-745131e8f069.png)

