#== Author: Darie Alexandru ===========================================#
# This file defines the GUI-based QKD node implementation.            #
#======================================================================#

import time
import os
import cv2
try:
    import tkinter as tk
except ImportError:
    print("tkinter library not found. Ensure this code is running in an environment with tkinter installed.")
    tk = None
from node_type_interface import QKD_Node

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
        
    def read(self, num_bits):
        print("Reading data from GUI node...")
        """
        Reads a specified number of bits/colors using the webcam.
        For each interval, captures a frame, reads the center pixel,
        and decides the predominant color (Red, Green, Blue).
        """
        print(f"Reading {num_bits} bits from GUI node using webcam...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Could not open webcam.")
            return None

        detected_colors = []
        try:
            for i in range(num_bits):
                ret, frame = cap.read()
                if not ret:
                    print(f"Error: Failed to capture frame {i+1}.")
                    detected_colors.append('Off')
                    continue

                # Get center pixel
                h, w, _ = frame.shape
                center_pixel = frame[h // 2, w // 2]
                b, g, r = int(center_pixel[0]), int(center_pixel[1]), int(center_pixel[2])

                # Decide predominant color
                if r > g and r > b and r > 50:
                    color = 'Red'
                elif g > r and g > b and g > 50:
                    color = 'Green'
                elif b > r and b > g and b > 50:
                    color = 'Blue'
                else:
                    color = 'Off'

                detected_colors.append(color)
                print(f"Bit {i+1}/{num_bits}: Center pixel RGB=({r},{g},{b}) -> Detected: {color}")

                # Show frame with a dot at the center for user feedback (optional)
                cv2.circle(frame, (w // 2, h // 2), 5, (0, 255, 255), -1)
                cv2.imshow('QKD Webcam Read', frame)
                if cv2.waitKey(int(self.TIME_BETWEEN * 1000)) & 0xFF == ord('q'):
                    print("Interrupted by user.")
                    break

            print(f"Read finished. Detected colors: {detected_colors}")
            return detected_colors

        finally:
            cap.release()
            cv2.destroyAllWindows()

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

# Test the GUI node
data_key = "0x1234567890abcdef"  # Example hex data
gui_node = QKD_Node_GUI(time_between=0.1)
gui_node.write(data_key)
# gui_node.calibrate(32)