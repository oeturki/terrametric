from flask import Flask, request, jsonify
import copy

app = Flask(__name__)

# store per group
controls_db = {
    "1": {},
    "2": {}
}

default_controls = {
        "temperature": {"min": 15, "max": 30, "warn": 5, "interval": 60},
        "humidity": {"min": 20, "max": 40, "warn": 5, "interval": 60},
        "light": {"min": 5000, "max": 10000, "warn": 500, "interval": 60},
        "motion": {"min": 0, "max": 1, "warn": 1, "interval": 20},
        "height": {"min": 0, "max": 10000, "warn": 5, "interval": 1440},
        "camera": {"on_motion": False, "on_alert": False, "interval": 60}
    }
    

@app.route('/api/control', methods=['GET'])
def get_controls():
    group = request.args.get("group", "1")
    data = controls_db.get(group)

    return jsonify(data if data else default_controls)

@app.route('/api/control', methods=['POST'])
def save_controls():
    data = request.json
    group = str(data.get("group", "1"))

    existing = controls_db.get(group, {})
    updated = copy.deepcopy(default_controls)

    # merge existing
    for key in existing:
        if isinstance(existing[key], dict):
            updated[key].update(existing[key])

    # merge new data
    for key in data:
        if isinstance(data[key], dict):
            updated[key].update(data[key])

    # Validation
    temp = updated.get("temperature", {})
    if temp.get("min") is not None and temp.get("max") is not None:
        if temp["min"] >= temp["max"]:
            return jsonify({"error": "Invalid temperature range"}), 400

    humidity = updated.get("humidity", {})
    if humidity.get("warn") is not None and humidity["warn"] > 100:
        return jsonify({"error": "Humidity too high"}), 400

    controls_db[group] = updated

    return jsonify({
        "status": "saved",
        "group": group,
        "controls": updated
    })

@app.route('/api/control/reset', methods=['POST'])
def reset_controls():
    data = request.json or {}
    group = str(data.get("group", "1"))

    controls_db[group] = copy.deepcopy(default_controls)

    return jsonify({
        "status": "reset",
        "group": group,
        "controls": controls_db[group]
    })

alerts_db = []

@app.route('/api/alerts', methods=['POST'])
def create_alert():
    data = request.json or {}

    alert = {
        "type": data.get("type", "info"),
        "message": data.get("message", ""),
        "sensor": data.get("sensor", ""),
        "group": data.get("group", "1"),
        "timestamp": time.time()
    }

    alerts_db.append(alert)

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)