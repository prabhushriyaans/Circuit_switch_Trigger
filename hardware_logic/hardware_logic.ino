int switchPin = 2;
int buzzerPin = 8;

unsigned long lastPressTime = 0;
const unsigned long debounceDelay = 50; // ms debounce

bool alertMode = false; // starts OFF
unsigned long lastMessageTime = 0; // for 1s message delay

void setup() {
  pinMode(switchPin, INPUT_PULLUP);
  pinMode(buzzerPin, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  // --- Button Press Logic ---
  static int lastState = HIGH;
  int currentState = digitalRead(switchPin);
  unsigned long now = millis();

  // Detect a single button press (falling edge with debounce)
  if (currentState == LOW && lastState == HIGH && (now - lastPressTime > debounceDelay)) {
    // Toggle the alert mode
    alertMode = !alertMode;

    if (alertMode) {
      Serial.println("Help! Help!");
      // Turn buzzer ON and start message loop
      digitalWrite(buzzerPin, HIGH);
      lastMessageTime = now;
    } else {
      // STOP messages
      Serial.println("alert message off.");
      // Beep 2 times for cancellation confirmation
      for (int i = 0; i < 2; i++) {
        digitalWrite(buzzerPin, HIGH);
        delay(80);
        digitalWrite(buzzerPin, LOW);
        delay(80);
      }
    }
    lastPressTime = now;
  }

  // If alert mode is ON → send help message every 1s
  if (alertMode && (now - lastMessageTime >= 1000)) {
    Serial.println("Help! Help!");
    lastMessageTime = now;
  }

  // If alert is OFF → ensure buzzer is OFF
  if (!alertMode) {
    digitalWrite(buzzerPin, LOW);
  }

  lastState = currentState;

  // --- Listen for Serial commands from Python ---
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    if (command == "BEEP_6_TIMES") {
      Serial.println("BEEP_6_TIMES command received.");
      alertMode = false; // Turn off the alert mode
      digitalWrite(buzzerPin, LOW);
      for (int i = 0; i < 6; i++) {
        digitalWrite(buzzerPin, HIGH);
        delay(150);
        digitalWrite(buzzerPin, LOW);
        delay(150);
      }
    }
  }
}