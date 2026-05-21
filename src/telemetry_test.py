import numpy as np
import matplotlib.pyplot as plt

# fake "distance" along track
distance = np.linspace(0, 1000, 200)

# fake lap 1 (faster)
lap1_speed = 120 - 0.02 * distance + np.random.normal(0, 2, 200)

# fake lap 2 (slower)
lap2_speed = 115 - 0.018 * distance + np.random.normal(0, 2, 200)

plt.plot(distance, lap1_speed, label="Lap 1")
plt.plot(distance, lap2_speed, label="Lap 2")

plt.xlabel("Distance (m)")
plt.ylabel("Speed")
plt.title("SRLTA Test: Fake Lap Comparison")
plt.legend()

plt.show()