"""
ADS1293 ECG Viewer
Real-time ECG data visualization from ESP32
"""

import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import numpy as np
import sys

# Configuration
WINDOW_SIZE = 1000  # Number of samples to display
BAUD_RATE = 115200

class ECGViewer:
    def __init__(self, port, baud_rate=115200):
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None

        # Data buffers
        self.timestamps = deque(maxlen=WINDOW_SIZE)
        self.ecg_data = deque(maxlen=WINDOW_SIZE)

        # Statistics
        self.sample_count = 0
        self.min_val = float('inf')
        self.max_val = float('-inf')

        # Setup plot
        self.fig, self.ax = plt.subplots(figsize=(12, 6))
        self.line, = self.ax.plot([], [], 'b-', linewidth=0.8)

        self.ax.set_xlim(0, WINDOW_SIZE)
        self.ax.set_ylim(-10, 10)  # FIXED SCALE: ±10mV
        self.ax.set_xlabel('Sample')
        self.ax.set_ylabel('ECG Signal (mV, DC Removed)')
        self.ax.set_title('ADS1293 Real-time ECG - Fixed Y-Axis (±10mV)')
        self.ax.grid(True, alpha=0.3)

        # Status text
        self.status_text = self.ax.text(0.02, 0.98, '',
                                        transform=self.ax.transAxes,
                                        verticalalignment='top',
                                        fontsize=9,
                                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    def connect(self):
        """Connect to serial port"""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            print(f"Connected to {self.port} at {self.baud_rate} baud")

            # Brief wait for device initialization
            print("Waiting for device initialization...")
            import time
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            print("Starting data acquisition...\n")

            return True
        except Exception as e:
            print(f"Error connecting: {e}")
            return False

    def read_data(self):
        """Read and parse data from serial port"""
        if self.ser and self.ser.in_waiting:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()

                # Skip diagnostic/comment lines
                if line.startswith('#'):
                    print(line)  # Print diagnostic messages to console
                    return False

                # Parse CSV format: timestamp,raw_value,ac_signal_mV
                if ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        try:
                            timestamp = int(parts[0])
                            raw_value = int(parts[1])
                            ac_signal_mV = float(parts[2])

                            # Plot the AC signal (DC removed)
                            self.timestamps.append(self.sample_count)
                            self.ecg_data.append(ac_signal_mV)

                            self.sample_count += 1
                            self.min_val = min(self.min_val, ac_signal_mV)
                            self.max_val = max(self.max_val, ac_signal_mV)

                            return True
                        except ValueError:
                            # Skip lines with non-numeric data
                            pass
            except Exception as e:
                # Skip malformed lines
                pass

        return False

    def update_plot(self, frame):
        """Animation update function"""
        # Read new data
        for _ in range(10):  # Read up to 10 samples per frame
            self.read_data()

        # Update plot data
        if len(self.ecg_data) > 0:
            self.line.set_data(list(self.timestamps), list(self.ecg_data))

            # FIXED Y-axis scale - no auto-scaling
            # ECG signals are typically ±5mV after DC removal
            # Fixed scale prevents "zoom in on noise" problem
            self.ax.set_ylim(-10, 10)

            # Update X axis to show latest data
            if len(self.timestamps) >= WINDOW_SIZE:
                self.ax.set_xlim(self.timestamps[0], self.timestamps[-1])

            # Update status text
            sample_rate = 0
            if len(self.timestamps) > 1:
                time_span = (self.timestamps[-1] - self.timestamps[0])
                if time_span > 0:
                    sample_rate = len(self.timestamps) / (time_span / 1.0)

            status = f'Samples: {self.sample_count}\n'
            status += f'Rate: {sample_rate:.1f} samples/sec\n'
            status += f'Current: {self.ecg_data[-1] if self.ecg_data else 0}\n'
            status += f'Min: {self.min_val if self.min_val != float("inf") else 0}\n'
            status += f'Max: {self.max_val if self.max_val != float("-inf") else 0}'

            self.status_text.set_text(status)

        return self.line, self.status_text

    def start(self):
        """Start real-time plotting"""
        if not self.connect():
            return

        print("Starting ECG viewer...")
        print("Close the plot window to exit")

        # Create animation
        ani = animation.FuncAnimation(
            self.fig,
            self.update_plot,
            interval=50,  # Update every 50ms (20 FPS)
            blit=True,
            cache_frame_data=False
        )

        plt.show()

        # Cleanup
        if self.ser:
            self.ser.close()
            print("Disconnected")

def list_ports():
    """List available COM ports"""
    ports = serial.tools.list_ports.comports()
    print("\nAvailable COM ports:")
    for i, port in enumerate(ports):
        print(f"  {i+1}. {port.device} - {port.description}")
    return ports

if __name__ == "__main__":
    print("=" * 50)
    print("ADS1293 ECG Viewer")
    print("=" * 50)

    # List available ports
    ports = list_ports()

    if not ports:
        print("No COM ports found!")
        sys.exit(1)

    # Select port
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        print("\nEnter COM port number (or full port name): ", end='')
        selection = input().strip()

        try:
            port_num = int(selection)
            if 1 <= port_num <= len(ports):
                port = ports[port_num - 1].device
            else:
                print("Invalid port number!")
                sys.exit(1)
        except ValueError:
            port = selection

    print(f"\nUsing port: {port}")

    # Start viewer
    try:
        viewer = ECGViewer(port, BAUD_RATE)
        viewer.start()
    except KeyboardInterrupt:
        print("\nExiting...")
