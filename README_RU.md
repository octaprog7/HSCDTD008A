# Модуль MicroPython для управления геомагнитным датчиком HSCDTD008A.

## Лицензия
MIT License

## Характеристики
- 3-осевой магнитометр с разрешением 0.15 мкТл/LSB
- Интерфейс: I2C (Standard/Fast/Fast+/HS modes)
- Диапазон измерений: ±2.4 мТл (по каждой оси)
- Частота опроса: 0.5, 10, 20, 100 Гц
- Встроенный датчик температуры
- Функция самопроверки (Self-Test, сбоит!)
- Аппаратная калибровка смещений
- Потребление: < 100 мкА (Standby)
- Корпус: FLGA 1.6×1.6×0.7 мм

## Подключение 
Просто подключите (VCC, GND, SDA, SCL) от вашей платы HSCDTD008A к Arduino, ESP или любой другой плате с прошивкой MicroPython.

## Питание
Напряжение питания HSCDTD008A составляет строго 3.3 В!

## Прошивка
Загрузите прошивку MicroPython на плату NANO (ESP и т. д.), а затем файлы: main.py, hscdtd008a и папку sensor_pack. 
Затем откройте main.py в вашей IDE и запустите его.

## Быстрый старт
```python
from machine import I2C, Pin
import hscdtd008a

# Инициализация I2C
i2c = I2C(1, scl=Pin(7), sda=Pin(6), freq=400_000)

# Создание экземпляра датчика
sensor = hscdtd008a.HSCDTD008A(i2c)

# Проверка ID чипа
print(f"Chip ID: 0x{sensor.get_id():02X}")  # Ожидается 0x49

# Запуск измерений
sensor.start_measurement()

# Чтение данных
field = sensor.get_measurement_value()
print(f"Magnetic field: X={field.x}, Y={field.y}, Z={field.z}")

# Чтение температуры
temp = sensor.get_temperature()
print(f"Temperature: {temp}°C")
```


### 6. **Калибровка**
```markdown
## Калибровка (Hard Iron Compensation)
Для компенсации влияния постоянных магнитов и ферромагнитных материалов:

1. Запустите процедуру калибровки:
```python
from sensor_pack.geosensmod import run_calibration

calibrator = run_calibration(sensor, duration_ms=15000)
offsets = calibrator.calculate_offsets()
```
2. Вращайте датчик во всех трех плоскостях в течение 15 секунд!
3. Сохраните результаты:

```python
from sensor_pack.geosensmod import save_calibration
save_calibration(offsets, "mag_calib.json")
```
4. Применяйте калибровку при чтении:
```python
calib_data = calibrator.apply(raw_data)
```

## Режимы работы

### Режимы питания
- **Stand-by Mode**: Низкое энергопотребление, доступ к регистрам
- **Active Mode**: Активные измерения

### Состояния измерений
- **Force State**: Однократное измерение по команде
- **Normal State**: Непрерывные измерения с заданной частотой (ODR)

### Частоты опроса (ODR)
- 0.5 Гц - для экономии энергии
- 10 Гц - компас, навигация
- 20 Гц - динамические системы
- 100 Гц - высокоскоростные приложения

### Разрешение
- 14-bit: ±8191 отсчетов
- 15-bit: ±16383 отсчетов (по умолчанию)

## API драйвера

### Основные методы
| Метод                     | Описание                            |
|---------------------------|-------------------------------------|
| `get_id()`                | Возвращает ID чипа (0x49)           |
| `start_measurement()`     | Запускает измерения                 |
| `get_measurement_value()` | Возвращает данные по осям (X, Y, Z) |
| `get_temperature()`       | Возвращает температуру (°C)         |
| `is_data_ready()`         | Проверяет готовность данных         |
| `perform_self_test()`     | Выполняет самопроверку              |

### Настройка
| Метод                              | Описание                      |
|------------------------------------|-------------------------------|
| `set_continuous_mode(True/False)`  | Непрерывный/однократный режим |
| `set_update_rate_index(rate)`      | Установка частоты ODR         |
| `set_magnitude_range_index(range)` | Установка диапазона           |
| `set_raw_mode(True/False)`         | Сырые данные или Гауссы       |


## Расчет магнитного азимута
```python
import math
from sensor_pack.geosensmod import get_magnetic_heading, get_true_heading

# Получение откалиброванных данных
data = sensor.get_measurement_value()
calib_data = calibrator.apply(data)

# Расчет азимута (датчик должен быть горизонтален)
heading = get_magnetic_heading(calib_data.x, calib_data.y)

# Учет магнитного склонения (для Москвы +11.5°)
true_heading = get_true_heading(heading, declination=11.5)

print(f"Магнитный азимут: {heading:.1f}°")
print(f"Истинный азимут: {true_heading:.1f}°")
```

## Устранение неполадок

### Датчик не найден
- Проверьте подключение проводов I2C
- Убедитесь, что питание 3.3В подключено
- Проверьте подтягивающие резисторы на линиях I2C (4.7кОм)
- Убедитесь, что адрес I2C правильный (0x0C)

### Self-test не проходит
- Убедитесь, что датчик в режиме Force State
- Добавьте задержку 10мс после установки бита STC
- Проверьте, что датчик не в режиме Stand-by
 
**Инженерный совет:** 
Если self-test упорно не проходит, но при этом датчик стабильно выдает корректные значения индукции магнитного поля Земли (около **0.25 – 0.65 G** для вашей широты) и адекватно реагирует на вращение — **вы можете смело игнорировать ошибку self-test**. Физическая работоспособность MEMS-структуры в данном случае важнее формальной проверки цифрового регистра!

### Нестабильные показания
- Выполните калибровку Hard Iron
- Уберите датчик от источников магнитных помех (USB-кабели, моторы, динамики)
- Проверьте, что датчик закреплен неподвижно

# Картинки
## IDE
### Датчик температуры
![alt text](https://github.com)
### Компоненты магнитного поля
![alt text](https://github.com)
## Макетная плата
![alt text](https://github.com)
