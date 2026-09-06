# Robin Cam

1. On the Mac, activate the Python environment and run:

   ```bash
   python -m app.ui.demo
   ```

2. Open `SeaStreetCamera.xcodeproj` in Xcode.
3. Select the **SeaStreetCamera** target, open **Signing & Capabilities**, and
   choose your Apple development team.
4. Connect and trust the iPhone, choose it as the run destination, and press Run.
5. In the phone app, enter the Mac hostname printed by Python and tap
   **Start Camera**.

Robin Cam captures the rear camera at 1080p/30 fps, sends up to 8 Mbps over WebRTC,
scans PDF417 driver-license barcodes, and plays criminal-record and invalid-ID
alerts. A valid license lookup is silent. Keep the app foregrounded and both
devices on the same local network.

The existing SeaStreet local certificate must be trusted on the phone. If it is
not, use the certificate URL printed by `python -m app.ui.demo`, install the
profile, then enable it under **Settings → General → About → Certificate Trust
Settings**.
