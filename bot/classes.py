from tkinter import *
from tkinter import ttk
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
            raise "Header and Body frame incomplete" 


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
            raise "Navigation and Content frame incomplete" 


        self._setup_screens()
        pprint.pprint(self.screens)

        all_screens = self.screens.keys()
        if len(all_screens) == 0:
            raise "Screens setup incomplete" 


        # Show default screen
        self.show_screen(list(all_screens)[-1])

        self.root.mainloop()
        
