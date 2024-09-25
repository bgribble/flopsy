# -*- coding: utf-8 -*-
"""
inspector.py -- state timeline and visualizer

Copyright (c) 2022-2024 Bill Gribble <grib@billgribble.com>
"""
import asyncio
import ctypes
import json
import copy
import OpenGL.GL as gl
from sdl2 import *  # noqa
from datetime import datetime
from threading import Thread
from imgui_bundle import imgui
from flopsy.action import Action
from flopsy.store import Store
from imgui_bundle.python_backends.sdl_backend import SDL2Renderer


class Inspector(Thread):
    """
    imgui display for viewing and interacting with state.

    Modeled after the Redux devtools for Chrome.

    Can run its own main loop (using GLFW) in a thread:
    Inspector().start()

    Or you can integrate it into an existing imgui app
    by creating an Inspector and calling render()
    """
    def __init__(
        self, *,
        title="Flopsy inspector",
        event_loop=None,
        width=800, height=600
    ):
        super().__init__()
        self.window_name = title
        self.window_width = width
        self.window_height = height

        self.timeline_item_selected = None
        self.store_item_selected = None
        self.store_item_selected_value = None

        self.sagas = {}
        self.timeline = []

        self.event_loop = event_loop or asyncio.get_event_loop()
        self.window = None
        self.needs_focus = False

        self.initial_store = Store.store()
        self.initial_store_ts = datetime.now()
        self.current_store = copy.copy(self.initial_store)

        self.store_listen()

    def focus(self):
        self.needs_focus = True

    async def update_timeline(self, store, action, state_diff):
        if action not in [t[1] for t in self.timeline]:
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
            self.sagas[store_type.store_type] = store_type.install_saga(
                self.update_timeline,
            )

    def store_unlisten(self):
        for store_type in Store.all_store_types():
            store_type.uninstall_saga(self.sagas[store_type.store_type])
            del self.sagas[store_type.store_type]

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

    def render(self):
        """
        render()
        """
        keep_going = True

        # one window that fills the workspace
        imgui.set_next_window_size([self.window_width, self.window_height])
        imgui.get_style().window_rounding = 0
        imgui.style_colors_light()

        if self.window:
            imgui.set_next_window_pos([0, 0])
            flags = (
                imgui.WindowFlags_.no_move
                | imgui.WindowFlags_.always_auto_resize
                | imgui.WindowFlags_.menu_bar
            )
        else:
            flags = imgui.WindowFlags_.menu_bar

        imgui.begin(
            "Flopsy Inspector",
            flags=flags,
        )
        if self.needs_focus:
            imgui.set_window_focus()
            imgui.set_window_collapsed(False)
            self.needs_focus = False

        ########################################
        # menu bar
        if imgui.begin_menu_bar():
            if imgui.begin_menu("Inspector"):
                clicked, _ = imgui.menu_item("Clear timeline", "", False)
                if clicked:
                    self.timeline = []
                    self.current_store = Store.store()
                    self.timeline_item_selected = None

                clicked, _ = imgui.menu_item("Follow timeline", "", False)
                if clicked:
                    self.current_store = Store.store()
                    self.timeline_item_selected = None

                # Quit
                clicked, _ = imgui.menu_item("Close", "Ctrl+w", False)
                if clicked:
                    keep_going = False
                    self.store_unlisten()
                imgui.end_menu()
            imgui.end_menu_bar()

        ########################################
        # timeline
        halfwidth = imgui.get_window_width() * 0.5
        imgui.begin_child(
            "Timeline", [halfwidth, 0], True
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
            flags = imgui.TreeNodeFlags_.open_on_double_click
            if self.timeline_item_selected == counter:
                flags |= imgui.TreeNodeFlags_.selected
            opened = imgui.tree_node_ex(f"{i_label}##{counter}", flags)
            if imgui.is_item_clicked():
                self.update_timeline_selection(counter)
            if opened:
                imgui.text(f"Store: {type(i_target).store_type}:{i_target.id}")
                imgui.text(f"Payload: {json.dumps(i_payload, indent=4)}")

                if imgui.tree_node(f"State diff##{counter}"):
                    for store_attr, store_diff in i_state_diff.items():
                        imgui.text(f"{store_attr}:")
                        imgui.same_line()
                        imgui.text(f"{store_diff}")
                    imgui.tree_pop()

                imgui.tree_pop()
        imgui.end_child()
        imgui.end_child()

        ########################################
        # store
        imgui.same_line()
        imgui.begin_child(
            "Store", [halfwidth, 0], True
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
            if not store_objmap:
                continue
            if imgui.tree_node(store_type):
                for obj_id, obj_store in store_objmap.items():
                    store_object = Store.find_store(store_type, obj_id)
                    obj_node_name = f"{obj_id}"
                    if (desc := store_object.description()):
                        obj_node_name += f" ({desc})"
                    if imgui.tree_node(obj_node_name):
                        for store_attr, store_value in obj_store.items():
                            imgui.text(f"{store_attr}:")
                            imgui.same_line()
                            item_id = f"{store_type}:{obj_id}:{store_attr}"
                            if self.store_item_selected == item_id:
                                imgui.push_item_width(
                                    0.5 * imgui.get_window_width()
                                )
                                _, self.store_item_selected_value = (
                                    imgui.input_text(
                                        "##store_edit_input",
                                        self.store_item_selected_value
                                    )
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
                                selected, _ = imgui.selectable(f"{store_value}", False)
                                if selected:
                                    self.store_item_selected = item_id
                                    self.store_item_selected_value = str(store_value)

                        imgui.tree_pop()
                imgui.tree_pop()
        imgui.end_child()
        imgui.end_child()
        self.window_width, self.window_height = imgui.get_window_size()
        imgui.end()

        return keep_going

    #####################
    # main loop routines -- needed if you aren't calling
    # render() directly from a containing app

    def create_sdl2_window(self, name, width, height):
        if SDL_Init(SDL_INIT_EVERYTHING) < 0:
            Store.log(
                "[sdl2] Error: SDL could not initialize! SDL Error: "
                + SDL_GetError().decode("utf-8")
            )
            return None, None

        SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1)
        SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24)
        SDL_GL_SetAttribute(SDL_GL_STENCIL_SIZE, 8)
        SDL_GL_SetAttribute(SDL_GL_ACCELERATED_VISUAL, 1)
        SDL_GL_SetAttribute(SDL_GL_MULTISAMPLEBUFFERS, 1)
        SDL_GL_SetAttribute(SDL_GL_MULTISAMPLESAMPLES, 8)
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG)
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4)
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1)
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE)

        SDL_SetHint(SDL_HINT_MAC_CTRL_CLICK_EMULATE_RIGHT_CLICK, b"1")
        SDL_SetHint(SDL_HINT_VIDEO_HIGHDPI_DISABLED, b"1")
        SDL_SetHint(SDL_HINT_VIDEODRIVER, b"wayland,x11")
        SDL_SetHint(SDL_HINT_VIDEO_X11_FORCE_EGL, b"1")
        SDL_SetHint(SDL_HINT_APP_NAME, name.encode('utf-8'))

        window = SDL_CreateWindow(
            name.encode("utf-8"),
            SDL_WINDOWPOS_CENTERED,
            SDL_WINDOWPOS_CENTERED,
            width,
            height,
            SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE,
        )

        if window is None:
            Store.log(
                "[sdl2] Error: Window could not be created! SDL Error: "
                + SDL_GetError().decode("utf-8")
            )
            return None, None

        gl_context = SDL_GL_CreateContext(window)
        if gl_context is None:
            Store.log(
                "[sdl2] Error: Cannot create OpenGL Context! SDL Error: "
                + SDL_GetError().decode("utf-8")
            )
            return None, None

        SDL_GL_MakeCurrent(window, gl_context)
        if SDL_GL_SetSwapInterval(1) < 0:
            Store.log(
                "[sdl2] Error: Unable to set VSync! SDL Error: " + SDL_GetError().decode("utf-8")
            )
            return None, None
        return window, gl_context

    def run(self):
        # set up the window and renderer context
        ctx = imgui.create_context()
        imgui.set_current_context(ctx)
        window, gl_context = self.create_sdl2_window(self.window_name, self.window_width, self.window_height)
        self.window = window
        impl = SDL2Renderer(window)

        keep_going = True

        event = SDL_Event()
        width = ctypes.c_int()
        height = ctypes.c_int()

        while keep_going:
            # top of loop stuff
            while SDL_PollEvent(ctypes.byref(event)) != 0:
                SDL_GetWindowSize(self.window, width, height)
                w_width = int(width.value)
                w_height = int(height.value)
                if w_width != self.window_width or w_height != self.window_height:
                    self.window_width = w_width
                    self.window_height = w_height

                if event.type == SDL_QUIT:
                    keep_going = False
                impl.process_event(event)

            impl.process_inputs()
            imgui.new_frame()

            # hard work
            keep_going = self.render()

            # bottom of loop stuff
            gl.glClearColor(1.0, 1.0, 1.0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            imgui.render()
            impl.render(imgui.get_draw_data())
            SDL_GL_SwapWindow(window)

        impl.shutdown()
        SDL_GL_DeleteContext(gl_context)
        SDL_DestroyWindow(self.window)
        SDL_Quit()
