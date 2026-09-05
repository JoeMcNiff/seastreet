#!/bin/bash
set -e
cd "$(dirname "$0")"

app=".build/iPhone Camera.app"
mkdir -p "$app/Contents/MacOS" .build/module-cache
binary="$app/Contents/MacOS/PhoneCamera"
if [[ ! -x "$binary" || PhoneCamera.swift -nt "$binary" || Info.plist -nt "$binary" || run.sh -nt "$binary" ]]; then
  cp Info.plist "$app/Contents/Info.plist"
  /usr/bin/arch -arm64 /usr/bin/swiftc -target arm64-apple-macos14.0 -swift-version 5 -module-cache-path .build/module-cache PhoneCamera.swift -o "$binary"
  codesign --force --sign - "$app"
fi

# Never reconnect Python to a stale helper left by an earlier run.
pkill -x PhoneCamera 2>/dev/null || true
sleep 0.2
open -n "$app"
