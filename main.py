# MicroPython
# mail: goctaprog@gmail.com
# MIT license
"""Демонстрационный скрипт для работы с магнитометром HSCDTD008A."""
import sys
import math
import time

from machine import I2C, Pin
from micropython import const
from hscdtd008a import HSCDTD008A
from sensor_pack_2.bus_service import I2cAdapter
from sensor_pack_2.geosensmod import AXIS_ALL, MagRange, UpdateRates, HardIronCalibrator, ICommonMagnitometer, PerformanceProfiles


I2C_ID = const(1)
SCL_PIN = const(7)
SDA_PIN = const(6)
I2C_FREQ = const(400_000)
ITERATIONS = const(33)
#
calibration_on: bool = True


def show_state(sen: ICommonMagnitometer):
    """Выводит текущее состояние датчика."""
    is_15bit = (sen.set_magnitude_range_index() == MagRange.G2)
    print(f"in standby mode: {sen.in_standby_mode()}; "
          f"15-bit mode: {is_15bit}")
    print(f"single shot mode: {sen.is_single_shot_mode()}; "
          f"continuous mode: {sen.is_continuously_mode()}")


def run_calibration(sens: ICommonMagnitometer, duration_ms: int = 15_000, samples_count = 1_000) -> HardIronCalibrator:
    """Проводит процедуру калибровки Hard Iron. Функция самодостаточна и сама настраивает датчик."""
    width = 60
    print("\n" + "=" * width)
    print(" КАЛИБРОВКА ДАТЧИКА (Hard Iron Compensation)")
    print("=" * width)
    print("ИНСТРУКЦИЯ ДЛЯ ПОЛЬЗОВАТЕЛЯ:")
    print("1. Убедитесь, что рядом нет посторонних магнитов или металла.")
    print("2. Медленно вращайте датчик во всех направлениях (восьмерка/сфера).")
    print(f"3. Продолжайте вращение в течение {duration_ms // 1000} секунд.")
    print("=" * width)

    print("\nПодготовьтесь... Начало сбора данных через 3 секунды.")
    time.sleep(3)

    # Работаю в физических единицах (Гауссы)
    sens.set_raw_mode(False)

    # Высокая частота опроса (100 Гц), чтобы не пропустить экстремумы магнитного поля при быстром вращении датчика
    sens.set_performance_profile(PerformanceProfiles.FAST_RESPONSE)

    # Включаю непрерывный режим (обязательно для стабильного потока данных)
    sens.set_continuous_mode(True)
    sens.start_measurement()
    # =========================================================================

    # Вычисляю, как часто НУЖНО опрашивать датчик
    ideal_interval_ms = duration_ms // samples_count
    sleep_time_ms = max(1, min(ideal_interval_ms, sens.get_conversion_cycle_time() + 2))

    print(f"Сбор данных запущен! Период опроса датчика: {sleep_time_ms} мс. Начинайте вращать датчик...\n")

    cal = HardIronCalibrator()
    start_time = time.ticks_ms()
    samples = 0

    while time.ticks_diff(time.ticks_ms(), start_time) < duration_ms:
        if sens.is_data_ready():
            # Явный вызов, а не использование итератора.
            data = sens.get_measurement_value(AXIS_ALL)

            if data is not None:
                cal.update(data)
                samples += 1
                # Визуальный индикатор прогресса
                if samples % 15 == 0:
                    print(".", end="")

        time.sleep_ms(sleep_time_ms)

    print(f"\n\nСбор данных завершен. Собрано образцов: {samples}")

    if samples < samples_count:
        print(f"ВНИМАНИЕ: Собрано слишком мало данных <{samples_count}. Калибровка может быть неточной!")
        print("Убедитесь, что датчик был подключен и находился в активном режиме!")
    cal.calculate_offsets()

    return cal


def show_calibration_offsets(cal: HardIronCalibrator):
    """Выводит вычисленные смещения (offsets) калибратора в консоль."""
    width = 45
    print("\n" + "=" * width)
    print(" РЕЗУЛЬТАТЫ КАЛИБРОВКИ (Смещения)")
    print("=" * width)
    if cal.is_calibrated():
        print(f" Смещение по оси X (Offset X): {cal.offset_x:>8.4f} G")
        print(f" Смещение по оси Y (Offset Y): {cal.offset_y:>8.4f} G")
        print(f" Смещение по оси Z (Offset Z): {cal.offset_z:>8.4f} G")
    else:
        print(" Калибровка не выполнена. Смещения равны 0.0000 G")
    print("=" * width + "\n")


