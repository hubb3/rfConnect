# Quick Start Guide

## Installation Steps

1. **Copy Integration to Home Assistant**
   ```
   Copy the entire `custom_components/rfconnect` folder to your Home Assistant 
   `config/custom_components/` directory
   ```

2. **Restart Home Assistant**
   - Settings → System → Restart

3. **Add Integration**
   - Settings → Devices & Services
   - Click "Add Integration"
   - Search for "RF Connect"
   - Enter ESPHome entity ID: `esphome.esphomeRF`

## Testing Checklist

### Test Relay Device
- [ ] Add new relay device (e.g., "Test Light")
- [ ] Select device type: **RF Relay (Switch)**
- [ ] **Automatic code learning page loads**
- [ ] Press ON button on your RF remote
  - Code is captured automatically
  - Click Submit to see it in the list
- [ ] Press OFF button on your RF remote
  - Code is captured automatically
  - Click Submit to see both codes
- [ ] Click **Done** to finish
- [ ] Verify entities are created:
  - `switch.test_light`
  - `event.test_light_pressed_on`
  - `event.test_light_pressed_off`
- [ ] Toggle switch ON from UI
  - Check ESPHome logs for service call
  - Verify `esphome.esphomerf_rf_code_send` was called
- [ ] Toggle switch OFF from UI
- [ ] Press physical RF remote ON button
  - Verify switch updates to ON in HA
  - Verify `event.test_light_pressed_on` fires
- [ ] Press physical RF remote OFF button
  - Verify switch updates to OFF in HA
  - Verify `event.test_light_pressed_off` fires

### Test Button Device
- [ ] Add new button device (e.g., "Test Button")
- [ ] Select device type: **RF Button (Event)**
- [ ] Press buttons on your RF remote
  - Codes captured automatically
  - Click Submit to update list
- [ ] Toggle unwanted codes OFF to remove them
- [ ] Click **Done** when finished
- [ ] Verify two event entities are created:
  - `event.test_button_pressed_on`
  - `event.test_button_pressed_off`
- [ ] Press physical RF remote ON button
  - Check if `rfconnect_button_pressed` event fires
  - Verify button_type = "on"
- [ ] Press physical RF remote OFF button
  - Check if `rfconnect_button_pressed` event fires
  - Verify button_type = "off"

### Test Duplicate Detection
- [ ] During code learning, press same button twice
- [ ] Click Submit
- [ ] Verify code only appears once in list

### Test Options Flow
- [ ] Go to device configuration
- [ ] Add additional RF code (manual entry)
- [ ] Verify new code works
- [ ] Remove RF code
- [ ] Verify code is removed
- [ ] Test device deletion

## Debugging

### Check ESPHome Events
Developer Tools → Events → Listen to Event:
```
esphome.rf_code_received
```

Press your RF remote and verify the event data structure:
```json
{
  "device": "0xB692BE",
  "channel": 1,
  "state": 1,
  "group": false,
  "level": 0
}
```

### Check Service Calls
Developer Tools → Services → Call Service:
```yaml
service: esphome.esphomerf_rf_code_send
data:
  device: 11965118
  channel: 1
  state: true
  level: 0
```

## Common Issues

### Issue: "No codes learned"
- **Solution**: Make sure you're pressing RF remote buttons
- Click Submit to see codes appear in the list
- Codes only save when you click Done with them in ON state

### Issue: Codes not appearing in list
- **Solution**: Click Submit to refresh the list
- Check ESPHome logs to verify codes are being received
- Verify event name is `esphome.rf_code_received`

### Issue: Switch doesn't respond to RF codes
- **Solution**: Check that ESPHome event name matches exactly: `esphome.rf_code_received`
- Verify event data includes device, channel, and state fields
- Check device format is hex string (e.g., "0xB692BE")

### Issue: RF commands not sending
- **Solution**: Verify service name is exactly: `esphome.esphomerf_rf_code_send`
- Check ESPHome device is online
- Verify device parameter is integer (not hex string)

### Issue: Events not firing for relay devices
- **Solution**: Make sure you added the relay device (not button device)
- Both switch and event entities should be created for relays
- Check Home Assistant logs for `rfconnect_button_pressed` events

## Next Steps

1. ✅ Test with your actual ESPHome device
2. ✅ Add your real RF devices using automatic learning
3. Create automations using the event entities
4. Integrate relays into your existing scenes
5. Test relay button press detection for advanced automations

## File Structure

Your final structure should look like:
```
config/
├── custom_components/
│   └── rfconnect/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── event.py
│       ├── manifest.json
│       ├── storage.py
│       ├── strings.json
│       ├── switch.py
│       └── translations/
│           └── en.json
└── configuration.yaml
```
