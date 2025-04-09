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
from settings import S0, S1, S2, S3, OUT
from collections import Counter
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO library not found. Ensure this code is running on a Raspberry Pi with the library installed.")
    GPIO = None


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

        try:
            for _ in range(n):
                for color in ['Red', 'Green', 'Blue']:
                    start_time = time.perf_counter()  # More precise timing
                    
                    # Update display
                    root.configure(bg=rgb_colors[color])
                    root.update_idletasks()  # Force immediate GUI update
                    root.update()  # Handle all pending events
                    
                    # Precision sleep using remaining time
                    elapsed = time.perf_counter() - start_time
                    remaining = self.TIME_BETWEEN - elapsed
                    
                    if remaining > 0:
                        time.sleep(remaining * 0.9)  # Account for sleep() inaccuracy
                    else:
                        print(f"WARNING: Frame overrun by {-remaining*1000:.1f}ms")
                    
                    # Verify total duration
                    total_elapsed = time.perf_counter() - start_time
                    if total_elapsed < self.TIME_BETWEEN * 0.95:
                        time.sleep(self.TIME_BETWEEN - total_elapsed)

        finally:
            # Ensure window cleanup even on errors
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
        time.sleep(1)
        for i in data:
            # Pick a random basis
            random_base = self.basis[os.urandom(1)[0] % 2]
            picked_bases.append(random_base)
            # Convert the bit to the corresponding color based on the chosen basis
            color = self.colors[random_base][i]
            #print(f"Displaying color: {color}")
            print(color[0])
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



class QKD_Node_Hardware(QKD_Node):
    def __init__(self, time_between):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([S0, S1, S2, S3], GPIO.OUT)
        GPIO.setup(OUT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.output(S0, GPIO.HIGH)
        GPIO.output(S1, GPIO.LOW)
        
        self.TIME_BETWEEN = time_between
        self.SAMPLE_TIME = time_between / 4  # Initialize first
        self.CHANNEL_TIME = self.SAMPLE_TIME / 3  # Then calculate
        self.filters = {
            'R': (GPIO.LOW, GPIO.LOW),
            'G': (GPIO.HIGH, GPIO.HIGH),
            'B': (GPIO.LOW, GPIO.HIGH)
        }
        self.last_color = None

    def read_interval(self):
        """Read all 4 samples within TIME_BETWEEN"""
        start = time.monotonic()
        votes = []
        
        for _ in range(4):
            sample_start = time.monotonic()
            readings = {}
            
            # Read all three colors quickly
            for color in ['R', 'G', 'B']:
                readings[color] = self._read_color(color)
            
            # Determine dominant color for this sample
            votes.append(max(readings, key=readings.get))
            
            # Enforce sample timing
            elapsed = time.monotonic() - sample_start
            if elapsed < self.SAMPLE_TIME:
                time.sleep(self.SAMPLE_TIME - elapsed)
        
        # Final majority vote
        majority = Counter(votes).most_common(1)[0][0]
        print(f"Detected: {majority} | Samples: {votes} | "
              f"Actual: {time.monotonic() - start:.3f}s")
        
    def _read_color(self, color):
        """Read a single color channel with strict timing"""
        GPIO.output(S2, self.filters[color][0])
        GPIO.output(S3, self.filters[color][1])
        
        # Handle color transitions
        settle_time = 0.002 if (self.last_color != color) else 0.001
        time.sleep(settle_time)
        self.last_color = color
        
        # Time-bound reading
        count = 0
        end_time = time.monotonic() + self.CHANNEL_TIME
        while time.monotonic() < end_time:
            if GPIO.input(OUT) == GPIO.HIGH:
                count += 1
                while GPIO.input(OUT) == GPIO.HIGH: pass
        return count

    def read(self):
        print("Reading data from hardware QKD node...")
        

    def write(self, data):
        print(f"Writing data to hardware QKD node: {data}")
        # Implementation for writing to the hardware QKD node



data_key = os.urandom(32//8).hex()
print(data_key)
print(type(data_key))
# print in binary
print(bin(int(data_key, 16))[2:])
# print size of key in binary
print(bin(int(data_key, 16))[2:].__len__())

# Test the GUI node
gui_node = QKD_Node_GUI(time_between=0.5)
gui_node.write(data_key)
# gui_node.calibrate(32)