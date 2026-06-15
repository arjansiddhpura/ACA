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

# LED strip configuration constants:
LED_COUNT      = 4      # Number of LED pixels.
LED_PIN        = 18     # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ    = 800000 # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 5      # DMA channel to use for generating signal
LED_BRIGHTNESS = 255    # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False  # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0

# Global shutdown flag
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
        # Distance sensors
        self.DR_status = 1
        self.DL_status = 1
        # Peripherals
        self.tr_sensor = TRSensor()
        self.servo = ServoController()
        self.camera_server = CameraServer()
        # LED strip
        self.led_strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ,
                                            LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        self.led_strip.begin()
        # Queue beep patterns so obstacle polling does not block
        self.beep_queue = queue.Queue()
        # Object recognition
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

    # Stop both motors
    def stop(self):
        self.PWMA.ChangeDutyCycle(0)
        self.PWMB.ChangeDutyCycle(0)

        GPIO.output(self.AIN1, GPIO.LOW)
        GPIO.output(self.AIN2, GPIO.LOW)
        GPIO.output(self.BIN1, GPIO.LOW)
        GPIO.output(self.BIN2, GPIO.LOW)

    # Backward-compatible aliases
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
            # Build preprocessing once
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

    # Camera and recognition
    def start_camera(self):
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
                # Match by class id to avoid substring false positives.
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

        # Normalize derivative by loop time to reduce jitter when timing varies.
        dt_ms = (now - self._last_time) * 1000.0   # convert to ms
        dt_ms = max(dt_ms, 1.0)                     # guard against zero/negative

        derivative = (proportional - self.last_proportional) / dt_ms

        # Boost P more than D near the edges.
        p_boost = 1.0 + (0.6 * (abs(proportional) / 2000.0))
        d_boost = 1.0 + (0.2 * (abs(proportional) / 2000.0))

        power_difference = (KP * p_boost) * proportional + (KD * d_boost) * derivative

        # Early hairpin detection: large error and still moving away from center.
        approaching_hairpin = (
            abs(proportional) > SHARP_THRESHOLD and
            (proportional * derivative) > 0      # error growing in same direction
        )

        if approaching_hairpin:
            turn_speed = max(SPEED * 2, 30)
            if proportional > 0:
                self.setMotor(turn_speed, -turn_speed // 2)   # sharp right
            else:
                self.setMotor(-turn_speed // 2, turn_speed)   # sharp left
            self.last_proportional = proportional
            self._last_time = now
            return

        # Recovery spin when all sensors lose the line.
        if black_count == 0:
            recover_speed = max(SPEED * 3, 35)

            time_lost = (now - self._lost_line_time) * 1000.0  # ms

            if not self._line_lost:
                self._line_lost = True
                self._lost_line_time = now
                self._recover_direction = self.last_proportional

            if time_lost > 600:
                self._recover_direction = -self._recover_direction
                self._lost_line_time = now

            if self._recover_direction > 0:
                self.setMotor(recover_speed, -recover_speed)
            else:
                self.setMotor(-recover_speed, recover_speed)

            self._last_time = now
            return

        self._line_lost = False
        self.last_proportional = proportional
        self._last_time = now
        self.setMotor(SPEED - power_difference, SPEED + power_difference)

 #########################################################################
if __name__ == '__main__':
    bot = AlphaBot2()
    bot.set_led(2, 0, 0, 255)    # Blue
    bot.buzzer_on()
    time.sleep(0.1)
    bot.buzzer_off()
    bot.start_camera()
    print("Camera server started. Visit http://<your_pi_ip>:5000/ in your browser.")
    time.sleep(2)
    bot.clear_leds()

    ####### CALIBRATION PHASE
    # print("Calibrating... move robot over line")
    # Manual
    # while True:
        # print(bot.tr_sensor.AnalogRead())
        # time.sleep(0.1)

    # Automatic
    # for i in range(200):
        # if (i // 50) % 2 == 0:
            # bot.setMotor(10, -10)
        # else:
            # bot.setMotor(-10, 10)

        # bot.tr_sensor.calibrate()
        # time.sleep(0.02)

    # bot.stop()
    # print("Min:", bot.tr_sensor.calibratedMin)
    # print("Max:", bot.tr_sensor.calibratedMax)

    # print("Calibration done")
    # bot.tr_sensor.calibratedMin = [164, 142, 176, 138, 177]
    # bot.tr_sensor.calibratedMax = [971, 973, 975, 970, 978]
    
    bot.tr_sensor.calibratedMin = [210, 193, 218, 184, 247]
    bot.tr_sensor.calibratedMax = [956, 957, 960, 951, 949]

    print("Min:", bot.tr_sensor.calibratedMin)
    print("Max:", bot.tr_sensor.calibratedMax)

    # Thread tasks

    def line_following_task():
        """Tight PID loop — highest priority, fastest polling."""
        while not stop_event.is_set():
            bot.follow_line()
            time.sleep(0.01)

    def obstacle_detection_task():
        """Counts distinct obstacles via edge-detection on IR sensors with debouncing."""
        object_count = 0
        was_obstacle = False
        last_detect_time = 0
        while not stop_event.is_set():
            is_obstacle = bot.infrared_obstacle_check()
            if is_obstacle and not was_obstacle:
                current_time = time.time()
                # Debounce to avoid counting one obstacle multiple times.
                if current_time - last_detect_time > 1.0:
                    object_count += 1
                    last_detect_time = current_time
                    print(f"Task 2 (Obstacle Detection) - Obstacle detected! Count: {object_count}")
                    # Beep pattern cycles: 1, 2, 3.
                    buzzes = ((object_count - 1) % 3) + 1
                    bot.beep_queue.put(buzzes)
            was_obstacle = is_obstacle
            time.sleep(0.05)

    def beeper_task():
        """Handles asynchronous beeping so it doesn't block detection."""
        while not stop_event.is_set():
            try:
                buzzes = bot.beep_queue.get(timeout=0.1)
                for _ in range(buzzes):
                    if stop_event.is_set(): break
                    bot.buzzer_on()
                    time.sleep(0.1)
                    bot.buzzer_off()
                    time.sleep(0.1)
                time.sleep(0.2)
            except queue.Empty:
                pass

    def object_recognition_task():
        """Camera inference — slowest task, runs independently."""
        while not stop_event.is_set():
            bot.recognize_object()
            time.sleep(0.2)

    try:
        t1 = threading.Thread(target=line_following_task, daemon=True)
        t2 = threading.Thread(target=obstacle_detection_task, daemon=True)
        t3 = threading.Thread(target=object_recognition_task, daemon=True)
        t4 = threading.Thread(target=beeper_task, daemon=True)

        t1.start()
        t2.start()
        t3.start()
        t4.start()

        while not stop_event.is_set():
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("KeyboardInterrupt detected. Stopping execution.")
    finally:
        stop_event.set()
        t1.join(timeout=2)
        t2.join(timeout=2) 
        t3.join(timeout=2)
        t4.join(timeout=2)
        bot.stop()
        bot.buzzer_off()
        bot.clear_leds()
        bot.stop_camera()
        bot.servo.stop()
        GPIO.cleanup()
        print("All operations stopped. Exiting program.")