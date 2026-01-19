import time                    # Χρήση καθυστερήσεων και χρονισμού
import board                   # Πρόσβαση στις ακίδες (pins) του μικροελεγκτή
import digitalio               # Χρήση ψηφιακών εισόδων/εξόδων
import pwmio                   # Χρήση PWM εξόδων για έλεγχο κινητήρων

# === Ρύθμιση κινητήρων ===
# Ορισμός των ακίδων PWM για κάθε κατεύθυνση στους κινητήρες
left_motor_forward = pwmio.PWMOut(board.GP11, frequency=20000, duty_cycle=0)   # Μπροστινή κατεύθυνση αριστερού κινητήρα
left_motor_backward = pwmio.PWMOut(board.GP10, frequency=20000, duty_cycle=0)  # Πίσω κατεύθυνση αριστερού κινητήρα
right_motor_forward = pwmio.PWMOut(board.GP8, frequency=20000, duty_cycle=0)   # Μπροστινή κατεύθυνση δεξιού κινητήρα
right_motor_backward = pwmio.PWMOut(board.GP9, frequency=20000, duty_cycle=0)  # Πίσω κατεύθυνση δεξιού κινητήρα

# === Αισθητήρες υπερύθρων (IR) ===
# Ορισμός των ψηφιακών εισόδων για τους IR αισθητήρες
gp2 = digitalio.DigitalInOut(board.GP2)
gp3 = digitalio.DigitalInOut(board.GP3)
gp4 = digitalio.DigitalInOut(board.GP4)
gp5 = digitalio.DigitalInOut(board.GP5)
gp16 = digitalio.DigitalInOut(board.GP16)
gp17 = digitalio.DigitalInOut(board.GP17)

# Ρύθμιση των IR αισθητήρων ως είσοδοι με εσωτερική αντίσταση pull-up
for pin in [gp2, gp3, gp4, gp5, gp16, gp17]:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# === Κουμπιά ===
# Ορισμός κουμπιών για λειτουργίες: παρακολούθηση γραμμής & αγώνας γύρων
line_follow_button = digitalio.DigitalInOut(board.GP20)
line_follow_button.direction = digitalio.Direction.INPUT
line_follow_button.pull = digitalio.Pull.UP

lap_mode_button = digitalio.DigitalInOut(board.GP21)
lap_mode_button.direction = digitalio.Direction.INPUT
lap_mode_button.pull = digitalio.Pull.UP

# === Σταθερές ταχύτητας ===
BASE_SPEED = 40100        # Κανονική ταχύτητα κίνησης
TURN_SPEED = 46000        # Ταχύτητα στροφής
SEARCH_SPEED = 38000      # Ταχύτητα όταν ψάχνει τη γραμμή
LEFT_ADJUST = 1.16        # Διόρθωση ταχύτητας αριστερού κινητήρα
RIGHT_ADJUST = 1.20       # Διόρθωση ταχύτητας δεξιού κινητήρα
MIN_DUTY = 5000           # Ελάχιστη τιμή για να κινηθεί ο κινητήρας

# === Συνάρτηση για ρύθμιση ταχύτητας στους κινητήρες ===
def set_motors(left_speed, right_speed):
    # Διόρθωση με συντελεστές και ελάχιστη τιμή duty cycle
    adjusted_left = max(int(abs(left_speed) * LEFT_ADJUST), MIN_DUTY if left_speed != 0 else 0)
    adjusted_right = max(int(abs(right_speed) * RIGHT_ADJUST), MIN_DUTY if right_speed != 0 else 0)

    # Ρύθμιση PWM για την αντίστοιχη κατεύθυνση σε κάθε κινητήρα
    left_motor_forward.duty_cycle = adjusted_left if left_speed > 0 else 0
    left_motor_backward.duty_cycle = adjusted_left if left_speed < 0 else 0
    right_motor_forward.duty_cycle = adjusted_right if right_speed > 0 else 0
    right_motor_backward.duty_cycle = adjusted_right if right_speed < 0 else 0

# === Συνάρτηση για σταμάτημα κινητήρων ===
def stop_motors():
    left_motor_forward.duty_cycle = 0
    left_motor_backward.duty_cycle = 0
    right_motor_forward.duty_cycle = 0
    right_motor_backward.duty_cycle = 0

