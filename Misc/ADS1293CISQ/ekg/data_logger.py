"""
ADS1293 Data Logger and Analyzer
Captures ECG data and performs statistical analysis
"""

import serial
import serial.tools.list_ports
import sys
import time
import numpy as np

def list_ports():
    """List available COM ports"""
    ports = serial.tools.list_ports.comports()
    print("\nAvailable COM ports:")
    for i, port in enumerate(ports):
        print(f"  {i+1}. {port.device} - {port.description}")
    return ports

def capture_data(port, baud_rate=115200, num_samples=500):
    """Capture data samples from serial port"""
    print(f"\nConnecting to {port}...")

    try:
        ser = serial.Serial(port, baud_rate, timeout=2)
        print("Connected!")

        # Wait for initialization
        print("Waiting 3 seconds for device initialization...")
        time.sleep(3)
        ser.reset_input_buffer()

        print(f"\nCapturing {num_samples} samples...")
        samples = []
        timestamps = []
        skipped = 0

        while len(samples) < num_samples:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()

                    # Parse CSV: timestamp,value
                    if ',' in line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                timestamp = int(parts[0])
                                value = int(parts[1])

                                timestamps.append(timestamp)
                                samples.append(value)

                                # Progress indicator
                                if len(samples) % 50 == 0:
                                    print(f"  Captured {len(samples)}/{num_samples} samples...")
                            except ValueError:
                                skipped += 1
                except Exception as e:
                    skipped += 1

        ser.close()
        print(f"\nCapture complete! ({skipped} lines skipped)")

        return np.array(timestamps), np.array(samples)

    except Exception as e:
        print(f"Error: {e}")
        return None, None

def analyze_data(timestamps, samples):
    """Analyze captured ECG data"""
    print("\n" + "="*60)
    print("DATA ANALYSIS")
    print("="*60)

    # Basic statistics
    print("\n--- Basic Statistics ---")
    print(f"Number of samples: {len(samples)}")
    print(f"Min value: {np.min(samples)}")
    print(f"Max value: {np.max(samples)}")
    print(f"Mean value: {np.mean(samples):.2f}")
    print(f"Median value: {np.median(samples):.2f}")
    print(f"Std deviation: {np.std(samples):.2f}")
    print(f"Peak-to-peak: {np.max(samples) - np.min(samples)}")

    # Check for saturation (24-bit ADC: -8388608 to 8388607)
    print("\n--- Saturation Check ---")
    if np.min(samples) <= -8000000:
        print("WARNING: Near negative saturation!")
    elif np.max(samples) >= 8000000:
        print("WARNING: Near positive saturation!")
    else:
        print(f"OK - Range within limits ({np.min(samples)} to {np.max(samples)})")

    # Sample rate calculation
    print("\n--- Sample Rate ---")
    if len(timestamps) > 1:
        time_span = (timestamps[-1] - timestamps[0]) / 1000.0  # Convert to seconds
        sample_rate = len(timestamps) / time_span
        print(f"Time span: {time_span:.2f} seconds")
        print(f"Calculated rate: {sample_rate:.1f} Hz")

    # Variation analysis
    print("\n--- Signal Variation ---")
    range_val = np.max(samples) - np.min(samples)

    if range_val == 0:
        print("ERROR: All samples identical - no variation!")
        print("  -> ADC not updating or stuck")
    elif range_val < 100:
        print(f"Very low noise: {range_val} counts")
        print("  -> Good baseline with floating/open inputs")
    elif range_val < 10000:
        print(f"Low variation: {range_val} counts")
        print("  -> Normal for disconnected leads or low-level noise")
    elif range_val < 100000:
        print(f"Moderate variation: {range_val} counts")
        print("  -> Could be 50/60Hz pickup or small signals")
    else:
        print(f"Large variation: {range_val} counts")
        print("  -> Strong signal, mains pickup, or oscillation")

    # Check for constant value
    unique_values = len(np.unique(samples))
    print(f"\nUnique values: {unique_values} out of {len(samples)}")
    if unique_values == 1:
        print("  -> WARNING: Only one unique value!")
    elif unique_values < 10:
        print("  -> WARNING: Very few unique values - possible issue")

    # Show first and last 10 samples
    print("\n--- First 10 Samples ---")
    for i in range(min(10, len(samples))):
        print(f"  {i}: {samples[i]}")

    print("\n--- Last 10 Samples ---")
    for i in range(max(0, len(samples)-10), len(samples)):
        print(f"  {i}: {samples[i]}")

    # Expected behavior for floating inputs
    print("\n--- Expected Behavior for Floating Inputs ---")
    print("With leads disconnected/floating on table:")
    print("  • Should see random noise from environmental pickup")
    print("  • Typical range: 1,000 - 100,000 counts")
    print("  • May see 50/60Hz if near power lines")
    print("  • Values should change over time")

    # Interpretation
    print("\n--- Interpretation ---")
    if range_val == 0:
        print("❌ PROBLEM: ADC not working or data path broken")
    elif range_val < 100:
        print("✓ GOOD: Low noise baseline, ADC working")
        print("  (For disconnected inputs, this is expected)")
    elif 100 <= range_val < 100000:
        print("✓ NORMAL: Reasonable noise pickup for floating inputs")
    else:
        print("⚠ HIGH: Large variations - check for:")
        print("  • Mains (50/60Hz) coupling")
        print("  • Oscillation")
        print("  • Incorrect gain settings")

if __name__ == "__main__":
    print("="*60)
    print("ADS1293 DATA LOGGER AND ANALYZER")
    print("="*60)

    # List and select port
    ports = list_ports()

    if not ports:
        print("No COM ports found!")
        sys.exit(1)

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

    # Capture data
    timestamps, samples = capture_data(port, num_samples=500)

    if samples is not None and len(samples) > 0:
        # Analyze
        analyze_data(timestamps, samples)

        # Save to file
        filename = f"ecg_data_{int(time.time())}.csv"
        print(f"\n--- Saving Data ---")
        print(f"Saving to {filename}...")
        np.savetxt(filename, np.column_stack((timestamps, samples)),
                   delimiter=',', header='timestamp_ms,value', comments='', fmt='%d')
        print("Saved!")
    else:
        print("Failed to capture data!")
