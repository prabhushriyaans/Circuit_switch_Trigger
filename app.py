import serial
import time
from threading import Thread, Timer
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import requests
import datetime

# --- Flask and SocketIO setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key' 
socketio = SocketIO(app)

# --- Serial Port Configuration ---
try:
    ser = serial.Serial('COM3', 9600, timeout=1) 
    time.sleep(2) 
    print("Serial port connected.")
except serial.SerialException as e:
    print(f"Error: {e}")
    print("Please check the port number and ensure the Arduino is connected.")
    ser = None

# --- AI API Configuration ---
AI_API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "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"
AI_MODEL = "deepseek/deepseek-r1:free"

# --- Global state variables ---
last_alert_message = ""
alert_active = False
alert_start_time = None
alert_timer = None

# --- AI API Function ---
def get_ai_response(prompt_message):
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for emergency services. Based on the situation and time, provide a clear and urgent response. Consider the time of day and the duration of the alert."},
                {"role": "user", "content": prompt_message}
            ]
        }
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        ai_message = response.json()['choices'][0]['message']['content']
        print(f"AI response received: {ai_message}")
        return ai_message
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI API: {e}")
        return "Failed to get AI response. Please check API connection."

def trigger_ai_response():
    global alert_active, alert_start_time, last_alert_message
    if not alert_active:
        return

    duration = datetime.datetime.now() - alert_start_time
    time_of_day = datetime.datetime.now().strftime("%I:%M %p")
    
    prompt = f"An emergency alert has been active for {duration.total_seconds():.0f} seconds. The current time is {time_of_day}. The original message was: '{last_alert_message}'. Please provide an urgent response for security forces."
    
    ai_response = get_ai_response(prompt)
    
    if ser:
        ser.write(b'BEEP_6_TIMES\n')
        print("Sent BEEP_6_TIMES command to Arduino.")
    
    socketio.emit('deployment_message', {'message': "Alert not terminated. " + ai_response})
    alert_active = False

# --- Serial Listener Thread ---
def serial_listener():
    global alert_active, alert_start_time, last_alert_message, alert_timer
    print("Serial listener thread started.")
    while ser and True:
        try:
            if ser.in_waiting > 0:
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                if "Help! Help!" in data:
                    print("Alert message received from Arduino!")
                    last_alert_message = data
                    alert_active = True
                    alert_start_time = datetime.datetime.now()
                    
                    if alert_timer and alert_timer.is_alive():
                        alert_timer.cancel()
                    
                    alert_timer = Timer(10.0, trigger_ai_response)
                    alert_timer.daemon = True
                    alert_timer.start()

                    socketio.emit('alert_event', {'message': data})
                
                elif "alert message off." in data:
                    print("Alert message terminated by user.")
                    if alert_timer and alert_timer.is_alive():
                        alert_timer.cancel()
                    alert_active = False
                    last_alert_message = ""
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
    return render_template('index.html', initial_status="Awaiting alert from Arduino...")

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
        thread = Thread(target=serial_listener)
        thread.daemon = True
        thread.start()
    socketio.run(app, debug=True, port=5000, use_reloader=False)