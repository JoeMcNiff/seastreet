#!/bin/zsh
set -e
cd "${0:A:h}"

app=".build/iPhone Camera.app"
mkdir -p "$app/Contents/MacOS" .build/module-cache
cp Info.plist "$app/Contents/Info.plist"
swiftc -swift-version 5 -module-cache-path .build/module-cache PhoneCamera.swift -o "$app/Contents/MacOS/PhoneCamera"
codesign --force --sign - "$app"
open "$app"
