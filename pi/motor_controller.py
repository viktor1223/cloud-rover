"""Motor controller — translates actions to PCA9685 I2C writes.

Maps high-level actions (FORWARD, LEFT, RIGHT, STOP) to 12 PWM channel
values on the PCA9685, which drives 2× L298N H-bridges controlling 4 motors.

Channel mapping matches diagram.json:

    PCA CH  →  L298N Pin        →  Motor
    ──────────────────────────────────────
    CH0     →  bridge_ab IN1    →  Front-Left direction A
    CH1     →  bridge_ab IN2    →  Front-Left direction B
    CH2     →  bridge_ab IN3    →  Front-Right direction A
    CH3     →  bridge_ab IN4    →  Front-Right direction B
    CH4     →  bridge_ab ENA    →  Front-Left speed (PWM)
    CH5     →  bridge_ab ENB    →  Front-Right speed (PWM)
    CH6     →  bridge_cd IN1    →  Rear-Left direction A
    CH7     →  bridge_cd IN2    →  Rear-Left direction B
    CH8     →  bridge_cd IN3    →  Rear-Right direction A
    CH9     →  bridge_cd IN4    →  Rear-Right direction B
    CH10    →  bridge_cd ENA    →  Rear-Left speed (PWM)
    CH11    →  bridge_cd ENB    →  Rear-Right speed (PWM)

Direction truth table (per motor channel on L298N):
    IN1=HIGH, IN2=LOW   →  Forward
    IN1=LOW,  IN2=HIGH  →  Reverse
    IN1=LOW,  IN2=LOW   →  Coast (free-spin)

Usage:
    On Pi:    python3 pi/motor_controller.py --test
    Dry run:  python3 pi/motor_controller.py --dry-run --test
"""

import sys
import os
import time

_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from shared.protocol import Action, MotorState

# ---------------------------------------------------------------------------
# PCA9685 channel assignments (from diagram.json)
# ---------------------------------------------------------------------------

# Front-left motor (bridge_ab channel A)
FL_IN1 = 0
FL_IN2 = 1
FL_ENA = 4

# Front-right motor (bridge_ab channel B)
FR_IN3 = 2
FR_IN4 = 3
FR_ENB = 5

# Rear-left motor (bridge_cd channel A)
RL_IN1 = 6
RL_IN2 = 7
RL_ENA = 10

# Rear-right motor (bridge_cd channel B)
RR_IN3 = 8
RR_IN4 = 9
RR_ENB = 11

# PWM constants
PWM_FREQ = 1000       # Hz — DC motor PWM frequency
DUTY_HIGH = 0xFFFF    # 100% duty = logic HIGH for direction pins
DUTY_LOW = 0x0000     # 0% duty = logic LOW

# Default speeds per discrete action (Phase 1)
DEFAULT_SPEEDS = {
    Action.FORWARD: 0.75,
    Action.LEFT: 0.50,
    Action.RIGHT: 0.50,
    Action.STOP: 0.00,
}


