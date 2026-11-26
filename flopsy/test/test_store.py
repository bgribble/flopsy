import threading
import asyncio
from unittest import IsolatedAsyncioTestCase

from flopsy.action import Action
from flopsy.reducer import reducer
from flopsy.saga import saga
from flopsy.store import Store, SyncedStore


class StoreTest(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        Store.flush_registry()
        Store.setup_asyncio()

    async def test_store_type(self):
        class Address(Store):
            store_attrs = ['street', 'addr_state', 'city', 'zipcode']
            def __init__(self):
                self.street = None
                self.addr_state = None
                self.city = None
                self.zipcode = None
                super().__init__()

        self.assertEqual(Store._store_types, {'Address': Address})

        a = Address()
        self.assertEqual(
            list(Store._store_registry.keys()),
            ['Address']
        )

        self.assertEqual(
            list(Store._store_registry['Address'].keys()),
            ['1']
        )

        self.assertEqual(
            Store._store_registry['Address']['1'],
            a
        )

        await a.dispatch_setter(Address.STREET, "123 Main St")
        await a.dispatch_setter(Address.ADDR_STATE, "New York")
        await a.dispatch_setter(Address.CITY, "Brooklyn")
        await a.dispatch_setter(Address.ZIPCODE, "11111")

        self.assertEqual(a.street, "123 Main St")
        self.assertEqual(a.addr_state, "New York")
        self.assertEqual(a.city, "Brooklyn")
        self.assertEqual(a.zipcode, "11111")

        await Store.drain_tasks()
        return None

    async def test_auto_action_symbols(self):
        class Address(Store):
            store_attrs = ['street', 'city']
            def __init__(self, *args, **kwargs):
                self.street = None
                self.city = None
                super().__init__(*args, **kwargs)

        self.assertEqual(Address.STREET, 'street')
        self.assertEqual(Address.CITY, 'city')
        self.assertEqual(Address.SET_STREET, 'SET_STREET')
        self.assertEqual(Address.SET_CITY, 'SET_CITY')
        self.assertTrue(hasattr(Address, '_SET_STREET'))
        self.assertTrue(hasattr(Address, '_SET_CITY'))

    async def test_custom_reducer(self):
        class Counter(Store):
            store_attrs = ['count']
            def __init__(self, *args, **kwargs):
                self.count = 0
                super().__init__(*args, **kwargs)

            @reducer('count')
            def add_from_previous(self, action, state, oldval):
                return oldval + action.payload.get('value', 0)

        c = Counter(id=1)
        await c.dispatch(
            Action(c, Counter.ADD_FROM_PREVIOUS, dict(value=3)),
            previous={'count': 7}
        )
        await Store.drain_tasks()
        self.assertEqual(c.count, 10)

    async def test_saga_updates_state(self):
        class Ledger(Store):
            store_attrs = ['entries', 'last']
            def __init__(self, *args, **kwargs):
                self.entries = []
                self.last = None
                super().__init__(*args, **kwargs)

            @saga('entries')
            async def log_entry(self, action, state_diff, previous):
                if action.type_name == Ledger.SET_ENTRIES:
                    yield self.action(
                        Ledger.SET_LAST,
                        value=state_diff[Ledger.ENTRIES][1]
                    )

        l = Ledger(id=1)
        await l.dispatch_setter(Ledger.ENTRIES, ['first'])
        await Store.drain_tasks()
        self.assertEqual(l.last, ['first'])

    async def test_saga_only_runs_on_matching_state(self):
        class Tracker(Store):
            store_attrs = ['a', 'b']
            def __init__(self, *args, **kwargs):
                self.a = 0
                self.b = 0
                self.calls = 0
                super().__init__(*args, **kwargs)

            @saga('a')
            async def only_a(self, action, state_diff, previous):
                self.calls += 1
                yield None

        t = Tracker(id=1)
        await t.dispatch_setter('a', 1)
        await t.dispatch_setter('b', 2)
        await Store.drain_tasks()
        self.assertEqual(t.calls, 1)

    async def test_store_id_and_find_store(self):
        class Point(Store):
            store_attrs = ['x', 'y']
            def __init__(self, *args, **kwargs):
                self.x = 0
                self.y = 0
                super().__init__(*args, **kwargs)

        p1 = Point(id=10)
        p2 = Point(id=20)
        pid1 = p1.store_id()
        pid2 = p2.store_id()
        self.assertEqual(pid1.split(':')[0], 'Point')
        self.assertEqual(pid2.split(':')[0], 'Point')
        self.assertNotEqual(pid1, pid2)
        self.assertIs(Store.find_store(pid1), p1)
        self.assertIs(Store.find_store(pid2), p2)
        self.assertEqual(len(Store.all_stores()), 2)
        self.assertIn(Point, Store.all_store_types())

    async def test_delete_removes_from_registry(self):
        class Point(Store):
            store_attrs = ['x']
            def __init__(self, *args, **kwargs):
                self.x = 0
                super().__init__(*args, **kwargs)

        p = Point(id=1)
        pid = p.store_id()
        self.assertIs(Store.find_store(pid), p)
        await p.delete()
        await Store.drain_tasks()
        self.assertIsNone(Store.find_store(pid))

    async def test_synced_store_actions(self):
        class Card(SyncedStore):
            store_attrs = ['balance']
            def __init__(self, *args, **kwargs):
                self.balance = 0
                super().__init__(*args, **kwargs)

        self.assertTrue(hasattr(Card, 'SYNC_BALANCE'))
        self.assertTrue(hasattr(Card, '_SYNC_BALANCE'))
        c = Card(id=1)
        await c.dispatch(Action(c, Card.SYNC_BALANCE, dict(value=7)))
        await Store.drain_tasks()
        self.assertEqual(c.balance, 7)

    async def test_state_method(self):
        class Address(Store):
            store_attrs = ['street', 'city']
            def __init__(self, *args, **kwargs):
                self.street = 'Main'
                self.city = 'Brooklyn'
                super().__init__(*args, **kwargs)

        a = Address(id=1)
        self.assertEqual(a.state(), {'street': 'Main', 'city': 'Brooklyn'})
        self.assertEqual(a.state('street'), 'Main')

    async def test_uninstall_reducer_disables_action(self):
        class Counter(Store):
            store_attrs = ['count']
            def __init__(self, *args, **kwargs):
                self.count = 0
                super().__init__(*args, **kwargs)

            @reducer('count')
            def increment(self, action, state, oldval):
                return oldval + 1

        c = Counter(id=1)
        await c.dispatch(Action(c, Counter.INCREMENT, {}))
        await Store.drain_tasks()
        self.assertEqual(c.count, 1)

        Counter.uninstall_reducer(Counter.INCREMENT, 1)
        self.assertEqual(Counter._store_reducers[Counter.INCREMENT], [])
        await Store.drain_tasks()
        self.assertEqual(c.count, 1)


class ActionTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Store.flush_registry()
        Store.setup_asyncio()

    async def test_action_attributes_and_str(self):
        class Dummy(Store):
            store_attrs = ['v']
            def __init__(self, *args, **kwargs):
                self.v = 1
                super().__init__(*args, **kwargs)

        d = Dummy(id=1)
        action = Action(d, 'TEST_ACTION', {'key': 'val'})
        self.assertIs(action.target, d)
        self.assertEqual(action.type_name, 'TEST_ACTION')
        self.assertEqual(action.payload, {'key': 'val'})
        self.assertIn('TEST_ACTION', str(action))
        self.assertIn('TEST_ACTION', repr(action))
        self.assertIn("key", repr(action))

    async def test_action_dispatch(self):
        class Dummy(Store):
            store_attrs = ['v']
            def __init__(self, *args, **kwargs):
                self.v = 0
                super().__init__(*args, **kwargs)

        d = Dummy(id=1)
        action = Action(d, 'SET_V', dict(value=9))
        await action.dispatch()
        self.assertEqual(d.v, 9)
