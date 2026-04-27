import time
import requests

#camera imports
from picamera import PiCamera
from time import sleep


API_URL = "http://127.0.0.1:8000/api/control?group=1"
# FastAPI: per-plant profile (use a real plant_id from your DB / UI)
API_URL = "http://127.0.0.1:8000/api/control?plant_id=1"

controls_cache = None
last_fetch_time = 0
FETCH_INTERVAL = 10  # seconds

ALERT_API = "http://127.0.0.1:8000/api/alerts"
last_alert_time = {}
camera = PiCamera() #initialising camera

# warning/alert logic 
def send_alert(sensor, message, level="warning", group="1", cooldown=30):
    now = time.time()
    key = f"{sensor}:{message}"

    if key in last_alert_time and now - last_alert_time[key] < cooldown:
        return  # skip duplicate

    last_alert_time[key] = now

    try:
        requests.post(ALERT_API, json={
            "sensor": sensor,
            "message": message,
            "type": level,
            "group": group
        }, timeout=2)
    except Exception as e:
        print("⚠ Failed to send alert:", e)

def get_controls():
    global controls_cache, last_fetch_time

    now = time.time()

    # only fetch every 10 seconds
    if controls_cache is None or now - last_fetch_time > FETCH_INTERVAL:
        try:
            res = requests.get(API_URL, timeout=2)
            if res.ok:
                controls_cache = res.json()
                last_fetch_time = now
                print("Updated controls from API")
        except Exception as e:
            print("Failed to fetch controls:", e)

    return controls_cache

#takes the picture and saves it to the desktop -- need to add camera showing up in gallery page
def take_photo(reason, group_id):
    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"group_{group_id}_{reason}_{timestamp}.jpg"
        filepath = f"/home/pi/Desktop/{filename}" # figure out fle path 
        
        camera.start_preview()
        sleep(2) #light adjustment timing 
        camera.capture(filepath)
        camera.stop_preview()
        
        print(f"📸 Photo captured! Reason: {reason} | Saved to: {filepath}")
        return True
    except Exception as e: #error trapping -- dispalys message if the camera capture fails for some reason
        print(f"⚠ Camera failed: {e}")
        return False

def read_sensors(): #how to read sensor data - see how omar got sensor data to be read
    sensors = {
        "temperature": read_temperature_sensor(),
        "light": read_light_sensor(),
        "height": read_ultrasonic_sensor(),
        "humidity": read_humidity_sensor(),
        "motion": read_motion_sensor() 
    }

    # --- handle failures ---
    for name, value in sensors.items():
        if value is None:
            print(f"⚠ {name} sensor failed")

    return sensors


def apply_controls(sensors, controls):

    #camera variables
    global controls_cache, last_fetch_time
    now = time.time()

    temp = sensors.get("temperature")
    light = sensors.get("light")
    height = sensors.get("height")
    humidity = sensors.get("humidity")
    motion = sensors.get("motion") #connect to camera
    if temp is None or light is None or height is None or humidity is None or motion is None:
        print("⚠ Missing sensor data")
        return

    
    temp_min = controls["temperature"]["min"]
    temp_max = controls["temperature"]["max"]
    temp_warn = controls["temperature"]["warn"]
    temp_high_t = temp_max + temp_warn
    temp_low_t  = temp_min - temp_warn
    
    light_min = controls["light"]["min"]
    light_max = controls["light"]["max"]
    light_warn = controls["light"]["warn"]
    light_high_t = light_max + light_warn
    light_low_t = light_min - light_warn
    
    height_min = controls["height"]["min"]
    height_max = controls["height"]["max"]
    height_warn = controls["height"]["warn"]
    height_high_t = height_max + height_warn
    height_low_t = height_min - height_warn

    # humidity treshold calc 
    humidity_min = controls["humidity"]["min"]
    humidity_max = controls["humidity"]["max"]
    humidity_warn = controls["humidity"]["warn"]
    humidity_high_t = humidity_max + humidity_warn
    humidity_low_t = humidity_min - humidity_warn

    #motion -- to do

    photo_needed = False
    photo_reason = ""

    #takes pic for motion detected
    if motion:
        photo_needed = True
        photo_reason = "motion_detected"

    #takes pic based on user preference or 600s if nothing is chosen
    interval = controls.get("camera", {}).get("interval", 600)
    if now - last_photo_time > interval:
        photo_needed = True
        photo_reason = "scheduled_interval"

    #takes pic if warning/alett happens
    if (temp > temp_high_t or temp < temp_low_t or 
        humidity > humidity_high_t or humidity < humidity_low_t):
        photo_needed = True
        photo_reason = "sensor_warning"

    #logic to actually take the pic based on the above
    if photo_needed:
        if photo_reason == "motion_detected" or (now - last_photo_time > 30):
            if take_photo(photo_reason, group_id):
                last_photo_time = now

    if temp > temp_max:
        print("Fan ON") #connect to fan/motor
    else:
        print("Fan OFF") #connect to fan/motor
    
    if temp > temp_high_t:
        print("Please attend to the temperature of your plants in group --, as it is too hot/high.")
        send_alert("temperature", "Critical high temperature!", "critical")
        #print(f"Temperature {temp}°C exceeded max {temp_high_t}°C")
    elif temp < temp_low_t:
        print("Please attend to the temperature of your plants in group --, as it is too cold/cool/low.")
        send_alert("temperature", "Critical low temperature!", "critical")
    
    if light > light_high_t:
        print("Please attend to the light intensity of your plants in group --, as it is too hot/high.")
    elif light < light_low_t:
        print("Please attend to the light intensity of your plants in group --, as it is too cold/cool/low.")

    if height > height_high_t:
        print("Please attend to your plants in group --, as they have grown above your desired height threshold.")
    elif height < height_low_t:
        print("Please attend to your plants in group --, as their height has decreased to below an abnormal threshold..")

    if humidity > humidity_high_t:
        print("Please attend to the humidity of your plants in group -- as it is too high.")
        send_alert("humidity", "Critical high humidity!", "critical")
    elif humidity < humidity_low_t:
        print("Please attend to the humidity of your plants in group -- as it is too low.")
        send_alert("humidity", "Critical low humidity!", "critical")

#upload to the webpage gallery -- to do
def upload_image(filepath, reason, group_id):
    upload_url = "http://127.0.0.1:8000/api/gallery" #gallery page
    try:
        with open(filepath, 'rb') as f:
            files = {'image': f}
            data = {'reason': reason, 'group': group_id}
            response = requests.post(upload_url, files=files, data=data, timeout=5)
            if response.ok:
                print("Image uploaded to server successfully")
            else:
                print(f"Upload failed: {response.status_code}")
    except Exception as e:
        print(f"⚠ Upload error: {e}")

def main_loop():
    try: 
        while True:
            sensors = read_sensors()
            controls = get_controls()
            if controls is None:
                print("⚠ No controls available yet")
                time.sleep(2)
                continue
            apply_controls(sensors, controls)
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        camera.close() #camera shutdown

if __name__ == "__main__":
    main_loop()

# make print statements alerts, how often alerts? like just once or every five seconds until issue is fixed for urgent or critical ones?
# read every interval, 
# read sensors and connect to controlling motor/fan, 
# allow the alert to state what plant group is affected. and not just group 1
# validation