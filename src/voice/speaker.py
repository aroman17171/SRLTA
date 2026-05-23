"""
SRLTA Voice Coaching
"""

import pyttsx3


class Speaker:
    def __init__(self, rate=185, volume=1.0):
        self.rate = rate
        self.volume = volume

    def say(self, message: str):
        """Reinitialize engine each call — fixes Windows reuse bug."""
        engine = pyttsx3.init()
        engine.setProperty('rate', self.rate)
        engine.setProperty('volume', self.volume)
        engine.say(message)
        engine.runAndWait()
        engine.stop()

    def say_lap_result(self, stats: dict, zones: list):
        total = stats['total_delta']
        sectors = stats['sector_deltas']

        if abs(total) < 0.05:
            message = "Nearly identical lap time."
        elif total < 0:
            message = f"Lap faster by {abs(total):.2f} seconds. "
        else:
            message = f"Lap slower by {abs(total):.2f} seconds. "

        sector_items = list(sectors.items())
        best = min(sector_items, key=lambda x: x[1])
        worst = max(sector_items, key=lambda x: x[1])

        sector_names = {
            'sector_1': 'sector 1',
            'sector_2': 'sector 2',
            'sector_3': 'sector 3'
        }

        if best[1] < -0.05:
            message += f"Best in {sector_names[best[0]]}, gained {abs(best[1]):.2f}. "

        if worst[1] > 0.05:
            message += f"Lost {abs(worst[1]):.2f} in {sector_names[worst[0]]}. "

        losses = [z for z in zones if z['type'] == 'loss']
        if losses:
            biggest_loss = max(losses, key=lambda z: z['delta_change'])
            message += (
                f"Biggest loss around {biggest_loss['start_distance']:.0f} meters, "
                f"{biggest_loss['delta_change']:.2f} seconds."
            )

        self.say(message)

    def test(self):
        self.say("Sim Racing Lap Time Analyzer voice coaching active. Ready to race.")