if __name__ == '__main__':
    # =========================================================================
    # Инициализация I2C
    # =========================================================================
    # Замените id, scl, sda на выводы вашей платы!
    i2c = I2C(id=I2C_ID, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=I2C_FREQ)  # Raspberry Pi Pico
    adapter = I2cAdapter(i2c)

    dly: int = 25 # ms
    # max_cnt = ITERATIONS

    # =========================================================================
    # Создание экземпляра датчика
    # =========================================================================
    sensor = HSCDTD008A(adapter)
    print(f"Sensor ID: 0x{sensor.get_id():02X} (ожидается 0x49)")
    print(f"Offset drift values: {sensor.offset_drift_values}")
    print(16 * "_")
    show_state(sensor)
    print(16 * "_")

    # =========================================================================
    # Самопроверка (Self Test)
    # =========================================================================
    # Для self test датчик должен быть в Active Mode
    sensor.set_continuous_mode(False)
    sensor.set_update_rate_index(UpdateRates.HZ_10)
    sensor.start_measurement()

    make_self_test = True

    if make_self_test:
        test_result = sensor.perform_self_test()
        if not test_result:
            print("Sensor NOT passed self test! Broken or invalid sensor mode!")
        else:
            print("Sensor self test passed!")
        print(16 * "_")

    # =========================================================================
    # Измерение температуры (в режиме Force State)
    # =========================================================================
    print("Temperature measurement (Force mode)!")
    sensor.set_continuous_mode(False)
    sensor.start_measurement()
    show_state(sensor)
    sensor.enable_temp_meas(True)  # Запускаем измерение температуры

    cnt = 0
    while cnt < ITERATIONS:
        status = sensor.get_data_status()
        if status.DataReady or status.DataOverrun:
            temp = sensor.get_temperature()
            print(f"Sensor temperature: {temp} ℃")
            # Для следующего замера нужно снова запустить измерение
            sensor.start_measurement()
            sensor.enable_temp_meas(True)
        else:
            print(f"status: DRDY={status.DataReady}, DOR={status.DataOverrun}, "
                  f"FFU={status.FIFOfullAlarm}")
        time.sleep_ms(dly)
        cnt += 1

    print(16 * "_")

    # Hard Iron калибровка
    calib = run_calibration(sensor)
    # показ результатов калибровки
    show_calibration_offsets(calib)
    
    # =========================================================================
    # Измерение магнитного поля (Force State - однократные измерения)
    # =========================================================================
    print("Magnetic field measurement! Force mode!")
    sensor.set_continuous_mode(False)
    sensor.set_update_rate_index(UpdateRates.HZ_10)
    sensor.set_magnitude_range_index(MagRange.G2)  # 15-bit, высокая точность
    sensor.start_measurement()

    cnt = 0
    while cnt < ITERATIONS:
        status = sensor.get_data_status()
        if status.DataReady or status.DataOverrun:
            # Читаем все три оси за один вызов
            field = sensor.get_measurement_value(AXIS_ALL)
            print(f"Raw magnetic field: X:{field.x}; Y:{field.y}; Z:{field.z}")
            # Запускаем следующее однократное измерение
            sensor.start_measurement()
        else:
            print(f"status: DRDY={status.DataReady}, DOR={status.DataOverrun}")
        time.sleep_ms(dly)
        cnt += 1

    print(16 * "_")

    # =========================================================================
    # Измерение магнитного поля (Normal State - непрерывные измерения)
    # =========================================================================
    print("Magnetic field measurement! Periodical (continuous) mode! Компенсация по результату калибровки!")
    sensor.set_continuous_mode(True)
    sensor.set_update_rate_index(UpdateRates.HZ_10)
    sensor.set_magnitude_range_index(MagRange.G2)
    sensor.set_raw_mode(False)  # Возвращать значения в Гауссах
    sensor.start_measurement()
    show_state(sensor)
    print(16 * "_")
    cnt = 0
    while cnt < ITERATIONS:
        status = sensor.get_data_status()
        if status.DataReady:
            # Читаем все три оси за один вызов
            field = sensor.get_measurement_value(AXIS_ALL)
            # компенсация по результату калибровки
            compensated_field = calib.apply(field)
            # Напряженность магнитного поля (модуль вектора) в Гауссах
            mag_field_strength = math.sqrt(compensated_field.x ** 2 + compensated_field.y ** 2 + compensated_field.z ** 2)
            print(f"Mag. field components: X:{compensated_field.x:.4f}; Y:{compensated_field.y:.4f}; "
                  f"Z:{compensated_field.z:.4f}; |B|={mag_field_strength:.4f} G")
            cnt += 1
        time.sleep_ms(dly)


    print(16 * "_")
    print("Done!")