#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

app=".build/iPhone Camera.app"
mkdir -p "$app/Contents/MacOS" .build/module-cache
binary="$app/Contents/MacOS/PhoneCamera"
cp app/capture/Info.plist "$app/Contents/Info.plist"
/usr/bin/arch -arm64 /usr/bin/swiftc -target arm64-apple-macos14.0 -swift-version 5 -module-cache-path .build/module-cache app/capture/PhoneCamera.swift -o "$binary"
codesign --force --sign - "$app"
open "$app"
