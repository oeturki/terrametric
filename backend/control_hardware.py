import time
import requests

API_URL = "http://127.0.0.1:8000/api/control?group=1"

controls_cache = None
last_fetch_time = 0
FETCH_INTERVAL = 10  # seconds


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

def read_sensors():
    return {
        "temperature": 32,
        "light": 50,
        "height": 7
    }


def apply_controls(sensors, controls):
    temp = sensors.get("temperature")
    light = sensors.get("light")
    height = sensors.get("height")

    if temp is None or light is None or height is None:
        print("⚠ Missing sensor data")
        return

def apply_controls(sensors, controls):
    temp = sensors["temperature"]
    temp_min = controls["temperature"]["min"]
    temp_max = controls["temperature"]["max"]
    temp_warn = controls["temperature"]["warn"]
    temp_high_t = temp_max + temp_warn
    temp_low_t  = temp_min - temp_warn
    light = sensors["light"]
    light_min = controls["light"]["min"]
    light_max = controls["light"]["max"]
    light_warn = controls["light"]["warn"]
    light_high_t = light_max + light_warn
    light_low_t = light_min - light_warn
    height = sensors["height"]
    height_min = controls["height"]["min"]
    height_max = controls["height"]["max"]
    height_warn = controls["height"]["warn"]
    height_high_t = height_max + height_warn
    height_low_t = height_min - height_warn

    if temp > temp_max:
        print("Fan ON")
    else:
        print("Fan OFF")
    
    if temp > temp_high_t:
        print("Please attend to the temperature of your plants in group --, as it is too hot/high.")
    elif temp < temp_low_t:
        print("Please attend to the temperature of your plants in group --, as it is too cold/cool/low.")


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