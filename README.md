# MicroPython module for control HSCDTD008A Geomagnetic Sensor.

## [На русском](README_RU.md)

## 🇨🇳 对中国开发者 / For Developers from China

Я знаю, что зеркала некоторых моих репозиториев активно используются на китайских платформах (Gitee / GitCode), и очень рад, что мой код помогает вашим проектам и обучению! 如果您在中国 впн/镜像 发现了我的开源项目，并且它对 structure 或者是 你的项目 有所帮助，**请在 GitHub 原仓库上点个赞 (Star) ⭐**！这对我持续更新和维护驱动非常重要。谢谢大家 Support！ *(If you are using my libraries in China via Gitee/mirrors, please support the original repository by giving it a **Star ⭐ on GitHub**!)*


Just connect (VCC, GND, SDA, SCL) from your HSCDTD008A board to Arduino, ESP or any other board with MicroPython firmware.

Supply voltage HSCDTD008A 3.3 Volts only!

Upload micropython firmware to the NANO(ESP, etc) board, and then files: main.py, hscdtd008a and sensor_pack folder. 
Then open main.py in your IDE and run it.

# Pictures
## IDE
### Chip temperature sensor
![alt text](https://github.com/octaprog7/GeomagneticSensor/blob/master/ide_temp.png)
### Magnetic field component
![alt text](https://github.com/octaprog7/GeomagneticSensor/blob/master/ide_mag_xyz.png)
## Макетная плата/Bread board
![alt text](https://github.com/octaprog7/GeomagneticSensor/blob/master/board.jpg)
