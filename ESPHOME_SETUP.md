# ESPHome Configuration for RF Connect

This guide shows the complete ESPHome configuration for RF Connect using a D1 Mini with CC1101 transceiver.

## Hardware Setup

### Components Required
- ESP8266 D1 Mini
- CC1101 433MHz RF Transceiver Module
- Jumper wires

### Pin Connections
```
CC1101  →  D1 Mini
VCC     →  3.3V
GND     →  GND
SCK     →  D5 (GPIO14)
MISO    →  D6 (GPIO12)
MOSI    →  D7 (GPIO13)
CS      →  D4 (GPIO2)
GDO0    →  D2 (GPIO4)  - TX pin
GDO2    →  D1 (GPIO5)  - RX pin
```

## Complete ESPHome Configuration

```yaml
esphome:
  name: esphomerf
  friendly_name: espHomeRF

esp8266:
  board: d1_mini

logger:
  level: DEBUG

api:
  encryption:
    key: !secret api_key
  services:
    - service: rf_code_send
      variables:
        device: int
        channel: int
        state: bool
        level: int
      then:
        - script.execute:
            id: rf_tx
            device: !lambda "return device;"
            channel: !lambda "return channel;"
            state: !lambda "return state;"
            level: !lambda "return level;"

ota:
  - platform: esphome
    password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  fast_connect: true
  ap:
    ssid: "Esphomerf Fallback Hotspot"
    password: !secret wifi_password

spi:
  clk_pin: D5
  miso_pin: D6
  mosi_pin: D7

cc1101:
  id: cc1101_1
  cs_pin: D4
  frequency: 433.92MHz
  modulation_type: ASK/OOK
  filter_bandwidth: 203kHz

remote_receiver:
  id: rf_rx
  pin: D1          # CC1101 GDO2
  dump: nexa
  tolerance: 60%
  filter: 80us
  idle: 10ms
  on_nexa:
    then:
      - homeassistant.event:
          event: esphome.rf_code_received
          data:
            device: !lambda |-
              char buf[11];
              sprintf(buf, "0x%06X", x.device);
              return std::string(buf);
            channel: !lambda "return x.channel;"
            group: !lambda "return x.group;"
            state: !lambda "return x.state;"
            level: !lambda "return x.level;"

remote_transmitter:
  pin: D2          # CC1101 GDO0
  carrier_duty_percent: 100%

script:
  - id: rf_tx
    mode: queued
    parameters:
      device: int
      channel: int
      state: bool
      level: int
    then:
      - lambda: |-
          ESP_LOGI("rf_tx", "TX start dev=%d ch=%d state=%d level=%d",
                   device, channel, (int)state, level);
          id(cc1101_1).set_idle(); 
          
      - cc1101.begin_tx
      - delay: 5ms

      - remote_transmitter.transmit_nexa:
          device: !lambda "return device;"
          channel: !lambda "return channel;"
          group: false
          state: !lambda "return state;"
          level: !lambda "return level;"
          repeat:
            times: 6
            wait_time: 15ms

      - cc1101.begin_rx

      - lambda: |-
          ESP_LOGI("nexa_tx", "TX done -> back to RX");
```

## Configuration Breakdown

### Service: rf_code_send
RF Connect calls this service to transmit RF codes:
- **device**: Integer (e.g., 11965118 from hex 0xB692BE)
- **channel**: Integer (0-15)
- **state**: Boolean (true/false for ON/OFF)
- **level**: Integer (0-255, typically 0 for on/off devices)

### Event: esphome.rf_code_received
ESPHome fires this event when receiving RF codes:
- **device**: Hexadecimal string (e.g., "0xB692BE")
- **channel**: Integer
- **state**: Integer (0 or 1)
- **group**: Boolean
- **level**: Integer

### Script: rf_tx
Handles RF transmission sequence:
1. Sets CC1101 to IDLE (stops reception)
2. Switches to TX mode
3. Waits 5ms for oscillator stabilization
4. Transmits Nexa protocol (6 repetitions)
5. Returns to RX mode

## Testing

### Test RF Reception
1. Flash the ESPHome configuration
2. Check ESPHome logs
3. Press buttons on your RF remote
4. Verify log output shows received codes

### Test RF Transmission
Use Home Assistant Developer Tools → Services:
```yaml
service: esphome.esphomerf_rf_code_send
data:
  device: 11965118
  channel: 1
  state: true
  level: 0
```

## Troubleshooting

### No RF Codes Received
- Check pin connections (especially GDO2 to D1)
- Verify antenna is connected to CC1101
- Check ESPHome logs for errors
- Try adjusting `tolerance` and `filter` values

### RF Transmission Not Working
- Check GDO0 pin connection (D2)
- Verify CC1101 is in TX mode during transmission
- Check ESPHome logs for transmission confirmation
- Test with known working RF receiver

### CC1101 Not Detected
- Verify 3.3V power (not 5V!)
- Check SPI pin connections
- Ensure CS pin is correct (D4)
- Check ESPHome logs for CC1101 initialization errors

## Secrets File Example

Create `secrets.yaml` in your ESPHome folder:
```yaml
wifi_ssid: "YourWiFiName"
wifi_password: "YourWiFiPassword"
api_key: "your-32-character-api-key"
ota_password: "your-ota-password"
```

## Next Steps

1. Flash this configuration to your D1 Mini
2. Install RF Connect integration in Home Assistant
3. Add your first device using the RF code learning feature
4. Test controlling your RF devices!
