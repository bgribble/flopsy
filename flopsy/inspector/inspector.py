#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import json
import copy
from datetime import datetime
from threading import Thread
from imgui.integrations.glfw import GlfwRenderer
import OpenGL.GL as gl
import glfw
import imgui
from flopsy.action import Action
from flopsy.store import Store


class Inspector(Thread):
    def __init__(self, *, width=800, height=600):
        super().__init__()
        self.window_name = "Flopsy inspector"
        self.window_width = width
        self.window_height = height

        self.timeline_item_selected = None
        self.store_item_selected = None
        self.store_item_selected_value = None

        self.sagas = {}
        self.timeline = []

        self.event_loop = asyncio.get_event_loop()

        self.initial_store = Store.store()
        self.initial_store_ts = datetime.now()
        self.current_store = copy.copy(self.initial_store)

        self.store_listen()

    async def update_timeline(self, store, action, state_diff):
        self.timeline.append([
            datetime.now(),
            action,
            state_diff
        ])
        if self.timeline_item_selected is None:
            store_items = self.current_store.setdefault(store.store_type, {})
            store_item_content = store_items.setdefault(store.id, {})

            for state_key, values in state_diff.items():
                store_item_content[state_key] = values[1]
        yield None

    def store_listen(self):
        for store_type in Store.all_store_types():
            self.sagas[store_type.__name__] = store_type.install_saga(
                self.update_timeline,
            )

    def store_unlisten(self):
        for store_type in Store.all_store_types():
            store_type.uninstall_saga(self.sagas[store_type.__name__])
            del self.sagas[store_type.__name__]

    def store_dispatch_change(self, store_type, store_id, attr, value):
        store = Store.find_store(store_type, store_id)
        action = Action(
            target=store,
            type_name=f"SET_{attr.upper()}",
            payload=dict(value=value)
        )
        asyncio.run_coroutine_threadsafe(action.dispatch(), self.event_loop)

    def update_timeline_selection(self, new_position):
        last_position = self.timeline_item_selected
        self.timeline_item_selected = new_position

        if last_position is None:
            self.current_store = copy.copy(self.initial_store)
            last_position = 0

        if new_position >= last_position:
            incr = 1
            new_position += 1
        else:
            incr = -1

        for p in range(last_position, new_position, incr):
            store = self.timeline[p][1].target
            store_items = self.current_store.setdefault(store.store_type, {})
            store_item_content = store_items.setdefault(store.id, {})
            for state_key, values in self.timeline[p][2].items():
                new_value = values[1] if incr > 0 else values[0]
                store_item_content[state_key] = new_value

    def create_glfw_window(self):
        if not glfw.init():
            print("Could not initialize OpenGL context")
            return None

        # OS X supports only forward-compatible core profiles from 3.2
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)

        # Create a windowed mode window and its OpenGL context
        window = glfw.create_window(
            int(self.window_width),
            int(self.window_height),
            self.window_name,
            None,
            None
        )
        glfw.make_context_current(window)

        if not window:
            glfw.terminate()
            print("Could not initialize Window")
            return None

        return window

    def imgui_paint(self):
        keep_going = True

        ########################################
        # global menu bar
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):

                clicked, enabled = imgui.menu_item("Clear timeline")
                if clicked:
                    self.timeline = []
                    self.current_store = Store.store()
                    self.timeline_item_selected = None

                clicked, enabled = imgui.menu_item("Follow timeline")
                if clicked:
                    self.current_store = Store.store()
                    self.timeline_item_selected = None

                # Quit
                clicked, rest = imgui.menu_item("Quit", "Ctrl+Q")
                if clicked:
                    keep_going = False
                    self.store_unlisten()
                imgui.end_menu()

            imgui.end_main_menu_bar()

        # one window that fills the workspace
        imgui.set_next_window_size(self.window_width, self.window_height-21)
        imgui.set_next_window_position(0, 21)
        imgui.get_style().window_rounding = 0
        imgui.style_colors_light()

        imgui.begin(
            "Flopsy Inspector",
            closable=False,
            flags=imgui.WINDOW_NO_MOVE| imgui.WINDOW_ALWAYS_AUTO_RESIZE,
        )

        ########################################
        # timeline
        halfwidth = imgui.get_window_width() * 0.5
        fullheight = imgui.get_window_height()
        imgui.set_next_window_size(halfwidth, fullheight)
        imgui.set_next_window_position(0, 21)
        imgui.begin(
            "Timeline",
            closable=False,
            flags=imgui.WINDOW_NO_COLLAPSE|imgui.WINDOW_NO_MOVE|imgui.WINDOW_NO_RESIZE,
        )
        items = [
            (
                f"{ts.strftime('%H:%M:%S.%f')[:-3]} {action.type_name}",
                action.target,
                action.payload,
                state_diff
            )
            for ts, action, state_diff in self.timeline
        ]
        imgui.begin_child("##timeline-list")

        for counter, item in enumerate(items):
            i_label, i_target, i_payload, i_state_diff = item
            flags = imgui.TREE_NODE_OPEN_ON_DOUBLE_CLICK
            if self.timeline_item_selected == counter:
                flags |= imgui.TREE_NODE_SELECTED
            opened = imgui.tree_node(f"{i_label}##{counter}", flags)
            if imgui.is_item_clicked():
                self.update_timeline_selection(counter)
            if opened:
                imgui.text(f"Store: {type(i_target).__name__}:{i_target.id}")
                imgui.text(f"Payload: {json.dumps(i_payload, indent=4)}")

                if imgui.tree_node(f"State diff##{counter}"):
                    for store_attr, store_diff in i_state_diff.items():
                        imgui.text(f"{store_attr}:")
                        imgui.same_line()
                        imgui.text(f"{store_diff}")
                    imgui.tree_pop()

                imgui.tree_pop()
        imgui.end_child()

        imgui.end()

        ########################################
        # store
        imgui.set_next_window_size(halfwidth, fullheight)
        imgui.set_next_window_position(halfwidth, 21)
        imgui.begin(
            "Store",
            closable=False,
            flags=imgui.WINDOW_NO_COLLAPSE|imgui.WINDOW_NO_MOVE|imgui.WINDOW_NO_RESIZE,
        )

        if self.timeline_item_selected is not None:
            ts = self.timeline[self.timeline_item_selected][0]
        elif self.timeline:
            ts = self.timeline[-1][0]
        else:
            ts = self.initial_store_ts
        imgui.text(f"Last update: {ts.strftime('%H:%M:%S.%f')[:-3]}")

        imgui.begin_child("##store-list")
        for store_type, store_objmap in self.current_store.items():
            if imgui.tree_node(store_type):
                for obj_id, obj_store in store_objmap.items():
                    if imgui.tree_node(f"{obj_id}"):
                        for store_attr, store_value in obj_store.items():
                            imgui.text(f"{store_attr}:")
                            imgui.same_line()
                            item_id = f"{store_type}:{obj_id}:{store_attr}"
                            if self.store_item_selected == item_id:
                                imgui.push_item_width(
                                    0.5 * imgui.get_window_width()
                                )
                                changed, self.store_item_selected_value = imgui.input_text(
                                    "##store_edit_input",
                                    self.store_item_selected_value
                                )
                                imgui.pop_item_width()
                                imgui.same_line()
                                if imgui.button("Change"):
                                    self.store_dispatch_change(
                                        store_type, obj_id, store_attr,
                                        self.store_item_selected_value
                                    )
                                    self.store_item_selected = None
                            else:
                                selected, _ = imgui.selectable(f"{store_value}")
                                if selected:
                                    self.store_item_selected = item_id
                                    self.store_item_selected_value = str(store_value)

                        imgui.tree_pop()
                imgui.tree_pop()
        imgui.end_child()

        imgui.end()

        imgui.end()
        return keep_going

    def run(self):
        # set up the window and renderer context
        imgui.create_context()
        window = self.create_glfw_window()
        impl = GlfwRenderer(window)

        keep_going = True

        while keep_going and not glfw.window_should_close(window):
            # top of loop stuff
            glfw.poll_events()
            impl.process_inputs()
            imgui.new_frame()

            width, height = glfw.get_window_size(window)
            self.window_width = width
            self.window_height = height

            # hard work
            keep_going = self.imgui_paint()

            # bottom of loop stuff
            gl.glClearColor(1.0, 1.0, 1.0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            imgui.render()
            impl.render(imgui.get_draw_data())
            glfw.swap_buffers(window)

        impl.shutdown()
        glfw.terminate()
