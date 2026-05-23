# test_ac_connection.py

import mmap
import ctypes
import time

class Physics(ctypes.Structure):
    _fields_ = [
        ("packetId", ctypes.c_int),
        ("gas", ctypes.c_float),
        ("brake", ctypes.c_float),
        ("fuel", ctypes.c_float),
        ("gear", ctypes.c_int),
        ("rpm", ctypes.c_int),
        ("steerAngle", ctypes.c_float),
        ("speedKmh", ctypes.c_float),
    ]

def read_physics():
    try:
        mm = mmap.mmap(-1, ctypes.sizeof(Physics), "acpmf_physics")
        data = Physics.from_buffer_copy(mm)
        return data
    except Exception:
        return None

print("Waiting for AC data...")

while True:
    physics = read_physics()

    if physics:
        print(f"Speed: {physics.speedKmh:.1f} km/h | Gear: {physics.gear} | RPM: {physics.rpm}")
    else:
        print("No data...")

    time.sleep(0.1)