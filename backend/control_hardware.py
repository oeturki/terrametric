import time
import requests

#camera imports
from picamera import PiCamera
from time import sleep

# Telemetry service imports
from database import SessionLocal
from services.telemetry_service import get_latest_reading_for_plant_ids
from services.recording_session_service import get_active_sessions

CONTROL_API_BASE = "http://127.0.0.1:8000/api/control"

controls_cache = {} 
last_fetch_time = {} 
FETCH_INTERVAL = 10  # seconds

last_run_time = {}
last_photo_time = {} #stores last time the camera took a photo to ensure photo is taken at the requested intervals
camera = None  # initalization - only create when needed


def is_due(plant_id, variable, controls, now=None):
    now = now or time.time()
    plant_times = last_run_time.setdefault(plant_id, {})
    last = plant_times.get(variable, 0)
    interval = controls.get(variable, {}).get("interval", 60)
    if now - last >= interval:
        plant_times[variable] = now
        return True
    return False

def get_camera():
    """initialize camera on first use"""
    global camera
    if camera is None:
        try:
            camera = PiCamera()
        except Exception as e:
            print(f"Error: Failed to initialize camera - {e}")
    return camera

def get_controls(plant_id: int):
    global controls_cache, last_fetch_time

    now = time.time()
    if plant_id not in controls_cache:
        controls_cache[plant_id] = None
        last_fetch_time[plant_id] = 0

    # only fetch every 10 seconds per plant
    if controls_cache[plant_id] is None or now - last_fetch_time[plant_id] > FETCH_INTERVAL:
        try:
            url = f"{CONTROL_API_BASE}?plant_id={plant_id}"
            res = requests.get(url, timeout=2)
            if res.ok:
                controls_cache[plant_id] = res.json()
                last_fetch_time[plant_id] = now
        except Exception as e:
            print("Error: Failed to fetch controls for plant_id=", plant_id, e)

    return controls_cache[plant_id]

#takes the picture and saves it to the desktop -- need to add camera showing up to gallery page
def take_photo(reason, plant_id):
    try:
        cam = get_camera()
        if cam is None:
            return False
            
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"plant_{plant_id}_{reason}_{timestamp}.jpg"
        filepath = f"/home/pi/Desktop/{filename}"
        
        cam.start_preview()
        sleep(2)  #light adjustment timing 
        cam.capture(filepath)
        cam.stop_preview()
        return True
    except Exception as e:  #error trapping - display message if camera capture fails
        print(f"Error: Camera failed for plant_id={plant_id}: {e}")
        return False

def read_sensors(plant_id: int):
    """Read latest sensor data from telemetry database"""
    try:
        db = SessionLocal()
        latest = get_latest_reading_for_plant_ids(db, [plant_id])
        db.close()
        
        if latest:
            return {
                "temperature": latest.get("temperature"),
                "light": latest.get("light"),
                "height": latest.get("height"),
                "humidity": latest.get("humidity"),
                "motion": latest.get("motion")
            }
    except Exception as e:
        print(f"Error: Failed to read sensors for plant_id={plant_id}: {e}")

    # Return dict with None values if reading failed
    return {
        "temperature": None,
        "light": None,
        "height": None,
        "humidity": None,
        "motion": None
    }

def apply_temperature_control(sensors, controls, plant_id):
    temp = sensors.get("temperature")
    if temp is None:
        return
    #temperature threshold calculations
    temp_min = controls["temperature"]["min"]
    temp_max = controls["temperature"]["max"]
    temp_high_t = controls["temperature"]["warn_high"]
    temp_low_t  = controls["temperature"]["warn_low"]

    if temp > temp_max - 1:
        # Fan ON - connect to fan/motor
        pass
    else:
        # Fan OFF - connect to fan/motor  
        pass

def apply_humidity_control(sensors, controls, plant_id):
    humidity = sensors.get("humidity")
    if humidity is None:
        return
    # humidity threshold calc 
    humidity_min = controls["humidity"]["min"]
    humidity_max = controls["humidity"]["max"]
    humidity_high_t = controls["humidity"]["warn_high"]
    humidity_low_t = controls["humidity"]["warn_low"]

def apply_light_control(sensors, controls, plant_id):
    light = sensors.get("light")
    if light is None:
        return
    #light threshold calculations
    light_min = controls["light"]["min"]
    light_max = controls["light"]["max"]
    light_high_t = controls["light"]["warn_high"]
    light_low_t = controls["light"]["warn_low"]

