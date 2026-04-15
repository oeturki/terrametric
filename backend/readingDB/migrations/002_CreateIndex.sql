-- Fast lookup via reading type (temperature, humidity, light etc.)
CREATE INDEX sensor_type_idx ON readings (key, timestamp DESC);

-- Fast lookup via device
CREATE INDEX device_idx ON readings (device_id, timestamp DESC);

-- Fast lookup via control group
CREATE INDEX control_group_idx ON readings (control_group, timestamp DESC);

-- Fast lookup via device and reading type
CREATE INDEX sensor_type_device_idx ON readings (key, device_id, timestamp DESC);

-- Fast lookup via control group and reading type
CREATE INDEX sensor_type_control_group_idx ON readings (key, control_group, timestamp DESC);