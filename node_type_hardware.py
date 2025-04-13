import time
import os # Needed for os.urandom
from collections import Counter
from node_type_interface import QKD_Node
# Import sensor and LED pins from settings
from settings import S0, S1, S2, S3, OUT, RED_PIN, GREEN_PIN, BLUE_PIN, TSC_LED
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
        # Ensure CHANNEL_TIME is calculated correctly after SAMPLE_TIME
        self.CHANNEL_TIME = self.SAMPLE_TIME / 3

        GPIO.setmode(GPIO.BCM)
        # Setup Sensor Pins (using settings.py imports)
        GPIO.setup([S0, S1, S2, S3, TSC_LED], GPIO.OUT)
        GPIO.setup(OUT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.output(S0, GPIO.HIGH) # Set frequency scaling to 20%
        GPIO.output(S1, GPIO.LOW)

        # Setup LED Pins (using settings.py imports)
        GPIO.setup([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.OUT)
        GPIO.output([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.LOW) # Start with LED off

        self.filters = {
            'Red': (GPIO.LOW, GPIO.LOW),
            'Green': (GPIO.HIGH, GPIO.HIGH),
            'Blue': (GPIO.LOW, GPIO.HIGH)
        }
        self.led_pins = {
            'Red': RED_PIN,
            'Green': GREEN_PIN,
            'Blue': BLUE_PIN
        }
        self.last_color = None # For sensor reading optimization
        GPIO.output(TSC_LED, GPIO.LOW) # Turn off TSC LED

    def _set_led_color(self, color_name):
        """Sets the RGB LED to the specified color."""
        # Turn off all LEDs first
        GPIO.output([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.LOW)
        if color_name in self.led_pins:
            GPIO.output(self.led_pins[color_name], GPIO.HIGH)
        # No 'White' signal needed anymore
        # 'Off' is handled by turning all off initially or when 'Off' is passed

    # --- Sensor Reading Logic from User's Working Example ---
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
        # Count rising edges within the time window
        last_state = GPIO.input(OUT)
        while time.monotonic() < end_time:
            current_state = GPIO.input(OUT)
            if current_state == GPIO.HIGH and last_state == GPIO.LOW:
                count += 1
            last_state = current_state
            # Small delay to avoid excessive CPU usage, adjust if needed
            time.sleep(0.00005) # 50 microseconds
        return count

    def read_interval(self):
        """Read all 4 samples within TIME_BETWEEN"""
        start = time.monotonic()
        votes = []
        readings = {} # Store last readings for debugging

        for _ in range(4):
            sample_start = time.monotonic()
            readings = {} # Reset readings for each sample

            # Read all three colors quickly
            for color in ['Red', 'Green', 'Blue']:
                readings[color] = self._read_color(color)

            # Determine dominant color for this sample
            # Find the color with the maximum reading, default to 'Off' if all are 0 or negative
            max_reading = 0 # Use 0 as threshold, any pulse counts
            dominant_color = 'Off'
            # Sort by reading descending to handle ties (e.g., prefer R over G if R=G) - order matters
            sorted_readings = sorted(readings.items(), key=lambda item: item[1], reverse=True)
            if sorted_readings and sorted_readings[0][1] > max_reading:
                 dominant_color = sorted_readings[0][0] # Get the color name with the highest reading

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
                 # Use Counter on the filtered list
                 majority = Counter(filtered_votes).most_common(1)[0][0]

        # Debug print - Consider reducing frequency or removing in production
        print(f"Detected: {majority} | Samples: {votes} | Last Readings: {readings} | "
              f"Actual Interval: {time.monotonic() - start:.3f}s")
        return majority # Return the detected color
    # --- End Sensor Reading Logic ---

    def read(self, num_bits):
        """
        Reads a specified number of bits/colors directly without start/stop signals.
        """
        detected_colors = []
        intervals_read = 0

        print(f"[{os.getpid()}] Read: Starting direct read for {num_bits} bits...")
        try:
            # Read Data Bits directly
            while intervals_read < num_bits:
                cycle_start = time.monotonic()
                detected_color = self.read_interval()
                detected_colors.append(detected_color)
                intervals_read += 1

                # Maintain exact interval timing
                elapsed = time.monotonic() - cycle_start
                if elapsed < self.TIME_BETWEEN:
                    time.sleep(self.TIME_BETWEEN - elapsed)
                else:
                    print(f"[{os.getpid()}] Read Warning: Interval overrun by {elapsed - self.TIME_BETWEEN:.3f}s at bit {intervals_read}")


            print(f"[{os.getpid()}] Read: Finished. Detected {len(detected_colors)} colors.")
            return detected_colors

        except KeyboardInterrupt:
            print(f"\n[{os.getpid()}] Read: Operation interrupted by user.")
            return None # Indicate interruption
        except Exception as e:
            print(f"[{os.getpid()}] Read Error: An exception occurred during read: {e}")
            # Consider logging the full traceback here for debugging
            # import traceback
            # traceback.print_exc()
            return None # Indicate error


    def write(self, hex_data):
        """Encodes hex_data into colors using BB84 logic and displays on RGB LED."""
        print(f"Writing data to hardware QKD node: {hex_data}")
        if GPIO is None:
            print("Error: GPIO library not available.")
            return [] # Return empty list or raise error

        # Convert hex to binary string
        try:
            data = bin(int(hex_data, 16))[2:].zfill(len(hex_data) * 4)
        except ValueError:
             print(f"Error: Invalid hex data provided: {hex_data}")
             return []

        picked_bases = []
        print(f"  Will transmit {len(data)} bits.")

        try:
            # No Start Signal needed
            # Optional short delay before starting data transmission
            time.sleep(self.TIME_BETWEEN / 2)

            for i, bit in enumerate(data):
                start_time = time.perf_counter() # Use perf_counter for timing
                # Pick a random basis ('+' or 'X')
                random_base = self.basis[os.urandom(1)[0] % 2]
                picked_bases.append(random_base)
                # Convert the bit to the corresponding color based on the chosen basis
                color_to_display = self.colors[random_base][bit]

                # Debug print - check if this appears in Alice's log
                print(f"  Bit {i+1}/{len(data)}: {bit}, Basis: {random_base}, Color: {color_to_display}")
                self._set_led_color(color_to_display) # This should light up the LED

                # Use precise timing, accounting for the time taken by GPIO calls etc.
                elapsed = time.perf_counter() - start_time
                remaining = self.TIME_BETWEEN - elapsed

                if remaining > 0:
                    time.sleep(remaining)
                else:
                    # This indicates the loop iteration took longer than TIME_BETWEEN
                    print(f"  WARNING: Frame overrun by {-remaining*1000:.1f}ms at bit {i+1}")

            # No End Signal needed
            self._set_led_color('Off') # Turn LED off finally
            print("Write finished.")

        except Exception as e:
            print(f"An error occurred during write: {e}")
            # Consider logging the full traceback here for debugging
            # import traceback
            # traceback.print_exc()
        finally:
            # Ensure LED is off even if an error occurs
            self._set_led_color('Off')
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
                    self._set_led_color(color) # Set LED color

                    # Read sensor while LED is on (useful for debugging calibration)
                    # detected = self.read_interval()
                    # print(f"    Sensor saw: {detected}")

                    # Precise timing
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

    def cleanup(self):
        """Cleans up GPIO resources."""
        if GPIO:
            print("Cleaning up GPIO...")
            GPIO.cleanup()

if __name__ == "__main__":
    try:
        # Example usage of QKD_Node_Hardware
        node = QKD_Node_Hardware(time_between=1.0)  # Set time_between to 1 second

        # Perform calibration
        node.calibrate(n=3)  # Perform 3 calibration cycles

        # Example write operation
        hex_data = "1A3F"  # Example hexadecimal data to transmit
        node.write(hex_data)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Ensure GPIO cleanup on exit
        if 'node' in locals():
            node.cleanup()
            