def apply_motion_control(sensors, controls, plant_id):
    motion = sensors.get("motion")
    if motion is None:
        return
    
def apply_height_control(sensors, controls, plant_id):
    height = sensors.get("height")
    if height is None:
        return
    #height threshold calculations
    height_min = controls["height"]["min"]
    height_max = controls["height"]["max"]
    height_high_t = controls["height"]["warn_high"]
    height_low_t = controls["height"]["warn_low"]
    
def apply_camera_control(sensors, controls, plant_id):
    temp = sensors.get("temperature")
    humidity = sensors.get("humidity")
    light = sensors.get("light")
    motion = sensors.get("motion")
    height = sensors.get("height")

    temp_high_t = controls["temperature"]["warn_high"]
    temp_low_t  = controls["temperature"]["warn_low"]
    humidity_high_t = controls["humidity"]["warn_high"]
    humidity_low_t = controls["humidity"]["warn_low"]
    light_high_t = controls["light"]["warn_high"]
    light_low_t = controls["light"]["warn_low"]
    height_high_t = controls["height"]["warn_high"]
    height_low_t = controls["height"]["warn_low"]

    #camera variables
    global last_photo_time
    last = last_photo_time.get(plant_id, 0)
    now = time.time()

    threshold_warning = (
    (temp is not None and (temp > temp_high_t or temp < temp_low_t)) or
    (light is not None and (light > light_high_t or light < light_low_t)) or
    (height is not None and (height > height_high_t or height < height_low_t)) or
    (humidity is not None and (humidity > humidity_high_t or humidity < humidity_low_t))
    )

    photo_reason = None
    interval = controls.get("camera", {}).get("interval", 600)

    if motion: #takes pic for motion detected
        photo_reason = "motion_detected"
    elif threshold_warning: #takes pic if threshold warning happens
        photo_reason = "sensor_warning"
    elif now - last > interval: #takes pic based on user preference or 600s if nothing is chosen
        photo_reason = "scheduled_interval"

    #logic to actually take the pic based on the above
    if photo_reason:
        if photo_reason in ["motion_detected", "scheduled_interval"] or (now - last > 30):
            if take_photo(photo_reason, plant_id):
                last_photo_time[plant_id] = now

# # upload to the webpage gallery -- to implent if time permits, photos are currently being saved to the researcher's device. 
# def upload_image(filepath, reason, plant_id):
#     upload_url = "http://127.0.0.1:8000/api/gallery"  # gallery page
#     try:
#         with open(filepath, 'rb') as f:
#             files = {'image': f}
#             data = {'reason': reason, 'plant_id': plant_id}
#             response = requests.post(upload_url, files=files, data=data, timeout=5)
#             if response.ok:
#                 pass
#             else:
#                 print(f"Upload failed: {response.status_code}")
#     except Exception as e:
#         print(f"Error: Upload error: {e}")

def get_active_plant_ids():
    try:
        db = SessionLocal()
        sessions = get_active_sessions(db)
        plant_ids = [s.plant_id for s in sessions if s.plant_id is not None]
        db.close()
        return plant_ids
    except Exception as e:
        print(f"Error: Failed to read active sessions - {e}")
        return []


def main_loop():
    try:
        while True:
            plant_ids = get_active_plant_ids()
            now = time.time()

            for plant_id in plant_ids:
                controls = get_controls(plant_id)
                if controls is None:
                    continue

                sensors = read_sensors(plant_id)

                if is_due(plant_id, "temperature", controls, now):
                    apply_temperature_control(sensors, controls, plant_id)

                if is_due(plant_id, "humidity", controls, now):
                    apply_humidity_control(sensors, controls, plant_id)

                if is_due(plant_id, "light", controls, now):
                    apply_light_control(sensors, controls, plant_id)

                if is_due(plant_id, "motion", controls, now):
                    apply_motion_control(sensors, controls, plant_id)

                if is_due(plant_id, "height", controls, now):
                    apply_height_control(sensors, controls, plant_id)
                
                apply_camera_control(sensors, controls, plant_id)

            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cam = get_camera()
        if cam is not None:
            cam.close()


if __name__ == "__main__":
    main_loop()


# control motor based on desired and tolerance + connect to controlling motor/fan
# validation for user input