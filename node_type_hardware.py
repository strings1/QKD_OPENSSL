#== Author: Darie Alexandru ===========================================#
# This file defines the hardware-based QKD node implementation.         #
#======================================================================#

import time
import os # Needed for os.urandom
from collections import Counter
from node_type_interface import QKD_Node
# Import sensor and LED pins from settings
from settings import S0, S1, S2, S3, OUT, RED_PIN, GREEN_PIN, BLUE_PIN
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO library not found. Ensure this code is running on a Raspberry Pi with the library installed.")
    GPIO = None


class QKD_Node_Hardware(QKD_Node):
    def __init__(self, time_between):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO library not available. Cannot initialize hardware node.")

        self.TIME_BETWEEN = time_between
        self.SAMPLE_TIME = time_between / 4
        self.CHANNEL_TIME = self.SAMPLE_TIME / 3

        GPIO.setmode(GPIO.BCM)
        # Setup Sensor Pins
        GPIO.setup([S0, S1, S2, S3], GPIO.OUT)
        GPIO.setup(OUT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.output(S0, GPIO.HIGH) # Set frequency scaling to 20%
        GPIO.output(S1, GPIO.LOW)

        # Setup LED Pins
        GPIO.setup([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.OUT)
        GPIO.output([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.LOW) # Start with LED off

        self.filters = {
            'R': (GPIO.LOW, GPIO.LOW),
            'G': (GPIO.HIGH, GPIO.HIGH),
            'B': (GPIO.LOW, GPIO.HIGH)
        }
        self.led_pins = {
            'Red': RED_PIN,
            'Green': GREEN_PIN,
            'Blue': BLUE_PIN
        }
        self.last_color = None # For sensor reading optimization

    def _set_led_color(self, color_name):
        """Sets the RGB LED to the specified color."""
        # Turn off all LEDs first
        GPIO.output([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.LOW)
        if color_name in self.led_pins:
            GPIO.output(self.led_pins[color_name], GPIO.HIGH)
        elif color_name == 'White': # Optional: White = R+G+B
             GPIO.output([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.HIGH)
        # 'Off' is handled by turning all off initially

    # ...existing read_interval and _read_color methods...
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
            if not readings: # Handle case where no color is read (should not happen ideally)
                dominant_color = 'Off' # Or some default/error indicator
            else:
                # Find the color with the maximum reading, default to 'Off' if all are 0 or negative
                max_reading = -1
                dominant_color = 'Off'
                for color, reading in readings.items():
                    if reading > max_reading:
                        max_reading = reading
                        dominant_color = color
                # If max_reading is still <= 0, it means no color was strongly detected
                if max_reading <= 0:
                     dominant_color = 'Off' # Or perhaps the last known color? Needs testing.


            votes.append(dominant_color)

            # Enforce sample timing
            elapsed = time.monotonic() - sample_start
            if elapsed < self.SAMPLE_TIME:
                time.sleep(self.SAMPLE_TIME - elapsed)

        # Final majority vote
        if not votes or all(v == 'Off' for v in votes):
             majority = 'Off' # No color detected or only 'Off' votes
        else:
             # Filter out 'Off' votes before determining the most common color
             filtered_votes = [v for v in votes if v != 'Off']
             if not filtered_votes:
                 majority = 'Off'
             else:
                 majority = Counter(filtered_votes).most_common(1)[0][0]

        print(f"Detected: {majority} | Samples: {votes} | Readings: {readings} | "
              f"Actual: {time.monotonic() - start:.3f}s")
        return majority # Return the detected color


    def _read_color(self, color):
        """Read a single color channel with strict timing"""
        GPIO.output(S2, self.filters[color][0])
        GPIO.output(S3, self.filters[color][1])

        # Handle color transitions - Allow sensor to settle
        # Increased settle time slightly for potentially better readings
        settle_time = 0.005 if (self.last_color != color) else 0.002
        time.sleep(settle_time)
        self.last_color = color

        # Time-bound reading - Count pulses within the channel time
        count = 0
        pulse_start_time = time.monotonic()
        end_time = pulse_start_time + self.CHANNEL_TIME

        # More robust pulse counting
        last_state = GPIO.input(OUT)
        while time.monotonic() < end_time:
            current_state = GPIO.input(OUT)
            if current_state == GPIO.HIGH and last_state == GPIO.LOW: # Rising edge detection
                count += 1
            last_state = current_state
            # Small sleep to prevent busy-waiting and reduce CPU load slightly
            # Adjust if it impacts timing accuracy
            time.sleep(0.0001)

        return count

    def read(self, num_bits):
        """
        Waits for a start signal, reads a specified number of bits/colors,
        waits for an end signal, and returns the detected colors.
        """
        detected_colors = []
        start_signal = 'White'
        end_signal = 'White'
        max_wait_signals = 10 # Max intervals to wait for start/end signals
        intervals_read = 0

        print(f"[{os.getpid()}] Read: Waiting for Start Signal ({start_signal})...")
        waited_intervals = 0
        try:
            # 1. Wait for Start Signal
            while waited_intervals < max_wait_signals:
                cycle_start = time.monotonic()
                detected = self.read_interval()
                if detected == start_signal:
                    print(f"[{os.getpid()}] Read: Start Signal detected.")
                    break
                # Maintain timing while waiting
                elapsed = time.monotonic() - cycle_start
                if elapsed < self.TIME_BETWEEN:
                    time.sleep(self.TIME_BETWEEN - elapsed)
                waited_intervals += 1
            else: # Loop finished without break
                print(f"[{os.getpid()}] Read Error: Timeout waiting for Start Signal.")
                # Don't cleanup here, let the main API handle errors
                return None # Indicate error

            # 2. Read Data Bits
            print(f"[{os.getpid()}] Read: Reading {num_bits} data bits...")
            while intervals_read < num_bits:
                cycle_start = time.monotonic()
                detected_color = self.read_interval()
                # Optional: Check if end signal detected prematurely
                # if detected_color == end_signal:
                #     print(f"[{os.getpid()}] Read Warning: End signal detected early after {intervals_read} bits.")
                #     break # Stop reading data bits

                detected_colors.append(detected_color)
                intervals_read += 1

                # Maintain exact interval timing
                elapsed = time.monotonic() - cycle_start
                if elapsed < self.TIME_BETWEEN:
                    time.sleep(self.TIME_BETWEEN - elapsed)

            if intervals_read != num_bits:
                 print(f"[{os.getpid()}] Read Warning: Read only {intervals_read}/{num_bits} bits before potential early end signal.")
                 # Decide how to handle this - return partial data or None? Returning partial for now.

            # 3. Wait for End Signal (Optional but good practice)
            print(f"[{os.getpid()}] Read: Waiting for End Signal ({end_signal})...")
            waited_intervals = 0
            end_signal_detected = False
            while waited_intervals < max_wait_signals:
                cycle_start = time.monotonic()
                detected = self.read_interval()
                if detected == end_signal:
                    print(f"[{os.getpid()}] Read: End Signal detected.")
                    end_signal_detected = True
                    break
                # Maintain timing while waiting
                elapsed = time.monotonic() - cycle_start
                if elapsed < self.TIME_BETWEEN:
                    time.sleep(self.TIME_BETWEEN - elapsed)
                waited_intervals += 1

            if not end_signal_detected:
                 print(f"[{os.getpid()}] Read Warning: Timeout waiting for End Signal.")
                 # Continue anyway, as data bits were read

            print(f"[{os.getpid()}] Read: Finished. Detected {len(detected_colors)} colors.")
            return detected_colors

        except KeyboardInterrupt:
            print(f"\n[{os.getpid()}] Read: Operation interrupted by user.")
            return None # Indicate interruption
        except Exception as e:
            print(f"[{os.getpid()}] Read Error: An exception occurred during read: {e}")
            return None # Indicate error


    def write(self, hex_data):
        """Encodes hex_data into colors using BB84 logic and displays on RGB LED."""
        print(f"Writing data to hardware QKD node: {hex_data}")
        if GPIO is None:
            print("Error: GPIO library not available.")
            return [] # Return empty list or raise error

        # Convert hex to binary string (remove '0b' prefix)
        # Ensure sufficient padding if needed, though os.urandom usually gives full bytes
        data = bin(int(hex_data, 16))[2:].zfill(len(hex_data) * 4)
        picked_bases = []

        try:
            # Synchronization Signal (e.g., White light for 1 interval)
            print("  Sending Start Signal (White)")
            self._set_led_color('White')
            time.sleep(self.TIME_BETWEEN)
            self._set_led_color('Off') # Short gap after sync
            time.sleep(self.TIME_BETWEEN / 4)


            for i, bit in enumerate(data):
                start_time = time.perf_counter()
                # Pick a random basis ('+' or 'X')
                random_base = self.basis[os.urandom(1)[0] % 2]
                picked_bases.append(random_base)
                # Convert the bit to the corresponding color based on the chosen basis
                color_to_display = self.colors[random_base][bit]

                print(f"  Bit {i+1}/{len(data)}: {bit}, Basis: {random_base}, Color: {color_to_display}")
                self._set_led_color(color_to_display)

                # Use precise timing, accounting for the time taken by GPIO calls etc.
                elapsed = time.perf_counter() - start_time
                remaining = self.TIME_BETWEEN - elapsed

                if remaining > 0:
                    time.sleep(remaining)
                else:
                    # This indicates the loop iteration took longer than TIME_BETWEEN
                    print(f"  WARNING: Frame overrun by {-remaining*1000:.1f}ms")

            # End Signal (e.g., White light again)
            print("  Sending End Signal (White)")
            self._set_led_color('White')
            time.sleep(self.TIME_BETWEEN)
            self._set_led_color('Off') # Turn LED off finally
            print("Write finished.")

        except Exception as e:
            print(f"An error occurred during write: {e}")
        finally:
            # Ensure LED is off even if an error occurs
            self._set_led_color('Off')
            # Don't cleanup GPIO here, let it be handled by a dedicated cleanup call or program exit
        return picked_bases # Return the bases used for transmission


    def calibrate(self, n=5):
        """Cycles through Red, Green, Blue LEDs n times for calibration."""
        print(f"Starting hardware calibration ({n} cycles)...")
        if GPIO is None:
            print("Error: GPIO library not available.")
            return

        calibration_colors = ['Red', 'Green', 'Blue']

        try:
            # Initial off state
            self._set_led_color('Off')
            time.sleep(self.TIME_BETWEEN)

            for i in range(n):
                print(f"Calibration Cycle {i+1}/{n}")
                for color in calibration_colors:
                    start_time = time.perf_counter()
                    print(f"  Displaying: {color}")
                    self._set_led_color(color)

                    # Precise timing similar to write/GUI calibrate
                    elapsed = time.perf_counter() - start_time
                    remaining = self.TIME_BETWEEN - elapsed
                    if remaining > 0:
                        time.sleep(remaining)
                    else:
                        print(f"  WARNING: Calibration frame overrun by {-remaining*1000:.1f}ms")

                # Turn off between cycles
                self._set_led_color('Off')
                time.sleep(self.TIME_BETWEEN / 2) # Shorter off time between cycles

            print("Calibration finished.")

        except Exception as e:
            print(f"An error occurred during calibration: {e}")
        finally:
            # Ensure LED is off after calibration
            self._set_led_color('Off')
            # Don't cleanup GPIO here

    def cleanup(self):
        """Cleans up GPIO resources."""
        if GPIO:
            print("Cleaning up GPIO...")
            GPIO.cleanup()