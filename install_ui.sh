mkdir diyhueUI

if [ $1 = diyhue ]; then
    # diyHue
    echo "diyhue ui install"   
    curl -sL https://github.com/diyhue/diyHueUI/releases/latest/download/DiyHueUI-release.zip -o diyHueUI.zip
else
    # Hendriksen-mark
    echo "hendriksen-mark ui install"
    curl -sL https://github.com/hendriksen-mark/diyHueUI/releases/latest/download/DiyHueUI-release.zip -o diyHueUI.zip
fi
unzip -qo diyHueUI.zip -d diyhueUI
rm diyHueUI.zip
cp -r diyhueUI/dist/index.html BridgeEmulator/flaskUI/templates/
cp -r diyhueUI/dist/assets BridgeEmulator/flaskUI/
rm -r diyhueUI