class MotorController:
    """Translates actions into PCA9685 PWM writes."""

    def __init__(self, dry_run: bool = False, i2c=None):
        self.dry_run = dry_run
        self._i2c = i2c  # shared I2C bus (optional, created if None)
        self.pca = None
        self.state = MotorState()

    def startup(self):
        if self.dry_run:
            print("  [dry-run] Motor controller ready (no hardware)")
            return

        from adafruit_pca9685 import PCA9685

        if self._i2c is None:
            import board
            import busio
            self._i2c = busio.I2C(board.SCL, board.SDA)

        self.pca = PCA9685(self._i2c)
        self.pca.frequency = PWM_FREQ
        self.stop()
        print(f"  ✓ PCA9685 ready at {PWM_FREQ} Hz")

    def shutdown(self):
        self.stop()
        if self.pca:
            self.pca.deinit()

    def _set_channel(self, channel: int, duty: int):
        if self.dry_run:
            pct = duty / 0xFFFF * 100
            print(f"    CH{channel:>2d} = 0x{duty:04X} ({pct:.0f}%)")
            return
        self.pca.channels[channel].duty_cycle = duty

    def _set_motor(self, in_a: int, in_b: int, en: int,
                   direction: str, speed: float):
        """Set a single motor's direction and speed.

        Args:
            in_a: PCA channel for IN1/IN3 (direction pin A)
            in_b: PCA channel for IN2/IN4 (direction pin B)
            en: PCA channel for ENA/ENB (speed PWM)
            direction: "forward", "reverse", or "stop"
            speed: 0.0–1.0 duty cycle
        """
        duty = int(max(0.0, min(1.0, speed)) * 0xFFFF)

        if direction == "forward":
            self._set_channel(in_a, DUTY_HIGH)
            self._set_channel(in_b, DUTY_LOW)
            self._set_channel(en, duty)
        elif direction == "reverse":
            self._set_channel(in_a, DUTY_LOW)
            self._set_channel(in_b, DUTY_HIGH)
            self._set_channel(en, duty)
        else:  # stop / coast
            self._set_channel(in_a, DUTY_LOW)
            self._set_channel(in_b, DUTY_LOW)
            self._set_channel(en, DUTY_LOW)

    def _set_left(self, direction: str, speed: float):
        """Set both left motors (front-left + rear-left)."""
        self._set_motor(FL_IN1, FL_IN2, FL_ENA, direction, speed)
        self._set_motor(RL_IN1, RL_IN2, RL_ENA, direction, speed)
        self.state.left_dir = direction
        self.state.left_duty = speed if direction != "stop" else 0.0

    def _set_right(self, direction: str, speed: float):
        """Set both right motors (front-right + rear-right)."""
        self._set_motor(FR_IN3, FR_IN4, FR_ENB, direction, speed)
        self._set_motor(RR_IN3, RR_IN4, RR_ENB, direction, speed)
        self.state.right_dir = direction
        self.state.right_duty = speed if direction != "stop" else 0.0

    def stop(self):
        """Coast all motors to stop."""
        self._set_left("stop", 0.0)
        self._set_right("stop", 0.0)

    def execute(self, action: str):
        """Execute a discrete action (FORWARD/LEFT/RIGHT/STOP).

        Uses fixed speed lookup (Phase 1). For skid-steer turns,
        left motors go backward and right motors go forward (LEFT),
        or vice versa (RIGHT), matching diagram.json motor_control_logic.
        """
        speed = DEFAULT_SPEEDS.get(Action(action), 0.0)

        if self.dry_run:
            print(f"  [dry-run] execute({action}, speed={speed})")

        if action == Action.FORWARD or action == Action.FORWARD.value:
            self._set_left("forward", speed)
            self._set_right("forward", speed)
        elif action == Action.LEFT or action == Action.LEFT.value:
            self._set_left("reverse", speed)
            self._set_right("forward", speed)
        elif action == Action.RIGHT or action == Action.RIGHT.value:
            self._set_left("forward", speed)
            self._set_right("reverse", speed)
        else:  # STOP
            self.stop()

    def get_state(self) -> MotorState:
        return self.state


# ---------------------------------------------------------------------------
# Self-test: cycle through all actions
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Motor controller test")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print PCA writes instead of sending I2C")
    parser.add_argument("--test", action="store_true",
                        help="Run action cycle test")
    args = parser.parse_args()

    mc = MotorController(dry_run=args.dry_run)
    mc.startup()

    if args.test:
        for action in [Action.FORWARD, Action.LEFT, Action.RIGHT, Action.STOP]:
            print(f"\n--- {action.value} ---")
            mc.execute(action.value)
            state = mc.get_state()
            print(f"  State: L={state.left_dir}@{state.left_duty:.0%}, "
                  f"R={state.right_dir}@{state.right_duty:.0%}")
            if not args.dry_run:
                time.sleep(2)

        print("\nDone.")

    mc.shutdown()
