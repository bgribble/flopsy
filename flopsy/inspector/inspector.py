#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
from datetime import datetime
from threading import Thread
from imgui.integrations.glfw import GlfwRenderer
import OpenGL.GL as gl
import glfw
import imgui
from flopsy.store import Store

class Inspector(Thread):
    def __init__(self, *, width=800, height=600):
        super().__init__()
        self.window_name = "Flopsy inspector"
        self.window_width = width
        self.window_height = height

        self.sagas = {}
        self.timeline = []

        for store_type in Store.all_store_types():
            self.sagas[store_type.__name__] = store_type.install_saga(
                self.update_timeline,
            )
        self.store = Store.store()

    async def update_timeline(self, store, action, state_diff):
        print(f"[update_timeline] {store} {action} {state_diff}")
        self.timeline.append([
            datetime.now(),
            action,
            state_diff
        ])
        yield None

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
        # global menu bar
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):

                clicked, enabled = imgui.menu_item("Clear timeline")
                if clicked:
                    self.timeline = []

                # Quit
                clicked, rest = imgui.menu_item("Quit", "Ctrl+Q")
                if clicked:
                    keep_going = False
                imgui.end_menu()

            imgui.end_main_menu_bar()

        # one window that fills the workspace
        imgui.set_next_window_size(self.window_width, self.window_height-21)
        imgui.set_next_window_position(0, 21)
        imgui.get_style().window_rounding = 0

        imgui.begin(
            "Flopsy Inspector",
            closable=False,
            flags=imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_DECORATION
        )

        ########################################
        # timeline
        halfwidth = imgui.get_window_width() * 0.5
        fullheight = imgui.get_window_height()
        imgui.set_next_window_size(halfwidth, fullheight)
        imgui.set_next_window_position(0, 21)
        imgui.begin(
            "Timeline", closable=False, flags=imgui.WINDOW_NO_COLLAPSE,
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
            if imgui.tree_node(f"{i_label}##{counter}"):
                imgui.text(f"Store: {type(i_target).__name__}:{i_target.id}")
                imgui.text(f"{json.dumps(i_payload, indent=4)}")

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
            "Store", closable=False, flags=imgui.WINDOW_NO_COLLAPSE,
        )

        imgui.begin_child("##store-list")
        store = Store.store()
        for store_type, store_objmap in store.items():
            if imgui.tree_node(store_type):
                for obj_id, obj_store in store_objmap.items():
                    if imgui.tree_node(f"{obj_id}"):
                        for store_attr, store_value in obj_store.items():
                            imgui.text(f"{store_attr}:")
                            imgui.same_line()
                            imgui.text(f"{store_value}")
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
