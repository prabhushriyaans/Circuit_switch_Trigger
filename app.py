import os
import serial
import time
from threading import Thread, Timer
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import requests
import datetime
from dotenv import load_dotenv
import secrets
print(secrets.token_hex(16))

# --- Load .env file ---
load_dotenv()

# --- Flask and SocketIO setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'change_me')
socketio = SocketIO(app)

# --- Serial Port Configuration ---
ser = None
try:
    # Change 'COM3' to your Arduino's serial port
    ser = serial.Serial('COM3', 9600, timeout=1)
    time.sleep(2)  # Give the serial port time to initialize
    print("Serial port connected.")
except serial.SerialException as e:
    print(f"Error: {e}")
    print("Please check the port number and ensure the Arduino is connected.")

# --- AI API Configuration ---
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Using a specific Deepseek model via OpenRouter
AI_MODEL = "meta-llama/llama-3.3-8b-instruct:free"
API_KEY = os.getenv("META_API_KEY")

# --- Global state variables ---
last_alert_message = ""
alert_active = False
alert_start_time = None
alert_timer = None

# --- AI API Function ---
def get_ai_response(prompt_message: str) -> str:
    if not API_KEY:
        print("DEEPSEEK_API_KEY not set in environment.")
        return "AI service unavailable (missing API key)."
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": AI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Rescue force Operations AI. Your purpose is to analyze alerts and provide "
                        "concise, factual reports and recommended actions to security personnel. "
                        "Your responses should be short, to the point, and never for the victim."
                        "you will try to locate the victim using the information provided in the alert."
                        "The victim is only a woman who is being entangled in an emergency situation , which may be roberry or assault."
                    )
                },
                {"role": "user", "content": prompt_message}
            ]
        }
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=20)
        response.raise_for_status()
        ai_message = response.json()['choices'][0]['message']['content']
        return ai_message
    except Exception as e:
        print("AI API error details:", str(e))
        if hasattr(e, "response") and e.response is not None:
            print("API Response:", e.response.text)
        return "AI service temporary error."

# --- Outbound serial helpers ---
def send_serial(cmd: str):
    try:
        if ser:
            ser.write((cmd + "\n").encode('utf-8'))
            print(f"[SERIAL] -> {cmd}")
    except Exception as e:
        print(f"Serial write failed for '{cmd}': {e}")

# --- AI message flow ---
def handle_emergency_timeout():
    global alert_active
    if not alert_active:
        return
    
    # Generate the follow-up emergency message for security agencies
    prompt = "Urgent: User unresponsive for >30 seconds. Advise immediate deployment."
    ai_text = get_ai_response(prompt)
    
    # Send the follow-up AI message to the frontend
    socketio.emit('emergency_message', {
        'message': "Emergency escalation triggered. " + ai_text
    })

    # Tell Arduino to terminate the alert with 6 beeps for the victim
    send_serial('BEEP_6_TIMES')
    
    # Reset state
    set_alert_inactive()

# --- State helpers ---
def set_alert_active(message: str):
    global alert_active, alert_start_time, last_alert_message, alert_timer
    
    # Check if an alert is already active to prevent re-triggering
    if alert_active:
        return
        
    last_alert_message = message
    alert_active = True
    alert_start_time = datetime.datetime.now()
    
    # Immediately get the first AI response on a new alert
    prompt = (
        "Initial alert received. Provide a brief one-sentence summary and 3 key action steps for security personnel."
    )
    ai_text = get_ai_response(prompt)

    # Send the first AI message to the frontend along with the alert event
    socketio.emit('alert_event', {'message': message, 'ai_advice': ai_text})

    # Start 30s timer for auto-emergency (changed from 60.0 to 30.0)
    if alert_timer and alert_timer.is_alive():
        alert_timer.cancel()
    new_timer = Timer(30.0, handle_emergency_timeout)
    new_timer.daemon = True
    new_timer.start()
    alert_timer = new_timer

def set_alert_inactive():
    global alert_active, last_alert_message, alert_timer
    alert_active = False
    last_alert_message = ""
    if alert_timer and alert_timer.is_alive():
        alert_timer.cancel()

# --- Serial Listener Thread ---
def serial_listener():
    global alert_active
    print("Serial listener thread started.")
    while ser and True:
        try:
            if ser.in_waiting > 0:
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                if not data:
                    continue
                print(f"[SERIAL] <- {data}")

                if "Help! Help!" in data:  # incoming alert trigger
                    set_alert_active(message=data)
                
                elif "alert message off." in data:  # user cancels alert
                    if alert_active:
                        set_alert_inactive()
                        socketio.emit('alert_terminated', {'message': "Alert terminated by user."})

        except serial.SerialException as e:
            print(f"Serial port error: {e}")
            break
        except Exception as e:
            print(f"Error in serial listener: {e}")
            break
    print("Serial listener thread stopped.")

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html', initial_status="Awaiting alert from Arduino…")

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    print('Client connected:', request.sid)
    emit('status_update', {'message': 'Connected to server.'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected:', request.sid)

# --- Main entry point ---
if __name__ == '__main__':
    if ser:
        thread = Thread(target=serial_listener, daemon=True)
        thread.start()
    socketio.run(app, debug=True, port=5000, use_reloader=False)