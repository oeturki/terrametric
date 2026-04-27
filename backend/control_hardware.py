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

last_photo_time = 0
camera = None  # Lazy initialization - only create when needed

def _get_camera():
    """Lazy initialize camera on first use"""
    global camera
    if camera is None:
        try:
            camera = PiCamera()
        except Exception as e:
            print(f"⚠ Failed to initialize camera: {e}")
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
            print("Failed to fetch controls for plant_id=", plant_id, e)

    return controls_cache[plant_id]

# takes the picture and saves it to the desktop -- need to add camera showing up to gallery page
def take_photo(reason, plant_id):
    try:
        cam = _get_camera()
        if cam is None:
            return False
            
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"plant_{plant_id}_{reason}_{timestamp}.jpg"
        filepath = f"/home/pi/Desktop/{filename}"
        
        cam.start_preview()
        sleep(2)  # light adjustment timing 
        cam.capture(filepath)
        cam.stop_preview()
        return True
    except Exception as e:  # error trapping - display message if camera capture fails
        print(f"⚠ Camera failed for plant_id={plant_id}: {e}")
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
        print(f"⚠ Failed to read sensors for plant_id={plant_id}: {e}")

    # Return dict with None values if reading failed
    return {
        "temperature": None,
        "light": None,
        "height": None,
        "humidity": None,
        "motion": None
    }


def apply_controls(sensors, controls, plant_id):

    #camera variables
    global last_photo_time
    now = time.time()

    temp = sensors.get("temperature")
    light = sensors.get("light")
    height = sensors.get("height")
    humidity = sensors.get("humidity")
    motion = sensors.get("motion")
    motion = sensors.get("motion")
    if temp is None or light is None or height is None or humidity is None or motion is None:
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

    # humidity threshold calc 
    humidity_min = controls["humidity"]["min"]
    humidity_max = controls["humidity"]["max"]
    humidity_warn = controls["humidity"]["warn"]
    humidity_high_t = humidity_max + humidity_warn
    humidity_low_t = humidity_min - humidity_warn

    photo_needed = False
    photo_reason = ""

    # takes pic for motion detected
    if motion:
        photo_needed = True
        photo_reason = "motion_detected"

    # takes pic based on user preference or 600s if nothing is chosen
    interval = controls.get("camera", {}).get("interval", 600)
    if now - last_photo_time > interval:
        photo_needed = True
        photo_reason = "scheduled_interval"

    # takes pic if warning/alert happens
    if (temp > temp_high_t or temp < temp_low_t or 
        humidity > humidity_high_t or humidity < humidity_low_t):
        photo_needed = True
        photo_reason = "sensor_warning"

    # logic to actually take the pic based on the above
    if photo_needed:
        if photo_reason == "motion_detected" or (now - last_photo_time > 30):
            if take_photo(photo_reason, plant_id):
                last_photo_time = now

    if temp > temp_max - 1:
        # Fan ON - connect to fan/motor
        pass
    else:
        # Fan OFF - connect to fan/motor  
        pass

# upload to the webpage gallery -- to do
def upload_image(filepath, reason, plant_id):
    upload_url = "http://127.0.0.1:8000/api/gallery"  # gallery page
    try:
        with open(filepath, 'rb') as f:
            files = {'image': f}
            data = {'reason': reason, 'plant_id': plant_id}
            response = requests.post(upload_url, files=files, data=data, timeout=5)
            if response.ok:
                pass
            else:
                print(f"Upload failed: {response.status_code}")
    except Exception as e:
        print(f"⚠ Upload error: {e}")

def get_active_plant_ids():
    try:
        db = SessionLocal()
        sessions = get_active_sessions(db)
        plant_ids = [s.plant_id for s in sessions if s.plant_id is not None]
        db.close()
        return plant_ids
    except Exception as e:
        print(f"⚠ Failed to read active sessions: {e}")
        return []


def main_loop():
    try:
        while True:
            plant_ids = get_active_plant_ids()
            if not plant_ids:
                time.sleep(2)
                continue

            for plant_id in plant_ids:
                sensors = read_sensors(plant_id)
                controls = get_controls(plant_id)
                if controls is None:
                    continue
                apply_controls(sensors, controls, plant_id)

            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cam = _get_camera()
        if cam is not None:
            cam.close()


if __name__ == "__main__":
    main_loop()


# read every interval,  
# read interval time
# validation
# control motor based on desired and tolerance
# connect to controlling motor/fan,
# --
# send alerts based on if outside tolerance? or do you want alerts for when fan and stuff is on as well
    #if temp > temp_high_t:
    #    send_alert("temperature", f"Critical high temperature! Reading: {temp:.1f}°C", "danger", plant_id=plant_id)
    #elif temp < temp_low_t:
    #    #Please attend to the temperature of plant {plant_id}: it is too cold/cool/low."
    #    send_alert("temperature", f"Critical low temperature! Reading: {temp:.1f}°C", "danger", plant_id=plant_id)
    
    #if light > light_high_t:
    #    #Please attend to the light intensity of plant {plant_id}: it is too high.
    #    send_alert("light", f"Critical high light! Reading: {light:.0f} lux", "danger", plant_id=plant_id)
    #elif light < light_low_t:
    #    send_alert("light", f"Critical low light! Reading: {light:.0f} lux", "danger", plant_id=plant_id)

    #if height > height_high_t:
    #    #print(f"⚠ Please attend to plant {plant_id}: it has grown above your desired height threshold.")
    #    send_alert("height", f"Critical high height! Reading: {height:.1f} cm", "danger", plant_id=plant_id)
    #elif height < height_low_t:
    #    send_alert("height", f"Critical low height! Reading: {height:.1f} cm", "danger", plant_id=plant_id)

    #if humidity > humidity_high_t:
    #    #print(f"⚠ Please attend to the humidity of plant {plant_id}: it is too high.")
    #    send_alert("humidity", f"Critical high humidity! Reading: {humidity:.1f}%", "danger", plant_id=plant_id)
    #elif humidity < humidity_low_t:
    #    send_alert("humidity", f"Critical low humidity! Reading: {humidity:.1f}%", "danger", plant_id=plant_id)