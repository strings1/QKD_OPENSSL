#== Author: Darie Alexandru ===========================================#
# This file serves the purpose to allow users to use different type    #
# of servers, since not everyone has an rgb led. Here are two classes  #
# that either light up an RGB_LED, or creates a box with the leds on   #
# the screen.                                                          #
#----------------------------------------------------------------------#
# For more information about the api, feel free to consult ETSI's doc. #
#======================================================================#

import time
import os
from abc import ABC, abstractmethod
import tkinter as tk


class QKD_Node(ABC):
    basis = ['+', 'X']
    colors = {
        basis[0]: {
            '0': 'Blue',
            '1': 'Green'
        },
        basis[1]: {
            '0': 'Blue',
            '1': 'Red'
        }
    }

    @abstractmethod
    def read(self):
        pass

    @abstractmethod
    def write(self, data):
        pass

    @abstractmethod
    def calibrate(self):
        pass


class QKD_Node_GUI(QKD_Node):
    '''
    This class should be used for desktop Client/Server
    '''
    def __init__(self, time_between=1.0):
        self.TIME_BETWEEN = time_between

    def calibrate(self, n=5):
        # Create a window to display RED, GREEN, BLUE n times
        root = tk.Tk()
        root.title("Calibration Window")
        root.geometry("256x256")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 256
        window_height = 256
        x_position = screen_width - window_width
        y_position = screen_height - window_height
        root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

        # Map colors to full RGB values
        rgb_colors = {
            'Red': '#FF0000',
            'Green': '#00FF00',
            'Blue': '#0000FF'
        }

        for _ in range(n):
            for color in ['Red', 'Green', 'Blue']:
                # print(f"Displaying calibration color: {color}")
                root.configure(bg=rgb_colors[color])
                root.update()
                time.sleep(self.TIME_BETWEEN)

        # Destroy the window after calibration
        root.destroy()
        
    def read(self):
        print("Reading data from GUI node...")
        # This method should be implemented by reading colors from a web-camera
        # I do not have one yet so no implementation for this method

    def write(self, hex_data):
        print(f"Writing data to GUI node: {hex_data}")
        data = bin(int(hex_data, 16))[2:]  # remove the '0b' prefix
        picked_bases = []

        # Create a single window at the start
        root = tk.Tk()
        root.title("QKD Node GUI")
        root.geometry("256x256")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 256
        window_height = 256
        x_position = screen_width - window_width
        y_position = screen_height - window_height
        root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

        # Map colors to full RGB values
        rgb_colors = {
            'Red': '#FF0000',
            'Green': '#00FF00',
            'Blue': '#0000FF',
            'Yellow': '#FFFF00'
        }
        # for each bit in the data
        # display white to indicate the start of the transmission
        root.configure(bg='white')
        root.update()
        time.sleep(self.TIME_BETWEEN)
        for i in data:
            # Pick a random basis
            random_base = self.basis[os.urandom(1)[0] % 2]
            picked_bases.append(random_base)
            # Convert the bit to the corresponding color based on the chosen basis
            color = self.colors[random_base][i]
            print(f"Displaying color: {color}")
            # Update the window's background color using the RGB value
            root.configure(bg=rgb_colors[color])
            root.update()  # Update the window to reflect the color change
            time.sleep(self.TIME_BETWEEN)

        # Destroy the window after displaying all colors
        # Display white to indicate the end of the transmission
        root.configure(bg='white')
        root.update()
        time.sleep(self.TIME_BETWEEN)
        root.destroy()



class QKD_Node_LED(QKD_Node):
    def read(self):
        print("Reading data from LED node...")
        # Implementation for reading from LED

    def write(self, data):
        print(f"Writing data to LED node: {data}")
        # Implementation for writing to LED



data_key = os.urandom(16//8).hex()
print(data_key)
print(type(data_key))
# print in binary
print(bin(int(data_key, 16))[2:])
# print size of key in binary
print(bin(int(data_key, 16))[2:].__len__())

# Test the GUI node
gui_node = QKD_Node_GUI(time_between=0.05)
#gui_node.write(data_key)
gui_node.calibrate(20)