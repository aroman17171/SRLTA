
import time

class RealTimeCoach:
    def __init__(self, speaker):
        self.speaker = speaker
        self.current_corner_index = 0
        self.last_callout_time = 0.0
        # Per-message cooldown. Short enough that entry + braking + exit
        # messages for the same corner can all fire, but long enough to
        # prevent one message from repeating dozens of times per second.
        self.cooldown = 0.6
        # Per-corner de-duplication: only one of each kind per corner.
        self._last_message_per_corner = {}

    def reset(self):
        self.current_corner_index = 0
        self._last_message_per_corner = {}
        self.last_callout_time = 0.0

    def update(self, frame, best_lap, corners):
        if not corners or not best_lap:
            return

        distance = frame["distance"]
        speed = frame["speed"]
        brake = frame.get("brake", 0)

        # Past the last corner? Nothing left to say.
        if self.current_corner_index >= len(corners):
            return

        corner = corners[self.current_corner_index]
        corner_num = self.current_corner_index + 1
        entry = corner.entry_distance
        apex = corner.apex_distance

        # ── Advance past this corner once distance is comfortably beyond
        # the apex. This is the key fix: previously the index only advanced
        # inside the narrow apex+40m exit window, so if your live apex
        # differed from the reference by even 50m, the coach got stuck.
        if distance > apex + 60:
            self.current_corner_index += 1
            return

        # ── Entry window: 80m before entry to entry point
        if entry - 80 < distance < entry:
            try:
                best_entry_speed = best_lap.get_speed_at_distance(entry)
            except Exception:
                return
            if speed < best_entry_speed - 5:
                self._say_once(corner_num, "entry_speed",
                               f"Turn {corner_num} — carry more speed in")
            elif speed > best_entry_speed + 5:
                self._say_once(corner_num, "entry_speed",
                               f"Turn {corner_num} — you're going in too hot")

            # Brake point comparison (how early/late vs reference)
            try:
                ref_brake_idx = self._find_ref_brake(best_lap, entry, lookback=120)
            except Exception:
                ref_brake_idx = None
            if ref_brake_idx is not None:
                diff = distance - ref_brake_idx
                if diff > 12:
                    self._say_once(corner_num, "brake_point",
                                   f"Turn {corner_num} — braking {diff:.0f} meters too early")
                elif diff < -12:
                    self._say_once(corner_num, "brake_point",
                                   f"Turn {corner_num} — braking {abs(diff):.0f} meters too late")

        # ── Mid-corner: between entry and apex
        if entry < distance < apex:
            try:
                best_brake = best_lap.get_brake_at_distance(entry)
            except Exception:
                return
            if brake > best_brake + 0.2:
                self._say_once(corner_num, "brake_amount",
                               f"Turn {corner_num} — too much brake")
            elif brake < best_brake - 0.2 and brake > 0.1:
                self._say_once(corner_num, "brake_amount",
                               f"Turn {corner_num} — brake harder")

        # ── Exit: just past apex
        if apex < distance < apex + 80:
            try:
                best_exit_speed = best_lap.get_speed_at_distance(apex + 30)
            except Exception:
                return
            if speed < best_exit_speed - 5:
                self._say_once(corner_num, "exit_speed",
                               f"Turn {corner_num} — focus on exit speed")

    def _find_ref_brake(self, best_lap, entry_distance, lookback=120):
        """Find the distance where the reference lap first braked >0.3
        in the 120m window before the corner entry."""
        if not best_lap.has_channel("brake"):
            return None
        try:
            d = best_lap.get_channel("distance")
            b = best_lap.get_channel("brake")
        except Exception:
            return None
        start = max(0, entry_distance - lookback)
        # Walk forward from start, find first index where brake > 0.3
        for i in range(len(d)):
            if d[i] < start:
                continue
            if d[i] > entry_distance:
                break
            if b[i] > 0.3:
                return float(d[i])
        return None

    def _say_once(self, corner_num, kind, text):
        """Fire a message, but only once per (corner, kind) pair and only
        if the global cooldown has elapsed."""
        key = (corner_num, kind)
        if key in self._last_message_per_corner:
            return
        now = time.time()
        if now - self.last_callout_time < self.cooldown:
            # Still throttle so we don't back-to-back speak, but remember
            # we wanted to say this so it doesn't get re-attempted next frame.
            self._last_message_per_corner[key] = -1  # -1 = suppressed
            return
        self._last_message_per_corner[key] = now
        self.last_callout_time = now
        print(f"[COACH] {text}")
        if self.speaker:
            try:
                self.speaker.say(text)
            except Exception as e:
                print(f"Speaker error: {e}")

    def say(self, text):
        """Legacy public method used by the original code path."""
        now = time.time()
        if now - self.last_callout_time > self.cooldown:
            print(f"[COACH] {text}")
            if self.speaker:
                self.speaker.say(text)
            self.last_callout_time = now
