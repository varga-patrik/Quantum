"""
Example script demonstrating how to use the CageRotatorController from device_hander.py

This script shows:
1. Connecting to a cage rotator device
2. Homing the device
3. Moving to specific angles
4. Getting current position
5. Properly disconnecting
"""

import logging
from device_hander import CageRotatorController

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    # Replace with your actual serial number
    SERIAL_NUMBER = "55526814"  # Example serial number
    
    # Create controller instance
    rotator = CageRotatorController(SERIAL_NUMBER)
    
    try:
        # Connect to the device
        print(f"\n=== Connecting to CageRotator {SERIAL_NUMBER} ===")
        rotator.connect()
        print("✓ Connected successfully\n")
        
        # Get current position
        current_pos = rotator.get_position()
        print(f"Current position: {current_pos:.2f} degrees\n")
        
        # Move to 45 degrees
        print("=== Moving to 45 degrees ===")
        rotator.move_to(45.0)
        current_pos = rotator.get_position()
        print(f"✓ Moved to {current_pos:.2f} degrees\n")
        
        # Move to 90 degrees
        print("=== Moving to 90 degrees ===")
        rotator.move_to(90.0)
        current_pos = rotator.get_position()
        print(f"✓ Moved to {current_pos:.2f} degrees\n")
        
        # Move back to 0 degrees
        print("=== Moving back to 0 degrees ===")
        rotator.move_to(0.0)
        current_pos = rotator.get_position()
        print(f"✓ Moved to {current_pos:.2f} degrees\n")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
    
    finally:
        # Always disconnect when done
        print("=== Disconnecting ===")
        rotator.disconnect()
        print("✓ Disconnected\n")


def example_with_context_manager():
    """
    Alternative approach using context manager (with statement)
    This automatically handles connect/disconnect
    """
    SERIAL_NUMBER = "55123456"  # Example serial number
    
    try:
        with CageRotatorController(SERIAL_NUMBER) as rotator:
            print("\n=== Using context manager ===")
            rotator.home()
            rotator.move_to(69.0)
            position = rotator.get_position()
            print(f"Final position: {position:.2f} degrees")
        # Device is automatically disconnected here
        print("✓ Context manager automatically disconnected device\n")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")


if __name__ == "__main__":
    # Run the main example
    main()
    
    # Uncomment to try the context manager approach
    # example_with_context_manager()