# === Ανάγνωση αισθητήρων με φίλτρο (σταθεροποίηση αναγνώσεων) ===
def read_sensors_filtered(samples=4, delay=0.0002):
    left_count = 0
    middle_count = 0
    right_count = 0

    # Πολλαπλές αναγνώσεις για αποφυγή θορύβου
    for _ in range(samples):
        if gp2.value or gp3.value:
            left_count += 1
        if gp4.value or gp5.value:
            middle_count += 1
        if gp16.value or gp17.value:
            right_count += 1
        time.sleep(delay)

    # Αν η πλειοψηφία λέει "μαύρο", τότε ενεργοποιείται η αντίστοιχη θέση
    left = left_count >= (samples // 2)
    middle = middle_count >= (samples // 2)
    right = right_count >= (samples // 2)

    return (left, middle, right)

# === Μεταβλητές κατάστασης ===
robot_running = False
robot_mode = "none"
last_direction = "center"
stop_requested = False
seen_black_line = False
consecutive_lost_readings = 0

# === Για λειτουργία γύρων ===
laps_completed = 0
target_laps = 3
start_line_detected = False
crossing_start_line = False
start_line_cooldown = 0
starting_from_black = False
line_width_counter = 0

# === Συνάρτηση παρακολούθησης γραμμής με υποστήριξη απότομων στροφών ===
def follow_line_with_sharp_turns(left, middle, right):
    global last_direction

    # Αν δεν βλέπει καθόλου γραμμή, προσπαθεί να την ξαναβρεί
    if not left and not middle and not right:
        print("Line lost – searching...")
        if last_direction == "left":
            set_motors(0, SEARCH_SPEED)
        elif last_direction == "right":
            set_motors(SEARCH_SPEED, 0)
        else:
            set_motors(SEARCH_SPEED // 2, -SEARCH_SPEED // 2)
        return

    # Ανάλογα με τους αισθητήρες, ρυθμίζονται οι στροφές
    if left and not middle and not right:
        print("Sharp LEFT turn")
        set_motors(0, TURN_SPEED)
        last_direction = "left"
    elif right and not middle and not left:
        print("Sharp RIGHT turn")
        set_motors(TURN_SPEED, 0)
        last_direction = "right"
    elif left and middle and not right:
        print("Moderate LEFT turn")
        set_motors(BASE_SPEED // 3, BASE_SPEED)
        last_direction = "left"
    elif right and middle and not left:
        print("Moderate RIGHT turn")
        set_motors(BASE_SPEED, BASE_SPEED // 3)
        last_direction = "right"
    elif not left and middle and not right:
        print("Going STRAIGHT")
        set_motors(BASE_SPEED, BASE_SPEED)
        last_direction = "center"
    elif left and right and not middle:
        print("Wide line or crossing - going straight")
        set_motors(BASE_SPEED, BASE_SPEED)
        last_direction = "center"
    else:
        set_motors(BASE_SPEED, BASE_SPEED)
        last_direction = "center"

# === Εκκίνηση ===
print("=== LINE FOLLOWER ROBOT ===")
print("Press GP20 for LINE FOLLOW")
print("Press GP21 for 3-LAP RACE")

# === Κύριος βρόχος ===
while True:
    # Έναρξη λειτουργίας παρακολούθησης γραμμής
    if not line_follow_button.value and not robot_running:
        print("Line follow mode started")
        robot_running = True
        robot_mode = "line_follow"
        consecutive_lost_readings = 0
        seen_black_line = False
        stop_requested = False

        # Μικρή εκκίνηση για ενεργοποίηση των κινητήρων
        set_motors(BASE_SPEED, BASE_SPEED)
        time.sleep(0.1)
        stop_motors()
        time.sleep(0.2)
        time.sleep(0.5)

    # Έναρξη λειτουργίας αγώνα γύρων
    if not lap_mode_button.value and not robot_running:
        print("=== 3-LAP RACE MODE STARTED ===")
        robot_running = True
        robot_mode = "lap_race"
        laps_completed = 0
        stop_requested = False
        seen_black_line = False
        start_line_detected = False
        crossing_start_line = False
        start_line_cooldown = 0
        starting_from_black = False
        line_width_counter = 0

        # Αν ξεκινά πάνω σε μαύρη γραμμή, αρχίζει να προχωρά
        left, middle, right = read_sensors_filtered()
        if left and middle and right:
            print("Starting on wide line - moving forward to find normal line")
            starting_from_black = True
            set_motors(BASE_SPEED // 2, BASE_SPEED // 2)
        else:
            print("Starting position ready")
        time.sleep(0.5)

    # Αν το ρομπότ είναι ενεργό, εκτελεί την ανάλογη λειτουργία
    if robot_running and not stop_requested:
        left, middle, right = read_sensors_filtered()
        print(f"L:{left} M:{middle} R:{right}")

        # Αν ανιχνεύσει μαύρο, κρατάει ότι "είδε γραμμή"
        if left or middle or right:
            seen_black_line = True

        # Αν εντοπίσει μαύρη γραμμή σε όλους τους αισθητήρες
        if left and middle and right:
            if robot_mode == "line_follow":
                print("Black stop line detected – stopping.")
                stop_motors()
                robot_running = False
                stop_requested = True
                continue
            elif robot_mode == "lap_race":
                if starting_from_black:
                    set_motors(BASE_SPEED // 2, BASE_SPEED // 2)
                    line_width_counter += 1
                    if line_width_counter > 50:
                        starting_from_black = False
                        line_width_counter = 0
                        print("Off starting line - beginning lap tracking")
                    time.sleep(0.005)
                    continue
                elif start_line_cooldown <= 0:
                    if not crossing_start_line:
                        crossing_start_line = True
                        if start_line_detected:
                            laps_completed += 1
                            print(f"=== LAP {laps_completed}/{target_laps} COMPLETED ===")
                            if laps_completed >= target_laps:
                                print("🏁 ALL LAPS COMPLETED! STOPPING ROBOT 🏁")
                                stop_motors()
                                robot_running = False
                                stop_requested = True
                                continue
                            start_line_cooldown = 100
                        else:
                            print("📍 Start line detected - lap counting starts")
                            start_line_detected = True
                            start_line_cooldown = 100
                    set_motors(BASE_SPEED // 2, BASE_SPEED // 2)
                else:
                    set_motors(BASE_SPEED // 2, BASE_SPEED // 2)
        else:
            crossing_start_line = False
            if start_line_cooldown > 0:
                start_line_cooldown -= 1

        # Κίνηση με βάση την κατεύθυνση γραμμής
        follow_line_with_sharp_turns(left, middle, right)
        time.sleep(0.005)
    else:
        # Αν δεν τρέχει, σταματά τους κινητήρες
        stop_motors()
        time.sleep(0.1)
