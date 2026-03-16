/***************************************************************************
* Sketch Name: arduino_bluetooth
*
* Original Version: 03/03/2020 (by Hakan KAYAN)
* Updated Version: 25/12/2024 (by Charith PERERA)
*
* Description:
*   - Demonstrates Bluetooth (BLE) communication between an Arduino and a
*     Raspberry Pi or other BLE-capable device.
*   - Uses a PIR (motion) sensor on digital pin 2 to detect movement and
*     sends a "Movement" message via Bluetooth when triggered.
*   - Configures a SoftwareSerial connection on digital pins 8 (RX) and 9 (TX)
*     for the Bluetooth module.
***************************************************************************/

// 1. Include the SoftwareSerial library so we can use digital pins for serial RX/TX.
#include <SoftwareSerial.h>
#include <DHT.h>

// 2. Assign pins for the SoftwareSerial (Bluetooth) module and the PIR sensor.
#define RxD 8    // Arduino RX pin for Bluetooth
#define TxD 9    // Arduino TX pin for Bluetooth
#define PIR_MOTION_SENSOR 2  // PIR sensor input pin
#define TEMP_HUMID_SENSOR 4  // TH sensor input pin
#define LIGHT_SENSOR A0
#define DHTTYPE DHT11
#define ULTRASONIC_PIN 5

// 3. Instantiate a SoftwareSerial object using pins RxD and TxD.
SoftwareSerial blueToothSerial(RxD, TxD);
DHT dht(TEMP_HUMID_SENSOR, DHTTYPE);

void setup()
{
  pinMode(ULTRASONIC_PIN, OUTPUT);
  // 4. Start the hardware Serial for debugging and messages to the Serial Monitor.
  Serial.begin(9600);
  //    Some Arduino boards require waiting for Serial to be ready (e.g., Leonardo).
  while(!Serial) { ; }
  Serial.println("Started");

  // 5. Configure the PIR sensor pin as INPUT, and the Bluetooth pins as needed.
  //    - pinMode(RxD, INPUT) is optional because SoftwareSerial handles it.
  //    - pinMode(TxD, OUTPUT) is also handled by SoftwareSerial, but we keep it for clarity.
  pinMode(PIR_MOTION_SENSOR, INPUT);
  pinMode(RxD, INPUT);
  pinMode(TxD, OUTPUT);
  dht.begin();
  

  // 6. Set up the Bluetooth module with the desired baud rate, role, and name.
  setupBlueToothConnection();

  // 7. Flush any lingering data on both the hardware and software serial buffers.
  Serial.flush();
  blueToothSerial.flush();
}

void loop()
{
  // 8. Check if there is any data coming from the Bluetooth module (blueToothSerial).
  //    If so, read it character by character and print it to the Arduino Serial Monitor.
  if (blueToothSerial.available() > 0) {
    char incoming = blueToothSerial.read();
    Serial.print(incoming);
  }

  // 9. Check if the PIR sensor detects motion (HIGH state). If yes, send "Movement" 
  //    to the connected device via Bluetooth, then delay briefly (200 ms).
  bool movement = digitalRead(PIR_MOTION_SENSOR);
  float temp = dht.readTemperature();
  float humid = dht.readHumidity();
  int light = analogRead(LIGHT_SENSOR);
  if (isnan(temp)||isnan(humid)) {
    blueToothSerial.println("{\"temperature\":null,\"humidity\"null}");
    Serial.println("{\"temperature\":null,\"humidity\"null}");
  }
  else{


    long duration;
    int distance;

    // Send trigger pulse
    pinMode(ULTRASONIC_PIN, OUTPUT);
    digitalWrite(ULTRASONIC_PIN, LOW);
    delayMicroseconds(2);

    digitalWrite(ULTRASONIC_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(ULTRASONIC_PIN, LOW);

    // Switch to input to read echo
    pinMode(ULTRASONIC_PIN, INPUT);

    duration = pulseIn(ULTRASONIC_PIN, HIGH, 30000);
    distance = duration * 0.034 / 2;
    String json = "{";
    json += "\"temperature\":";
    json += String(temp, 1);
    json += ",";
    json += "\"humidity\":";
    json += String(humid, 1);
    json += ",";
    json += "\"movement\":";
    json += movement ? "true":"false";
    json += ",";
    json += "\"light\":";
    json += String(light);
    json += ",";
    json += "\"distance\":";
    json += String(distance);
    json += "}";
    blueToothSerial.println(json);
    Serial.println(json);
  }
  delay(200);
}

/***************************************************************************
* Function Name: setupBlueToothConnection
* Description:   Initializes the Bluetooth connection with AT commands.
*                Configures the baud rate, role, name, and authentication.
***************************************************************************/
void setupBlueToothConnection()
{
  // 10. Begin a software serial session at 9600 baud for the Bluetooth module.
  blueToothSerial.begin(9600);

  // 11. Send a series of AT commands to configure the BLE module.
  blueToothSerial.print("AT");
  delay(2000);

  // Set the module’s baud rate to 9600 (AT+BAUD4 typically means 9600).
  blueToothSerial.print("AT+BAUD4");
  delay(2000);

  // Set the module’s role to “S” (often means slave/peripheral).
  blueToothSerial.print("AT+ROLES");
  delay(2000);

  // Assign a name (up to 12 characters). Here, it’s “Slave”.
  blueToothSerial.print("AT+NAMEGroup14");
  delay(2000);

  // Enable authentication (AT+AUTH1).
  blueToothSerial.print("AT+AUTH1");
  delay(2000);

  // 12. Flush any residual data from the software serial buffer.
  blueToothSerial.flush();
  Serial.println("Finished Bluetooth Setup");
}
