import threading
import asyncio
from unittest import IsolatedAsyncioTestCase

from flopsy.store import Store


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


