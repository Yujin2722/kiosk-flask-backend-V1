#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <EEPROM.h>

ESP8266WebServer server(80);

struct IPConfig {
  uint8_t ip[4];
  uint8_t gateway[4];
  uint8_t subnet[4];
};

const int EEPROM_SIZE = 64;
const int EEPROM_START = 0;

IPConfig ipConfig;

void writeIPConfig(IPConfig cfg) {
  for (int i=0; i<4; i++) EEPROM.write(EEPROM_START + i, cfg.ip[i]);
  for (int i=0; i<4; i++) EEPROM.write(EEPROM_START + 4 + i, cfg.gateway[i]);
  for (int i=0; i<4; i++) EEPROM.write(EEPROM_START + 8 + i, cfg.subnet[i]);
  EEPROM.commit();
}

IPConfig readIPConfig() {
  IPConfig cfg;
  for (int i=0; i<4; i++) cfg.ip[i] = EEPROM.read(EEPROM_START + i);
  for (int i=0; i<4; i++) cfg.gateway[i] = EEPROM.read(EEPROM_START + 4 + i);
  for (int i=0; i<4; i++) cfg.subnet[i] = EEPROM.read(EEPROM_START + 8 + i);
  return cfg;
}

bool isIPConfigEmpty(IPConfig cfg) {
  for(int i=0; i<4; i++) {
    if(cfg.ip[i] != 0) return false;
  }
  return true;
}

void defaultIPConfig() {
  ipConfig.ip[0] = 192; ipConfig.ip[1] = 168; ipConfig.ip[2] = 1; ipConfig.ip[3] = 184;
  ipConfig.gateway[0] = 192; ipConfig.gateway[1] = 168; ipConfig.gateway[2] = 1; ipConfig.gateway[3] = 1;
  ipConfig.subnet[0] = 255; ipConfig.subnet[1] = 255; ipConfig.subnet[2] = 255; ipConfig.subnet[3] = 0;
}

const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// LED pins
const int ledPhone = D1;
const int ledWallet = D2;
const int ledUmbrella = D3;
const int ledCalculator = D4;
const int ledRandom = D5;

void setup() {
  Serial.begin(115200);
  EEPROM.begin(EEPROM_SIZE);

  ipConfig = readIPConfig();

  if (isIPConfigEmpty(ipConfig)) {
    defaultIPConfig();
    writeIPConfig(ipConfig);
  }

  IPAddress staticIP(ipConfig.ip[0], ipConfig.ip[1], ipConfig.ip[2], ipConfig.ip[3]);
  IPAddress gateway(ipConfig.gateway[0], ipConfig.gateway[1], ipConfig.gateway[2], ipConfig.gateway[3]);
  IPAddress subnet(ipConfig.subnet[0], ipConfig.subnet[1], ipConfig.subnet[2], ipConfig.subnet[3]);

  if (!WiFi.config(staticIP, gateway, subnet)) {
    Serial.println("Failed to configure static IP");
  }

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected! IP: ");
  Serial.println(WiFi.localIP());

  // Setup LED pins as output
  pinMode(ledPhone, OUTPUT);
  pinMode(ledWallet, OUTPUT);
  pinMode(ledUmbrella, OUTPUT);
  pinMode(ledCalculator, OUTPUT);
  pinMode(ledRandom, OUTPUT);

  // Initially turn LEDs off (assuming active HIGH)
  digitalWrite(ledPhone, LOW);
  digitalWrite(ledWallet, LOW);
  digitalWrite(ledUmbrella, LOW);
  digitalWrite(ledCalculator, LOW);
  digitalWrite(ledRandom, LOW);

  // Define routes for LEDs
  server.on("/led/on/phone", []() {
    turnLedOn(ledPhone);
    server.send(200, "text/plain", "Phone LED ON");
  });
  server.on("/led/off/phone", []() {
    turnLedOff(ledPhone);
    server.send(200, "text/plain", "Phone LED OFF");
  });

  server.on("/led/on/wallet", []() {
    turnLedOn(ledWallet);
    server.send(200, "text/plain", "Wallet LED ON");
  });
  server.on("/led/off/wallet", []() {
    turnLedOff(ledWallet);
    server.send(200, "text/plain", "Wallet LED OFF");
  });

  server.on("/led/on/umbrella", []() {
    turnLedOn(ledUmbrella);
    server.send(200, "text/plain", "Umbrella LED ON");
  });
  server.on("/led/off/umbrella", []() {
    turnLedOff(ledUmbrella);
    server.send(200, "text/plain", "Umbrella LED OFF");
  });

  server.on("/led/on/calculator", []() {
    turnLedOn(ledCalculator);
    server.send(200, "text/plain", "Calculator LED ON");
  });
  server.on("/led/off/calculator", []() {
    turnLedOff(ledCalculator);
    server.send(200, "text/plain", "Calculator LED OFF");
  });

  server.on("/led/on/random", []() {
    turnLedOn(ledRandom);
    server.send(200, "text/plain", "Random LED ON");
  });
  server.on("/led/off/random", []() {
    turnLedOff(ledRandom);
    server.send(200, "text/plain", "Random LED OFF");
  });

  // Update IP config API
  server.on("/update_ip", HTTP_POST, []() {
    if (!server.hasArg("ip") || !server.hasArg("gateway") || !server.hasArg("subnet")) {
      server.send(400, "text/plain", "Missing parameters");
      return;
    }
    IPAddress newIP, newGateway, newSubnet;
    if (!newIP.fromString(server.arg("ip")) || !newGateway.fromString(server.arg("gateway")) || !newSubnet.fromString(server.arg("subnet"))) {
      server.send(400, "text/plain", "Invalid IP format");
      return;
    }
    ipConfig.ip[0] = newIP[0]; ipConfig.ip[1] = newIP[1]; ipConfig.ip[2] = newIP[2]; ipConfig.ip[3] = newIP[3];
    ipConfig.gateway[0] = newGateway[0]; ipConfig.gateway[1] = newGateway[1]; ipConfig.gateway[2] = newGateway[2]; ipConfig.gateway[3] = newGateway[3];
    ipConfig.subnet[0] = newSubnet[0]; ipConfig.subnet[1] = newSubnet[1]; ipConfig.subnet[2] = newSubnet[2]; ipConfig.subnet[3] = newSubnet[3];
    writeIPConfig(ipConfig);
    server.send(200, "text/plain", "IP configuration updated. Please reboot device.");
  });

  server.begin();
  Serial.println("HTTP server started");
}

void loop() {
  server.handleClient();
}

void turnLedOn(int pin) {
  digitalWrite(pin, HIGH);  // turn LED ON
}

void turnLedOff(int pin) {
  digitalWrite(pin, LOW);   // turn LED OFF
}
