#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

app=".build/iPhone Camera.app"
binary="$app/Contents/MacOS/PhoneCamera"
mkdir -p "$app/Contents/MacOS" .build/module-cache

if [[ ! -x "$binary" || ! -f "$app/Contents/Info.plist" || app/capture/PhoneCamera.swift -nt "$binary" || app/capture/Info.plist -nt "$binary" ]]; then
  cp app/capture/Info.plist "$app/Contents/Info.plist"
  /usr/bin/arch -arm64 /usr/bin/swiftc -target arm64-apple-macos14.0 -swift-version 5 -module-cache-path .build/module-cache app/capture/PhoneCamera.swift -o "$binary"
  codesign --force --sign - "$app"
fi

pkill -x PhoneCamera 2>/dev/null || true
sleep 0.2
open -n "$app"
