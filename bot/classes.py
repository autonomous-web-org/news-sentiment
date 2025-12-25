import os
import json
import pprint
from pathlib import Path
from dotenv import load_dotenv

import tkinter as tk
from tkinter import messagebox, ttk, Tk
from tkinter.scrolledtext import ScrolledText


load_dotenv()


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
        self.header.grid_columnconfigure(0, weight=1)

        ttk.Label(self.header, text=title, font=("Arial", 16, "bold"), anchor="center").grid(row=0, column=0, sticky="ew")
        ttk.Label(self.header, text=subtitle, font=("Arial", 10), anchor="center").grid(row=1, column=0, sticky="ew", pady=(0, 21))

        return self.header


    def _screen_body(self):
        self.body = ttk.Frame(self.frame)
        self.body.grid(row=1, column=0, sticky="nsew")

        return self.body


    def setup(self, title, subtitle):
        # Stack each screen in same cell in parent (content)
        self.frame.grid(row=0, column=0, sticky="nsew")
        # Screen layout: header row + body row
        self.frame.grid_rowconfigure(1, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

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

class SecretsScreen(Screen):
    """docstring for TestScreen"""
    def __init__(self, parent, _save_config, save_env, apis_config=None):
        super().__init__(parent)
        self.apis_config = apis_config

        self.api_vars = {}

        # methods
        self._save_config = _save_config
        self.save_env = save_env


    def attach_alt_reveal(self, entry: ttk.Entry):
        def reveal(_event=None):
            # only reveal if this entry currently has focus
            if entry == entry.focus_get():
                entry.configure(show="")

        def hide(_event=None):
            entry.configure(show="*")

        entry.bind("<KeyPress-Alt_L>", reveal)
        entry.bind("<KeyRelease-Alt_L>", hide)
        entry.bind("<KeyPress-Alt_R>", reveal)
        entry.bind("<KeyRelease-Alt_R>", hide)

        # if focus leaves while Alt is held, re-mask
        entry.bind("<FocusOut>", hide)


    def _build_api_frames(self, content_frame):
        outer_row = 0
        for api_name, values in self.apis_config.items():
            print(api_name, values, "api")
            
            api_frame = ttk.Frame(content_frame)
            api_frame.grid(row=outer_row, column=0, sticky="ew")
            api_frame.grid_columnconfigure(0, weight=0)  # labels
            api_frame.grid_columnconfigure(1, weight=1)  # inputs expand

            checkbox_var = tk.IntVar(value=1 if values.get("enabled", False) else 0)
            api_secret_var = tk.StringVar( value=os.getenv(values.get("api_key", "")) ) # this way we verify if the right key name is being used across configs or not
            base_endpoint_var = tk.StringVar( value=values.get("base_endpoint", "") )

            self.api_vars[api_name] = {
                "enabled": checkbox_var,
                "api_secret": api_secret_var,
                "base_endpoint": base_endpoint_var,
            }

            r = 0
            ttk.Label(api_frame, text=api_name, font=("Arial", 16, "bold")).grid(row=r, column=0, sticky="ew")

            checkbox = tk.Checkbutton(api_frame, 
                text="Enable/Disable", 
                variable=checkbox_var, # Link the variable to the checkbox
                # onvalue=1,    # Value when checked
                # offvalue=0,   # Value when unchecked
                # command=show_state  # Function to call on click
                )
            checkbox.grid(row=r, column=1, sticky="e")

            r += 1
            ttk.Label(api_frame, text="API Secret (press alt to view):", font=("Arial", 10)).grid(row=r, column=0, sticky="ew")
            api_secret_entry = ttk.Entry(api_frame, textvariable=api_secret_var, show="*")
            api_secret_entry.grid(row=r, column=1, sticky="ew")
            self.attach_alt_reveal(api_secret_entry)

            r += 1
            ttk.Label(api_frame, text="Base Endpoint:", font=("Arial", 10)).grid(row=r, column=0, sticky="ew")
            ttk.Entry(api_frame, textvariable=base_endpoint_var).grid(row=r, column=1, sticky="ew", pady=(6, 12))

            outer_row += 1


    def _save_secrets(self):
        if not hasattr(self, "api_vars") or not self.api_vars:
            messagebox.showwarning("Nothing to save", "No API fields were found.")
            return

        for api_name, vars_ in self.api_vars.items():
            self.apis_config[api_name] = {
                "api_key": self.apis_config[api_name]["api_key"],
                "api_secret": "",
                "enabled": bool(vars_["enabled"].get()),                 # IntVar.get() -> 0/1
                "base_endpoint": vars_["base_endpoint"].get().strip(),   # StringVar.get()
            }

        # print("\n", self.apis_config, "updated\n")
        self._save_config()
        messagebox.showinfo("Saved", "Config Updated!")


    def _build_body(self):
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        # --- content area (put your API frames here) ---
        content = ttk.Frame(self.body)
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)

        # build your dynamic api frames inside content (not self.body)
        self._build_api_frames(content)

         # --- bottom bar ---
        bottom = ttk.Frame(self.body)
        bottom.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)

        ttk.Button(bottom, text="Save", command=self._save_secrets).grid(row=0, column=0, sticky="e")   # right aligned


        # left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        # left.grid_rowconfigure(1, weight=1)

        # right = ttk.Frame(self.body)
        # right.grid(row=0, column=1, sticky="nsew")
        # right.grid_columnconfigure(1, weight=1)

        # # ---- Left: API list ----
        # ttk.Label(left, text="APIs").grid(row=0, column=0, sticky="w", pady=(0, 6))

        # self.tree = ttk.Treeview(left, columns=("name",), show="tree")
        # self.tree.grid(row=1, column=0, sticky="ns")
        # self.tree.bind("<<TreeviewSelect>>", self._on_select_api)

        # btns = ttk.Frame(left)
        # btns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        # ttk.Button(btns, text="New", command=self._new_api).grid(row=0, column=0, sticky="w")
        # ttk.Button(btns, text="Delete", command=self._delete_api).grid(row=0, column=1, sticky="w", padx=(8, 0))

        # # ---- Right: Editor ----
        # r = 0
        # ttk.Label(right, text="API name").grid(row=r, column=0, sticky="w", pady=(0, 4))
        # ttk.Entry(right, textvariable=self.api_name_var, state="readonly").grid(row=r, column=1, sticky="ew", pady=(0, 4))
        # r += 1

        # ttk.Label(right, text="API key").grid(row=r, column=0, sticky="w", pady=(0, 4))
        # ttk.Entry(right, textvariable=self.api_key_var).grid(row=r, column=1, sticky="ew", pady=(0, 4))
        # r += 1

        # ttk.Label(right, text="API secret").grid(row=r, column=0, sticky="w", pady=(0, 4))
        # self.secret_entry = ttk.Entry(right, textvariable=self.api_secret_var, show="*")
        # self.secret_entry.grid(row=r, column=1, sticky="ew", pady=(0, 4))
        # r += 1

        # ttk.Checkbutton(
        #     right,
        #     text="Show secret",
        #     variable=self.secret_visible,
        #     command=self._toggle_secret_visibility
        # ).grid(row=r, column=1, sticky="w", pady=(0, 8))
        # r += 1

        # ttk.Label(right, text="Base URL").grid(row=r, column=0, sticky="w", pady=(0, 4))
        # ttk.Entry(right, textvariable=self.base_url_var).grid(row=r, column=1, sticky="ew", pady=(0, 4))
        # r += 1

        # action_row = ttk.Frame(right)
        # action_row.grid(row=r, column=1, sticky="ew", pady=(10, 0))
        # ttk.Button(action_row, text="Save", command=self._save_current).grid(row=0, column=0, sticky="w")
        # ttk.Button(action_row, text="Reload file", command=self._load_and_refresh).grid(row=0, column=1, sticky="w", padx=(8, 0))

        # # Initial load
        # self._load_and_refresh()


    def setup(self, title, subtitle):
        super().setup(title, subtitle)
        self._build_body()



class Panel(object):
    """docstring for Panel"""
    def __init__(self, screens, config, save_config, save_env):
        super(Panel, self).__init__()
        self.root = Tk()
        self.nav = None
        self.content = None

        self.screens = screens
        self.config = config

        # methods
        self.save_config = save_config
        self.save_env = save_env


    # Function to raise a screen
    def show_screen(self, name):
        print("show ", name)
        self.screens[name]["screen"].frame.tkraise()


    def _save_config(self):
        self.save_config(complete_config=json.dumps(self.config, indent=3))


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
            elif screen_key == "Secrets":
                self.screens[screen_key]["screen"] = SecretsScreen(self.content, self._save_config, self.save_env, apis_config=self.config["apis"])
            else:
                self.screens[screen_key]["screen"] = Screen(self.content)

            self.screens[screen_key]["screen"].setup(self.screens[screen_key]["title"], self.screens[screen_key]["subtitle"])


    def setup(self):
        if self.screens is None or self.config is None:
            return

        self.root.title("Bot configuration")
        self.root.geometry("900x600")

        # Make content stretch with window
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)


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
        
