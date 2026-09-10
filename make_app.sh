#!/bin/bash
# 构建 macOS 应用包 MacWatermarkRemover.app（显示名: Mac 水印去除）
# 用法: bash make_app.sh [图标图片路径]
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
ICON_SRC="${1:-/Users/mouxiaobing/Pictures/好看的/mmexport1784122306391.jpg}"
APP_NAME="MacWatermarkRemover.app"

[ -f "$ICON_SRC" ] || { echo "图标不存在: $ICON_SRC"; exit 1; }

echo "==> [1/3] 生成 AppIcon.icns"
ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
PNG="$(mktemp -d)/icon.png"
sips -s format png "$ICON_SRC" --out "$PNG" >/dev/null
sips -z 16    16    "$PNG" --out "$ICONSET/icon_16x16.png"     >/dev/null
sips -z 32    32    "$PNG" --out "$ICONSET/icon_16x16@2x.png"  >/dev/null
sips -z 32    32    "$PNG" --out "$ICONSET/icon_32x32.png"     >/dev/null
sips -z 64    64    "$PNG" --out "$ICONSET/icon_32x32@2x.png"  >/dev/null
sips -z 128   128   "$PNG" --out "$ICONSET/icon_128x128.png"   >/dev/null
sips -z 256   256   "$PNG" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256   256   "$PNG" --out "$ICONSET/icon_256x256.png"   >/dev/null
sips -z 512   512   "$PNG" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512   512   "$PNG" --out "$ICONSET/icon_512x512.png"   >/dev/null
sips -z 1024  1024  "$PNG" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
mkdir -p Resources
iconutil -c icns "$ICONSET" -o "Resources/AppIcon.icns"
echo "   Resources/AppIcon.icns 已生成"

echo "==> [2/3] 构建 $APP_NAME"
rm -rf "$APP_NAME"
mkdir -p "$APP_NAME/Contents/MacOS" "$APP_NAME/Contents/Resources"
cp Resources/AppIcon.icns "$APP_NAME/Contents/Resources/"

cat > "$APP_NAME/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>                 <string>Mac 水印去除</string>
    <key>CFBundleDisplayName</key>          <string>Mac 水印去除</string>
    <key>CFBundleIdentifier</key>           <string>com.local.macwm</string>
    <key>CFBundleExecutable</key>           <string>MacWatermarkRemover</string>
    <key>CFBundleIconFile</key>             <string>AppIcon</string>
    <key>CFBundlePackageType</key>          <string>APPL</string>
    <key>CFBundleShortVersionString</key>   <string>1.1.0</string>
    <key>CFBundleVersion</key>              <string>1.1.0</string>
    <key>LSMinimumSystemVersion</key>       <string>12.0</string>
    <key>NSHighResolutionCapable</key>      <true/>
    <key>LSApplicationCategoryType</key>    <string>public.app-category.graphics-design</string>
</dict>
</plist>
PLIST

cat > "$APP_NAME/Contents/MacOS/MacWatermarkRemover" <<'LAUNCH'
#!/bin/bash
# App 启动器：定位项目根目录 -> 启动原生窗口（pywebview）
APP_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"   # .app 所在目录即项目根
LOG="$APP_DIR/app.log"

cd "$APP_DIR" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "首次运行: 安装环境..." >> "$LOG"
  bash setup_mac.sh >> "$LOG" 2>&1
fi

# 原生窗口模式（关闭窗口即退出）；pywebview 缺失时自动退回浏览器模式
exec ".venv/bin/python" run_app.py >> "$LOG" 2>&1
LAUNCH
chmod +x "$APP_NAME/Contents/MacOS/MacWatermarkRemover"

echo "==> [3/3] 注册图标缓存"
touch "$APP_NAME"

echo "✅ 已构建: $ROOT/$APP_NAME"
echo "   双击启动（图标生效需注销重登或执行: killall Finder）"
