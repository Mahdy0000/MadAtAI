// Sphinx-1 ESP32-CAM firmware v0.1 (AI-Thinker ESP32-CAM).
// Not yet tested on real hardware by the authors: see firmware/README.md for the bring-up checklist.
//
// HTTP API (port 80):
//   GET /status                 -> JSON {ip, rssi, uptime_s, distance_cm}
//   GET /jpg                    -> one JPEG frame
//   GET /stream                 -> MJPEG stream (open in a browser to aim the camera)
//   GET /distance               -> forward distance in cm as plain text, -1 = no echo
//   GET /drive?l=-255..255&r=-255..255   -> set left/right motor speed
//   GET /stop                   -> stop motors
// Failsafe: motors stop when no /drive arrives for CMD_TIMEOUT_MS, or when driving forward toward
// something closer than STOP_CM.
#include "esp_camera.h"
#include <WebServer.h>
#include <WiFi.h>
#include "config.h"

// ---- AI-Thinker camera pins (fixed by the board)
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

WebServer server(80);
unsigned long lastDriveMs = 0;
int curL = 0, curR = 0;

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000);  // 25 ms timeout = about 4 m
  if (us == 0) return -1;
  return us * 0.0343f / 2.0f;
}

// One motor: PWM on the pin for the direction we want, the other pin low.
static void setMotor(int pinA, int pinB, int speed) {
  speed = constrain(speed, -MAX_PWM, MAX_PWM);
  if (speed > 0) { analogWrite(pinA, speed); analogWrite(pinB, 0); }
  else if (speed < 0) { analogWrite(pinA, 0); analogWrite(pinB, -speed); }
  else { analogWrite(pinA, 0); analogWrite(pinB, 0); }
}

void drive(int l, int r) {
  curL = l; curR = r;
  if (LEFT_INVERT) l = -l;
  if (RIGHT_INVERT) r = -r;
  setMotor(PIN_IN1, PIN_IN2, l);
  setMotor(PIN_IN3, PIN_IN4, r);
}

void handleDrive() {
  int l = server.arg("l").toInt();
  int r = server.arg("r").toInt();
  if (l > 0 && r > 0) {  // driving forward: check the sensor first
    float d = readDistanceCm();
    if (d > 0 && d < STOP_CM) {
      drive(0, 0);
      server.send(200, "text/plain", "blocked");
      return;
    }
  }
  drive(l, r);
  lastDriveMs = millis();
  server.send(200, "text/plain", "ok");
}

void handleJpg() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(500, "text/plain", "camera error"); return; }
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handleStream() {
  WiFiClient client = server.client();
  client.print("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) break;
    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (unsigned)fb->len);
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    if (millis() - lastDriveMs > CMD_TIMEOUT_MS && (curL || curR)) drive(0, 0);  // failsafe while streaming
  }
}

void handleStatus() {
  String s = "{\"ip\":\"" + WiFi.localIP().toString() + "\",\"rssi\":" + String(WiFi.RSSI()) +
             ",\"uptime_s\":" + String(millis() / 1000) + ",\"distance_cm\":" + String(readDistanceCm()) + "}";
  server.send(200, "application/json", s);
}

bool initCamera() {
  camera_config_t cfg = {};
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM; cfg.pin_d1 = Y3_GPIO_NUM; cfg.pin_d2 = Y4_GPIO_NUM; cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM; cfg.pin_d5 = Y7_GPIO_NUM; cfg.pin_d6 = Y8_GPIO_NUM; cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM; cfg.pin_pclk = PCLK_GPIO_NUM;
  cfg.pin_vsync = VSYNC_GPIO_NUM; cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM; cfg.pin_sccb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn = PWDN_GPIO_NUM; cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.grab_mode = CAMERA_GRAB_LATEST;
  if (psramFound()) {
    cfg.frame_size = FRAMESIZE_VGA;  // 640x480
    cfg.jpeg_quality = 12;
    cfg.fb_count = 2;
    cfg.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    cfg.frame_size = FRAMESIZE_QVGA;  // 320x240
    cfg.jpeg_quality = 15;
    cfg.fb_count = 1;
    cfg.fb_location = CAMERA_FB_IN_DRAM;
  }
  return esp_camera_init(&cfg) == ESP_OK;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_IN1, OUTPUT); pinMode(PIN_IN2, OUTPUT); pinMode(PIN_IN3, OUTPUT); pinMode(PIN_IN4, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT);
  drive(0, 0);

  Serial.println(initCamera() ? "camera ok" : "CAMERA INIT FAILED (check the ribbon cable and power)");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println();
  Serial.print("READY. Robot address: http://");
  Serial.println(WiFi.localIP());  // <- write this down, the laptop needs it

  server.on("/status", handleStatus);
  server.on("/jpg", handleJpg);
  server.on("/stream", handleStream);
  server.on("/distance", []() { server.send(200, "text/plain", String(readDistanceCm())); });
  server.on("/drive", handleDrive);
  server.on("/stop", []() { drive(0, 0); server.send(200, "text/plain", "stopped"); });
  server.begin();
}

unsigned long lastWifiCheckMs = 0;

void loop() {
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiCheckMs > 5000) {  // reconnect after a Wi-Fi drop
    lastWifiCheckMs = millis();
    WiFi.reconnect();
  }
  if ((curL || curR) && millis() - lastDriveMs > CMD_TIMEOUT_MS) drive(0, 0);  // failsafe
}
