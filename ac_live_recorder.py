import pyaccsharedmemory
import time
import csv

asm = pyaccsharedmemory.accSharedMemory()

data_log = []

print("Recording... Go on track. Ctrl+C to stop.")

try:
    while True:
        try:
            data = asm.get_shared_memory_data()
            physics = data.Physics

            speed = physics.speed_kmh
            gear = physics.gear

            data_log.append({
                "time": time.time(),
                "speed": speed,
                "gear": gear,
                "rpm": physics.rpm,
                "gas": physics.gas,
                "brake": physics.brake
            })

            print(speed, gear)

        except pyaccsharedmemory.SharedMemoryTimeout:
            # no data yet → just wait
            pass

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nSaving CSV...")

    if len(data_log) == 0:
        print("No data recorded.")
    else:
        with open("lap_data.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data_log[0].keys())
            writer.writeheader()
            writer.writerows(data_log)

        print("Saved lap_data.csv")