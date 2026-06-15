import RPi.GPIO as GPIO
from rpi_ws281x import Adafruit_NeoPixel, Color
import torch
from torchvision import models, transforms
from torchvision.models.quantization import MobileNet_V2_QuantizedWeights
import ast
import time
import threading
import queue
from CameraServerClass import CameraServer
from TRSensors import TRSensor
from ServoControllerClass import ServoController

import multiprocessing as mp
import queue as standard_queue

# LED strip configuration constants:
LED_COUNT      = 4      # Number of LED pixels.
LED_PIN        = 18     # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ    = 800000 # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 5      # DMA channel to use for generating signal (try 5)
LED_BRIGHTNESS = 255    # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False  # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0

# Global flag to shutdown (threading.Event is thread-safe and GIL-friendly)
stop_event = threading.Event()
# Proportional and Derivative controller constants
KP = 0.06
KD = 0.008
CENTER = 2000  # Sensor center value
SPEED = 10
SHARP_THRESHOLD = 1200

# ImageNet class IDs for our target objects
SHOE_CLASS_IDS = {770, 788}          # running shoe, shoe shop
BOTTLE_CLASS_IDS = {440, 720, 737, 898, 907}  # beer/pill/pop/water/wine bottle
MUG_CUP_CLASS_IDS = {504, 647, 968}  # coffee mug, measuring cup, cup

