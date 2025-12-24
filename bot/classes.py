import tkinter as tk
from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import pprint


class Screen(object):
    """docstring for Screen"""
    def __init__(self, parent):
        super(Screen, self).__init__()
        self.parent = parent
        self.frame = ttk.Frame(parent)   # <-- actual widget to raise # root
        self.header = None
        self.body = None


    def _screen_header(self, title, subtitle):
        self.header = ttk.Frame(self.frame)
        self.header.grid(row=0, column=0, sticky="ew")
        # self.header.grid_columnconfigure(0, weight=1)

        ttk.Label(self.header, text=title, font=("Arial", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self.header, text=subtitle, font=("Arial", 10)).grid(row=1, column=0, sticky="w", pady=(4, 0))

        return self.header


    def _screen_body(self):
        self.body = ttk.Frame(self.frame)
        self.body.grid(row=1, column=0, sticky="nsew")

        return self.body


    def setup(self, title, subtitle):
        # Stack each screen in same cell in parent (content)
        self.frame.grid(row=0, column=0, sticky="nsew")
        # Screen layout: header row + body row
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        self._screen_header(title, subtitle)
        self._screen_body()

        if self.header is None or self.body is None:
            raise Exception("Header and Body frame incomplete")



class TestsScreen(Screen):
    """docstring for TestScreen"""
    def __init__(self, parent, run_tests_callback = None):
        super().__init__(parent)
        self.test_log = None
        self.run_tests_callback = run_tests_callback


    def _build_body(self):
        # Make body expandable
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        # Log area (expands)
        self.test_log = ScrolledText(self.body, wrap="word", height=10)
        self.test_log.grid(row=0, column=0, sticky="nsew", pady=(10, 10))
        self.test_log.configure(state="disabled")

        # Button row
        btn_row = ttk.Frame(self.body)
        btn_row.grid(row=1, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        ttk.Button(btn_row, text="Run tests", command=self.run_tests)\
            .grid(row=0, column=0, sticky="w")


    def _append_log(self, msg: str):
        self.test_log.configure(state="normal")
        self.test_log.insert("end", msg + "\n")
        self.test_log.yview("end")
        self.test_log.configure(state="disabled")


    def run_tests(self):
        if self.run_tests_callback is None:
            return

        self.test_log.configure(state="normal")
        self.test_log.delete("1.0", tk.END)   # clear all text
        self.test_log.configure(state="disabled")

        self._append_log("Starting tests...")
        
        tests_results = self.run_tests_callback()

        for results in tests_results:
            self._append_log(results)

        self._append_log("All tests completed.")


    def setup(self, title, subtitle):
        super().setup(title, subtitle)
        self._build_body()



class Panel(object):
    """docstring for Panel"""
    def __init__(self):
        super(Panel, self).__init__()
        self.root = Tk()
        self.screens = {}
        self.nav = None
        self.content = None


    # Function to raise a screen
    def show_screen(self, name):
        print("show ", name)
        self.screens[name]["screen"].frame.tkraise()


    def _setup_nav(self):
        # Top navigation bar
        self.nav = ttk.Frame(self.root, padding=5)
        self.nav.grid(row=0, column=0, sticky="ew")

        # Nav buttons
        for screen_key in self.screens:
            ttk.Button(self.nav, text=self.screens[screen_key]["title"], command=lambda key=screen_key: self.show_screen(key)).pack(side="left", padx=5)


    def _setup_content_frame(self):
        # Content area
        self.content = ttk.Frame(self.root, padding=10)
        self.content.grid(row=1, column=0, sticky="nsew")


    def _setup_screens(self):
        for screen_key in self.screens:
            if screen_key == "Tests":
                self.screens[screen_key]["screen"] = TestsScreen(self.content, self.screens[screen_key]["run_tests_callback"])
            else:
                self.screens[screen_key]["screen"] = Screen(self.content)
            self.screens[screen_key]["screen"].setup(self.screens[screen_key]["title"], self.screens[screen_key]["subtitle"])


    def setup(self, screens):
        if screens is None:
            return

        self.root.title("Bot configuration")
        self.root.geometry("900x600")
        # Make content stretch with window
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.screens = screens;


        self._setup_nav()
        self._setup_content_frame()

        if self.nav is None or self.content is None:
            raise Exception( "Navigation and Content frame incomplete" )


        self._setup_screens()
        pprint.pprint(self.screens)

        all_screens = self.screens.keys()
        if len(all_screens) == 0:
            raise Exception( "Screens setup incomplete" )


        # Show default screen
        self.show_screen(list(all_screens)[-1])

        self.root.mainloop()
        
