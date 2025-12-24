from tkinter import *
from tkinter import ttk
import json

from test import is_json_valid


class Panel(object):
    """docstring for Panel"""
    def __init__(self):
        super(Panel, self).__init__()
        self.root = Tk()
        self.screen_frames = {}
        self.content = None
        
    # Function to raise a screen
    def show_screen(self, name):
        self.screen_frames[name].tkraise()

    def setup_nav(self):
        # Top navigation bar
        nav = ttk.Frame(self.root, padding=5)
        nav.grid(row=0, column=0, sticky="ew")

        # Nav buttons
        for frame_key in self.screen_frames.keys():
            frame_name = frame_key
            if "Exchanges" in frame_key:
                frame_name = "Exchanges/Stocks"

            ttk.Button(nav, text=frame_name, command=lambda key=frame_key: self.show_screen(key)).pack(side="left", padx=5)

    def setup_screens(self):
        # Content area
        self.content = ttk.Frame(self.root, padding=10)
        self.content.grid(row=1, column=0, sticky="nsew")

        # Make content stretch with window
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # --- Three demo "screens" ---

        # Screen 1
        screen1 = ttk.Frame(self.content)
        ttk.Label(screen1, text="Screen 1: Overview", font=("Arial", 14)).pack(pady=20)
        ttk.Label(screen1, text="This is the first demo screen.").pack()
        self.screen_frames["Exchanges"] = screen1

        # Screen 2
        screen2 = ttk.Frame(self.content)
        ttk.Label(screen2, text="Screen 2: Settings", font=("Arial", 14)).pack(pady=20)
        ttk.Label(screen2, text="Put your settings widgets here.").pack()
        self.screen_frames["Secrets"] = screen2

        # Screen 3
        screen3 = ttk.Frame(self.content)
        ttk.Label(screen3, text="Screen 3: Logs", font=("Arial", 14)).pack(pady=20)
        ttk.Label(screen3, text="Show logs or output here.").pack()
        self.screen_frames["Tests"] = screen3

        # Layout all screens in the same grid cell
        for frame in self.screen_frames.values():
            frame.grid(row=0, column=0, sticky="nsew")
        
    def start(self):
        self.root.title("Bot configuration")
        self.root.geometry("600x400")

        self.setup_screens()
        self.setup_nav()

        print(self.screen_frames.keys())

        # Show default screen
        self.show_screen(list(self.screen_frames.keys())[-1])

        self.root.mainloop()
        



def default_config():
    with open("default.json", "r") as default_config_file:
        config = default_config_file.read()

    return config

def load_config():
    pass

def save_config():
    pass


panel = Panel()
panel.start()