class AlphaBot2(object):
    def __init__(self):
        self.AIN1 = 12
        self.AIN2 = 13
        self.BIN1 = 20
        self.BIN2 = 21
        self.ENA = 6
        self.ENB = 26
        self.PA = 25
        self.PB = 25
        self.last_proportional = 0
        self._last_time = time.monotonic()
        self._line_lost = False
        self._lost_line_time = 0.0
        self._recover_direction = 0
        self.maximum = 25
        self.DR = 16
        self.DL = 19
        self.CS = 5
        self.Clock = 25
        self.Address = 24
        self.DataOut = 23
        self.Buzzer = 4
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        motor_pins = [self.AIN1, self.AIN2, self.BIN1, self.BIN2, self.ENA, self.ENB]
        for pin in motor_pins:
            GPIO.setup(pin, GPIO.OUT)
        GPIO.setup(self.Clock, GPIO.OUT)
        GPIO.setup(self.CS, GPIO.OUT)
        GPIO.setup(self.Address, GPIO.OUT)
        GPIO.setup(self.DataOut, GPIO.IN, GPIO.PUD_UP)
        GPIO.setup(self.Buzzer, GPIO.OUT)
        GPIO.setup(self.DR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.DL, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.PWMA = GPIO.PWM(self.ENA, 500)
        self.PWMB = GPIO.PWM(self.ENB, 500)
        self.PWMA.start(0)
        self.PWMB.start(0)
        self.stop()
        # Initialize distance sensors
        self.DR_status = 1
        self.DL_status = 1
        # Initialize additional components
        self.tr_sensor = TRSensor()
        self.servo = ServoController()
        self.camera_server = CameraServer()
        # LED Strip Initialization
        self.led_strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ,
                                            LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        self.led_strip.begin()
        # Beep queue for asynchronous buzzing
        self.beep_queue = queue.Queue()
        # Initialize object recognition model and labels
        self.object_model = None
        self.imagenet_classes = None
        self.load_object_recognition_model()

    def setMotor(self, left, right):
        """
        left/right: -100 to +100
        positive = forward
        negative = backward
        """

        # clamp values
        left = max(-100, min(100, left))
        right = max(-100, min(100, right))

        # LEFT MOTOR
        if left >= 0:
            GPIO.output(self.AIN1, GPIO.LOW)
            GPIO.output(self.AIN2, GPIO.HIGH)
            self.PWMA.ChangeDutyCycle(left)
        else:
            GPIO.output(self.AIN1, GPIO.HIGH)
            GPIO.output(self.AIN2, GPIO.LOW)
            self.PWMA.ChangeDutyCycle(-left)

        # RIGHT MOTOR
        if right >= 0:
            GPIO.output(self.BIN1, GPIO.LOW)
            GPIO.output(self.BIN2, GPIO.HIGH)
            self.PWMB.ChangeDutyCycle(right)
        else:
            GPIO.output(self.BIN1, GPIO.HIGH)
            GPIO.output(self.BIN2, GPIO.LOW)
            self.PWMB.ChangeDutyCycle(-right)

    # SAFE STOP
    def stop(self):
        self.PWMA.ChangeDutyCycle(0)
        self.PWMB.ChangeDutyCycle(0)

        GPIO.output(self.AIN1, GPIO.LOW)
        GPIO.output(self.AIN2, GPIO.LOW)
        GPIO.output(self.BIN1, GPIO.LOW)
        GPIO.output(self.BIN2, GPIO.LOW)

    # compatibility aliases for old code
    def setPWMA(self, duty):
        self.PWMA.ChangeDutyCycle(max(0, min(100, duty)))

    def setPWMB(self, duty):
        self.PWMB.ChangeDutyCycle(max(0, min(100, duty)))

    def load_object_recognition_model(self):
        try:
            self.object_model = models.quantization.mobilenet_v2(
                weights=MobileNet_V2_QuantizedWeights.IMAGENET1K_QNNPACK_V1,
                quantize=True
            )
            self.object_model.eval()
            with open("imagenet1000_clsidx_to_labels.txt", "r") as f:
                labels_dict = ast.literal_eval(f.read())
                self.imagenet_classes = [labels_dict[i] for i in range(len(labels_dict))]
            # Cache the preprocessing pipeline (avoids recreating it every inference call)
            self.preprocess = transforms.Compose([
                transforms.ToTensor(),
                transforms.Resize((224, 224)),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225]),
            ])
            print("Object recognition model loaded successfully.")
        except Exception as e:
            print("Error loading object recognition model:", e)
            self.object_model = None
            self.imagenet_classes = None
            self.preprocess = None

    def set_led(self, index, r, g, b):
        """Set a single LED's color."""
        if 0 <= index < LED_COUNT:
            self.led_strip.setPixelColor(index, Color(r, g, b))

    def update_leds(self):
        """Update the LED strip to show the current colors."""
        self.led_strip.show()

    def clear_leds(self):
        """Turn off all LEDs."""
        for i in range(LED_COUNT):
            self.led_strip.setPixelColor(i, Color(0, 0, 0))
        self.led_strip.show()

    def set_leds_default(self):
        """Set a default pattern on the LED strip."""
        self.set_led(0, 255, 0, 0)    # Red
        self.set_led(1, 0, 255, 0)    # Green
        self.set_led(2, 0, 0, 255)    # Blue
        self.set_led(3, 255, 255, 0)  # Yellow
        self.update_leds()
        time.sleep(2)
        self.clear_leds()

    def infrared_obstacle_check(self):
        self.DR_status = GPIO.input(self.DR)
        self.DL_status = GPIO.input(self.DL)
        return self.DL_status == 0 or self.DR_status == 0

    def buzzer_on(self):
        GPIO.output(self.Buzzer, GPIO.HIGH)

    def buzzer_off(self):
        GPIO.output(self.Buzzer, GPIO.LOW)

    # Camera and Recognition Methods
    def start_camera(self):
        self.servo.center() # Horizontal angle to middle
        self.servo.pwm.setServoPulse(1, 1500) # Vertical angle
        time.sleep(0.5)
        self.camera_server.start_server()

    def stop_camera(self):
        self.camera_server.stop_server()

    def recognize_object(self):
        if self.object_model is None or self.imagenet_classes is None or self.preprocess is None:
            print("Object recognition model not loaded. Cannot recognize object.")
            return None
        if not hasattr(self, 'camera_server') or not hasattr(self.camera_server, 'picam2'):
            print("Camera server or PiCamera2 not initialized for object recognition.")
            return None
        try:
            with torch.no_grad():
                frame = self.camera_server.picam2.capture_array()
                if frame is None:
                    print("No frame captured for object recognition.")
                    return None
                input_tensor = self.preprocess(frame)
                input_batch = input_tensor.unsqueeze(0)
                output = self.object_model(input_batch)
                probs = output[0].softmax(dim=0)
                top_prob, top_idx = torch.max(probs, dim=0)
                class_id = top_idx.item()
                class_name = self.imagenet_classes[class_id].lower()
                # print(f"Object Recognition: {top_prob.item() * 100:.2f}% {class_name}")
                
                # Match by exact class ID to avoid substring false positives
                # (e.g. 'cup' is a substring of 'porcupine')
                matched = False
                if top_prob.item() > 0.1:
                    if class_id in SHOE_CLASS_IDS:
                        for i in range(LED_COUNT): self.set_led(i, 255, 0, 0)      # Red
                        matched = True
                    elif class_id in BOTTLE_CLASS_IDS:
                        for i in range(LED_COUNT): self.set_led(i, 255, 255, 0)    # Yellow
                        matched = True
                    elif class_id in MUG_CUP_CLASS_IDS:
                        for i in range(LED_COUNT): self.set_led(i, 0, 255, 0)      # Green
                        matched = True
                
                if not matched:
                    for i in range(LED_COUNT): self.set_led(i, 0, 0, 0)
                
                self.update_leds()
                return class_name if matched else None
        except Exception as e:
            print(f"Error during object recognition: {e}")
            return None

    def follow_line(self):
        now = time.monotonic()          # monotonic: no NTP jumps, sub-ms resolution

        position, sensors = self.tr_sensor.readLine()
        proportional = position - CENTER
        black_count = sum(1 for v in sensors if v > 200)

        # ── Time-normalized derivative ─────────────────────────────────────
        # Without dt normalization, a GIL-delayed sample (e.g. 35ms instead of
        # 10ms) produces a 3.5x spike in the raw difference — causing a sharp
        # twitch exactly on hairpin approach when vision thread is most active.
        dt_ms = (now - self._last_time) * 1000.0   # convert to ms
        dt_ms = max(dt_ms, 1.0)                     # guard against zero/negative

        derivative = (proportional - self.last_proportional) / dt_ms

        # ── Separate P and D boosts ────────────────────────────────────────
        # Previously both P and D were boosted together, amplifying D-term noise
        # at the edges. P benefits from aggressive boost; D should stay calmer.
        p_boost = 1.0 + (0.6 * (abs(proportional) / 2000.0))   # 1.0x → 1.6x
        d_boost = 1.0 + (0.2 * (abs(proportional) / 2000.0))   # 1.0x → 1.2x

        power_difference = (KP * p_boost) * proportional + (KD * d_boost) * derivative

        # ── Hairpin pre-detection ──────────────────────────────────────────
        # On a sharp curve, the sensor position drifts fast toward the edge.
        # We detect this BEFORE losing the line by checking:
        #   (a) proportional is near max edge (|error| > SHARP_THRESHOLD)
        #   (b) error is still growing (derivative confirms same direction)
        # When both are true, we lock the turn direction and boost turn authority.
        approaching_hairpin = (
            abs(proportional) > SHARP_THRESHOLD and
            (proportional * derivative) > 0      # error growing in same direction
        )

        if approaching_hairpin:
            # Hard pivot: inner wheel reverses, outer wheel drives forward.
            # This is much tighter than a differential bias at SPEED=18.
            turn_speed = max(SPEED * 2, 30)
            if proportional > 0:
                self.setMotor(turn_speed, -turn_speed // 2)   # sharp right
            else:
                self.setMotor(-turn_speed // 2, turn_speed)   # sharp left
            # Store state before returning — do NOT skip last_proportional update
            self.last_proportional = proportional
            self._last_time = now
            return

        # ── Line lost recovery ─────────────────────────────────────────────
        if black_count == 0:
            recover_speed = max(SPEED * 3, 35)

            # Timeout: if we've been spinning > 600ms with no line found,
            # flip direction — we overshot the hairpin the other way
            time_lost = (now - self._lost_line_time) * 1000.0  # ms

            if not self._line_lost:
                # First frame of losing line: record time and use last known direction
                self._line_lost = True
                self._lost_line_time = now
                self._recover_direction = self.last_proportional

            if time_lost > 600:
                # Flip recovery direction — we overshot, try the other way
                self._recover_direction = -self._recover_direction
                self._lost_line_time = now   # reset timer so we get another 600ms

            if self._recover_direction > 0:
                self.setMotor(recover_speed, -recover_speed)
            else:
                self.setMotor(-recover_speed, recover_speed)

            self._last_time = now
            return   # do NOT update last_proportional during recovery

        # ── Normal tracking ────────────────────────────────────────────────
        self._line_lost = False   # reset recovery state as soon as line is found
        self.last_proportional = proportional
        self._last_time = now
        self.setMotor(SPEED - power_difference, SPEED + power_difference)

#########################################################################
if __name__ == '__main__':
    # 1. Setup Inter-Process Communication (IPC) Queues
    # These allow the isolated processes to safely talk to the main hardware process
    frame_queue = mp.Queue(maxsize=1)  # Main sends frames -> Vision
    led_queue = mp.Queue()             # Vision sends colors -> Main
    buzzer_queue = mp.Queue()          # Obstacle sends beep counts -> Main
    stop_event = mp.Event()            # Global kill switch

    # 2. Initialize Hardware in the MAIN Process Only
    bot = AlphaBot2()
    bot.set_led(2, 0, 0, 255)    # Blue
    bot.buzzer_on()
    time.sleep(0.1)
    bot.buzzer_off()
    
    bot.start_camera()
    print("Camera server started. Hardware initialized on Main Process.")
    time.sleep(2)
    bot.clear_leds()

    # Apply calibration
    bot.tr_sensor.calibratedMin = [210, 193, 218, 184, 247]
    bot.tr_sensor.calibratedMax = [956, 957, 960, 951, 949]

    # ── TASK 3: Vision / AI Inference (Mapped to a separate Core) ────────
    def vision_process(stop_flag, f_queue, l_queue):
        print("[Process-Vision] Initializing PyTorch locally...")
        # PyTorch MUST be initialized inside the new process's memory space
        local_model = models.quantization.mobilenet_v2(
            weights=MobileNet_V2_QuantizedWeights.IMAGENET1K_QNNPACK_V1,
            quantize=True
        )
        local_model.eval()
        
        with open("imagenet1000_clsidx_to_labels.txt", "r") as f:
            labels_dict = ast.literal_eval(f.read())
            imagenet_classes = [labels_dict[i] for i in range(len(labels_dict))]
            
        preprocess = transforms.Compose([
            transforms.ToTensor(),
            transforms.Resize((224, 224)),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        while not stop_flag.is_set():
            try:
                # Wait for a fresh frame from the main process
                frame = f_queue.get(timeout=1.0)
                if frame is not None:
                    with torch.no_grad():
                        input_tensor = preprocess(frame).unsqueeze(0)
                        output = local_model(input_tensor)
                        probs = output[0].softmax(dim=0)
                        top_prob, top_idx = torch.max(probs, dim=0)
                        class_id = top_idx.item()

                        if top_prob.item() > 0.1:
                            if class_id in SHOE_CLASS_IDS:
                                l_queue.put(("shoe", 255, 0, 0))       # Red
                            elif class_id in BOTTLE_CLASS_IDS:
                                l_queue.put(("bottle", 255, 255, 0))   # Yellow
                            elif class_id in MUG_CUP_CLASS_IDS:
                                l_queue.put(("mug", 0, 255, 0))        # Green
                            else:
                                l_queue.put(("clear", 0, 0, 0))
            except standard_queue.Empty:
                pass
            except Exception as e:
                print(f"Vision Error: {e}")

    # ── TASK 2: Obstacle Detection (Mapped to a separate Core) ──────────
    def obstacle_process(stop_flag, b_queue):
        print("[Process-Obstacle] Polling IR sensors...")
        # Re-setup GPIO pins locally for this process memory space
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP) # DR
        GPIO.setup(19, GPIO.IN, pull_up_down=GPIO.PUD_UP) # DL
        
        object_count = 0
        was_obstacle = False
        last_detect_time = time.time()
        
        while not stop_flag.is_set():
            # Local read of GPIO to avoid main process bottlenecks
            is_obstacle = (GPIO.input(19) == 0 or GPIO.input(16) == 0)
            
            if is_obstacle and not was_obstacle:
                current_time = time.time()
                if current_time - last_detect_time > 1.0:
                    object_count += 1
                    last_detect_time = current_time
                    # Determine buzz count based on requirement (1st=1, 2nd=2, 3rd=3)
                    buzzes = ((object_count - 1) % 3) + 1
                    b_queue.put(buzzes)
            was_obstacle = is_obstacle
            time.sleep(0.01)

    # ── Start the isolated processes ───────────────────────────────────
    p_vision = mp.Process(target=vision_process, args=(stop_event, frame_queue, led_queue))
    p_obstacle = mp.Process(target=obstacle_process, args=(stop_event, buzzer_queue))

    p_vision.start()
    p_obstacle.start()

    # ── TASK 1: MAIN PROCESS (Hardware Coordinator & Line Follower) ────
    try:
        print("[Process-Main] Running motor control and hardware coordination...")
        last_frame_time = 0
        
        while not stop_event.is_set():
            # 1. Highest Priority: Keep the robot on the line
            bot.follow_line()

            # 2. Feed the Vision process a frame every ~0.2 seconds
            current_time = time.time()
            if current_time - last_frame_time > 0.2:
                if frame_queue.empty():
                    frame = bot.camera_server.picam2.capture_array()
                    if frame is not None:
                        frame_queue.put(frame)
                last_frame_time = current_time

            # 3. Handle incoming LED requests from the Vision process
            try:
                color_cmd = led_queue.get_nowait()
                if color_cmd[0] == "clear":
                    bot.clear_leds()
                else:
                    for i in range(LED_COUNT): 
                        bot.set_led(i, color_cmd[1], color_cmd[2], color_cmd[3])
                    bot.update_leds()
            except standard_queue.Empty:
                pass

            # 4. Handle incoming Buzzer requests from the Obstacle process
            try:
                buzzes = buzzer_queue.get_nowait()
                # Non-blocking beep implementation integrated into the main loop
                for _ in range(buzzes):
                    bot.buzzer_on()
                    time.sleep(0.05)
                    bot.buzzer_off()
                    time.sleep(0.05)
            except standard_queue.Empty:
                pass

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected. Shutting down all cores...")
    finally:
        stop_event.set()
        
        # Safely shut down hardware
        bot.stop()
        bot.buzzer_off()
        bot.clear_leds()
        bot.stop_camera()
        bot.servo.stop()
        GPIO.cleanup()
        
        # Terminate worker processes
        p_vision.terminate()
        p_obstacle.terminate()
        p_vision.join()
        p_obstacle.join()
        
        print("All processes terminated. Exiting program.")