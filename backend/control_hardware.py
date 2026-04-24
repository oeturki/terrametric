import time
import requests

# FastAPI: per-plant profile (use a real plant_id from your DB / UI)
API_URL = "http://127.0.0.1:8765/api/control?plant_id=1"

controls_cache = None
last_fetch_time = 0
FETCH_INTERVAL = 10  # seconds

ALERT_API = "http://127.0.0.1:8765/api/alerts"
last_alert_time = {}

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


def read_sensors(): #how to read sensor data - see how omar got sensor data to be read
    sensors = {
        "temperature": read_temperature_sensor(),
        "light": read_light_sensor(),
        "height": read_ultrasonic_sensor(),
        "humidity": read_humidity_sensor(),
        "motion": read_motion_sensor()
        # figure out how to add camera?? 
    }

    # --- handle failures ---
    for name, value in sensors.items():
        if value is None:
            print(f"⚠ {name} sensor failed")

    return sensors


def apply_controls(sensors, controls):
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

    if temp > temp_max:
        print("Fan ON") #connect to fan/motor
    else:
        print("Fan OFF") #connect to fan/motor
    
    if temp > temp_high_t:
        print("Please attend to the temperature of your plants in group --, as it is too hot/high.")
        send_alert("temperature", "Critical high temperature!", "critical")
        f"Temperature {temp}°C exceeded max {temp_high_t}°C"
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


def main_loop():
    while True:
        sensors = read_sensors()
        controls = get_controls()
        if controls is None:
            print("⚠ No controls available yet")
            time.sleep(2)
            continue
        apply_controls(sensors, controls)
        time.sleep(2)

if __name__ == "__main__":
    main_loop()

# make print statements alerts, how often alerts? like just once or every five seconds until issue is fixed for urgent or critical ones?
# read every interval, 
# read sensors and connect to controlling motor/fan, 
# allow the alert to state what plant group is affected. and not just group 1
# validation