# MicroPython
# mail: goctaprog@gmail.com
# MIT license
"""MicroPython module for HSCDTD008A Geomagnetic Sensor"""
from time import sleep_ms
import array
from micropython import const
from collections import namedtuple

from sensor_pack_2.bus_service import I2cAdapter
from sensor_pack_2.geosensmod import (MagnetometerData, UpdateRates, OversampleLevels, PerformanceProfile, MagRange,
                                      ICommonMagnitometer, AXIS_X, AXIS_Y, AXIS_Z, AXIS_ALL, PerformanceProfiles)
from sensor_pack_2.base_sensor import IDentifier, DeviceEx, check_value

#
DataStatus = namedtuple("DataStatus", "DataReady DataOverrun FIFOfullAlarm")

_REG_ADDR_SELF_TEST_RESPONSE = const(0x0C)
_REG_ADDR_X_AXIS_OUTPUT_DATA= const(0x10)
_REG_ADDR_CTRL1 = const(0x1B)
_REG_ADDR_CTRL2 = const(0x1C)
_REG_ADDR_CTRL3 = const(0x1D)
_REG_ADDR_CTRL4 = const(0x1E)
_REG_ADDR_OFFS_X_LSB = const(0x20)
_REG_ADDR_CASE_TEMP = const(0x31)
_REG_ADDR_ID = const(0x0F)
_REG_ADDR_STATUS = const(0x18)

# Для перевода сырых данных в Гауссы
# Чувствительность датчика: 0.15 μT/LSB = 0.0015 G/LSB
_SENSITIVITY_G_PER_LSB = const(0.0015)

# Константы для процедуры самопроверки (Self-Test Response register)
_STB_READY_VALUE = const(0x55)          # Значение регистра до начала теста
_STB_TEST_SUCCESS_VALUE = const(0xAA)   # Значение регистра после успешного теста

# Обратный маппинг битов регистра в унифицированные индексы UpdateRates.
# Индекс кортежа совпадает со значением битов ODR (0b00=0, 0b01=1, 0b10=2, 0b11=3)
_ODR_TO_RATE = (
    UpdateRates.HZ_0_5,  # 0b00: 0.5 Гц
    UpdateRates.HZ_10,  # 0b01: 10 Гц
    UpdateRates.HZ_20,  # 0b10: 20 Гц
    UpdateRates.HZ_100,  # 0b11: 100 Гц
)

# Маппинг "диапазона измерения напряженности магнитного поля" на бит RS (Resolution Select) регистра CTRL4.
# Индекс 0 = MagRange.G2, Индекс 1 = MagRange.G8
# Формат: (фактический_сохраняемый_индекс, значение_бита_RS)
_RANGE_MAPPING = (
    (MagRange.G2, 1),  # 15-bit mode (0.075 uT/LSB, выше точность)
    (MagRange.G8, 0),  # 14-bit mode (0.15 uT/LSB, по умолчанию)
)
# МАППИНГ ПРОФИЛЕЙ ДЛЯ HSCDTD008A
# Карта профилей производительности.
# Индексы (0-4) соответствуют значениям в классе PerformanceProfiles.
# Примечание: HSCDTD008A не имеет аппаратного OSR. Параметр oversample
# используется только для программного усреднения в высокоуровневом коде.
_PROFILE_MAP = (
    # ВЫСОКАЯ_ТОЧНОСТЬ
    # 10 Гц - практичный минимум для стабильности без чрезмерных задержек.
    # Высокий уровень OSR указывает высокоуровневому коду применять сильное программное усреднение.
    PerformanceProfile(UpdateRates.HZ_10, OversampleLevels.ULTRA_HIGH),
    # ФОНОВЫЙ_МОНИТОРИНГ
    # 0.5 Гц - реальная аппаратная возможность чипа для сверхнизкого энергопотребления.
    PerformanceProfile(UpdateRates.HZ_0_5, OversampleLevels.MEDIUM_LOW),
    # ДИНАМИЧЕСКАЯ_НАВИГАЦИЯ
    # 20 Гц - ближайшая доступная частота к запрошенным 50 Гц.
    # Хороший баланс для медленных роботов.
    PerformanceProfile(UpdateRates.HZ_20, OversampleLevels.BALANCED),
    # КОМПЕНСАЦИЯ_НАКЛОНА (TILT_COMPENSATION)
    # 100 Гц - максимальная частота непрерывного режима. Идеально для фильтров (Калман).
    PerformanceProfile(UpdateRates.HZ_100, OversampleLevels.BALANCED),
    # БЫСТРЫЙ_ОТКЛИК
    # 100 Гц - физический предел чипа в непрерывном режиме (переключение с запрошенных 200 Гц).
    PerformanceProfile(UpdateRates.HZ_100, OversampleLevels.HIGH_SPEED)
)

# ODR для HSCDTD008A.
# Индекс кортежа совпадает со значением UpdateRates (0..7).
# Формат: (фактически_возвращаемый_UpdateRates, биты для регистра CTRL1[4:3])
# Согласно даташиту: 00=0.5Hz, 01=10Hz, 10=20Hz, 11=100Hz
_ODR_MAPPING = (
    # 0: HZ_10 -> Поддерживается напрямую
    (UpdateRates.HZ_10, 0b01),
    # 1: HZ_50 -> Не поддерживается. Переход на ближайшую частоту (20 Гц)
    (UpdateRates.HZ_20, 0b10),
    # 2: HZ_100 -> Поддерживается напрямую
    (UpdateRates.HZ_100, 0b11),
    # 3: HZ_200 -> Не поддерживается. Переход до максимума чипа (100 Гц)
    (UpdateRates.HZ_100, 0b11),
    # 4: HZ_500 -> Не поддерживается. Переход до максимума чипа (100 Гц)
    (UpdateRates.HZ_100, 0b11),
    # 5: HZ_1000 -> Не поддерживается. Переход до максимума чипа (100 Гц)
    (UpdateRates.HZ_100, 0b11),
    # 6: HZ_0_5 -> Поддерживается напрямую (спец. режим HSC)
    (UpdateRates.HZ_0_5, 0b00),
    # 7: HZ_20 -> Поддерживается напрямую
    (UpdateRates.HZ_20, 0b10),
)


def _get_multiplier() -> float:
    """Возвращает множитель для перевода сырых данных АЦП в Гауссы."""
    return _SENSITIVITY_G_PER_LSB


class HSCDTD008A(ICommonMagnitometer, IDentifier):
    """Высокочувствительный трех осевой датчик магнитного поля от AlpsAlpine."""

    def __init__(self, adapter: I2cAdapter, address: int = 0x0C):
        check_value(value=address, valid_range=(0x0C,), error_msg=f"Invalid address value: {address}")
        self._connection = DeviceEx(adapter=adapter, address=address, big_byte_order=False)
        #
        t = 0, 0, 0
        self._mag_field_comp = array.array("h", t)  # h - целое со знаком, размером 2 байта!
        self._mag_field_offs = array.array("h", t)  # h - целое со знаком, размером 2 байта!
        self._buf_2 = bytearray(2)  # для хранения
        self._buf_6 = bytearray(6)  # для хранения
        # Этот датчик имеет режим ожидания и активный режим работы.
        # Состояние с низким энергопотреблением. В режиме ожидания есть доступ к регистрам!
        # self._stand_by_pwr_mode = None
        # Переход в активное (рабочее) состояние производится изменением содержимого управляющего регистра
        # В активном режиме датчик может производить однократное (Force State)
        # или периодические (Normal State) измерения с частотой .5, 10, 20, 100 Hz
        # режим однократных или периодических измерений (только в Active Power Mode)
        # чтение смещений и запись из в _mag_field_offs
        self._read_offset()
        self._use_offset = False
        # хранит последнее значение температуры, считанное методом get_temperature()
        self._temperature = 0
        #
        self._update_rate_index = UpdateRates.HZ_10
        self._continuous_mode = False
        # диапазон напряженности магнитного поля на который1 настроен датчик
        self._magnitude_range_index = MagRange.G2
        self._over_sample_index = OversampleLevels.ULTRA_HIGH
        # если Истина, то get_measurement_value возвращает результат в безразмерных (сырых значениях)
        # если Ложь, то get_measurement_value возвращает результат в Гауссах!
        self._raw_mode = False
        self._performance_profile = PerformanceProfiles.DYNAMIC_NAVIGATION  # профиль по умолчанию

        #
        self.setup()
        self.refresh_config()

    def read_buf_from_mem(self, mem_addr: int, buf: bytearray):
        """Читает из устройства с адресом address в буфер buf, начиная с адреса в устройстве mem_addr.
        Количество считываемых байт определяется длиной буфера buf."""
        return self._connection.read_buf_from_mem(mem_addr, buf)

    @staticmethod
    def _copy(destination, source):
        for i, item in enumerate(source):
            destination[i] = item

    def _read_ctrl1(self) -> int:
        """Чтение регистра управления 1"""
        return self._read_reg(_REG_ADDR_CTRL1)[0]

    def _read_raw_field_comp(self, axis_index: int) -> int:
        check_value(axis_index, (AXIS_X, AXIS_Y, AXIS_Z))
        if AXIS_ALL == axis_index:
            raise ValueError(f"Неверный индекс компоненты магнитного поля: {axis_index}!")
        source_addr = _REG_ADDR_X_AXIS_OUTPUT_DATA
        # Битовый сдвиг >> 1 превращает маски (1, 2, 4) в индексы (0, 1, 2).
        # Битовый сдвиг << 1 умножает индекс на 2, давая байтовые смещения (0, 2, 4).
        addr_offs = (axis_index >> 1) << 1
        buf = self._buf_2
        # читаю компоненту в буфер
        self.read_buf_from_mem(source_addr + addr_offs, buf)
        return self._connection.unpack("h", buf)[0]

    def _read_field(self, offset: bool = False):
        """Считывает в заранее подготовленные буферы составляющие магнитного поля (при offset=False),
        иначе считывает Offset drift values"""
        source_addr = _REG_ADDR_X_AXIS_OUTPUT_DATA  # read output X, output Y, output Z
        destination = self._mag_field_comp
        if offset:  # read offset X, offset Y, offset Z
            source_addr = _REG_ADDR_OFFS_X_LSB
            destination = self._mag_field_offs
        b_val = self._buf_6
        # читаю в буфер 3x2 байт из датчика
        self.read_buf_from_mem(source_addr, b_val)
        conn = self._connection
        # копирую сырые значения со знаком в destination!!!
        self._copy(destination, conn.unpack(fmt_char="hhh", source=b_val))

    def _read_offset(self):
        """считывает из датчика и записывает в массив несколько смещений!"""
        self._read_field(offset=True)

    def _read_reg(self, reg_addr: int, bytes_count: int = 1) -> bytes:
        """Считывает значение из регистра по адресу регистра 0..0x10. Смотри _get_reg_address"""
        return self._connection.read_reg(reg_addr, bytes_count)

    def _write_reg(self, reg_addr: int, value: int, bytes_count: int = 1):
        """Записывает в регистр с адресом reg_addr значение value по шине."""
        conn = self._connection
        conn.write_reg(reg_addr, value, bytes_count)

    def get_conversion_cycle_time(self) -> int:
        """Возвращает время преобразования сигнала измеряемой величины в значение,
        готовое к считыванию. В миллисекундах.

        Согласно даташиту (стр. 14 и 15, ACTIVE MEASUREMENT TIME),
        время измерения является аппаратной константой и всегда составляет < 5 мс
        независимо от частоты ODR и разрешения (14/15 бит).

        Это общее время, за которое чип должен успеть всё: измерить магнитное поле по трем осям,
        измерить температуру и выполнить внутреннюю температурную компенсацию.

        Производитель аппаратно "отключил" возможность программного отслеживания готовности именно температуры (бит TRDY всегда читается как 0,
        хотя внутри чипа компенсация работает).
        """
        return 5    # 5 ms!

    def _get_all_meas_result(self) -> tuple:
        """Для наибыстрейшего считывания за один вызов всех результатов измерений из датчика по
        относительно медленной шине!"""
        b_val = self._buf_6
        self.read_buf_from_mem(0x10, b_val)     # x, y, z. 6 bytes
        return self._connection.unpack(fmt_char='hhh', source=b_val)

    def get_temperature(self) -> int:
        """Возвращает температуру корпуса датчика в °C.
        LSB = 1°C, диапазон -128...+127°C.
        Также обновляет внутреннее поле self._temperature."""
        b_val = self._read_reg(_REG_ADDR_CASE_TEMP)
        self._temperature =  self._connection.unpack("b", b_val)[0]  # read as signed char
        return self._temperature

    def get_id(self):
        """Должен возвратить 0x49"""
        return self._read_reg(_REG_ADDR_ID)[0]

    def get_data_status(self, raw: bool = False) -> int | DataStatus:
        """Возвращает кортеж битов(номер бита): DRDY(6), DOR(5), FFU(2)"""
        stat = self._read_reg(_REG_ADDR_STATUS)[0]
        if raw:
            return stat
        data_ready = bool(stat & 0b0100_0000)
        dor = bool(stat & 0b0010_0000)
        ffu = bool(stat & 0b0000_0100)
        return DataStatus(DataReady=data_ready, DataOverrun=dor, FIFOfullAlarm=ffu)

    def _control_1(
            self,
            active_power_mode: bool | None = True,  # bit 7
            output_data_rate: int | None = 1,  # bit 4,3; 0 - .5 Hz, 1 - 10 Hz, 2 - 20 Hz, 3 - 100 Hz
            force_state: bool | None = True,  # bit 1
    ):
        """Control 1 Register (CTRL1)."""
        val = self._read_ctrl1()
        if active_power_mode is not None:
            val &= ~(1 << 7)  # mask
            val |= active_power_mode << 7
        if output_data_rate is not None:
            val &= ~(0b11 << 3)  # mask
            val |= output_data_rate << 3
        if force_state is not None:
            val &= ~(1 << 1)  # mask
            val |= force_state << 1
        self._write_reg(_REG_ADDR_CTRL1, val, 1)

    def _control_2(
            self,
            fco: bool | None = False,  # bit 6; Data storage method at FIFO. 0 = Direct, 1 = Comparison. Note:
            # Enabled if FIFO
            aor: bool | None = False,  # bit 5; Choice of method of data Comparison at FIFO. 0 = OR ,
            # 1 = AND.Enabled if FIFO
            fifo_enable: bool | None = False,  # bit 4; 0 = Disable, 1 = Enable
            den: bool | None = False,  # bit 3; Data Ready Function Control Enable. 0 = Disabled, 1 = Enabled
            data_ready_lvl_ctrl: bool | None = True  # bit 2; DRDY signal active level control, 0 = ACTIVE LOW,
            # 1 = ACTIVE HIGH
    ):
        """Control 2 Register (CTRL2).
        When a CTRL2 register value was changed during the measurement,
        The contents of the change are reflected after measurement."""
        val = self._read_reg(_REG_ADDR_CTRL2)[0]
        if fco is not None:
            val &= ~(1 << 6)  # mask
            val |= fco << 6
        if aor is not None:
            val &= ~(1 << 5)  # mask
            val |= aor << 5
        if fifo_enable is not None:
            val &= ~(1 << 4)  # mask
            val |= fifo_enable << 4
        if den is not None:
            val &= ~(1 << 3)  # mask
            val |= den << 3
        if data_ready_lvl_ctrl is not None:
            val &= ~(1 << 2)  # mask
            val |= data_ready_lvl_ctrl << 2
        self._write_reg(_REG_ADDR_CTRL2, val, 1)

    def _control_3(
            self,
            soft_reset: bool | None = False,  # bit 7; Soft Reset Control Enable. 0 = No Action, 1 = Soft Reset
            force_state: bool | None = False,  # bit 6; Start to Measure in Force State. 0 = No Action, 1 = Meas. Start
            self_test: bool | None = False,  # bit 4; Self Test Control Enable.
            # 0 = No Action, 1 = Set parameters to Self Test Response (STB) register.
            temp_measure: bool | None = False,  # bit 1; Start to Measure Temperature in Active Mode.
            # 0 = No Action, 1 = Measurement Start
            calibrate_offset: bool | None = False,  # bit 0; Start to Calibrate Offset in Active Mode.
            # 0 = No Action, 1 = Action
    ):
        """Control 3 Register (CTRL3).
        Bit control at the same time is prohibited.
        Priority of this register is MSB."""
        val = self._read_reg(_REG_ADDR_CTRL3)[0]
        if soft_reset is not None:
            val &= ~(1 << 7)    # mask
            val |= soft_reset << 7
        if force_state is not None:
            val &= ~(1 << 6)  # mask
            val |= force_state << 6
        if self_test is not None:
            val &= ~(1 << 4)  # mask
            val |= self_test << 4
        if temp_measure is not None:
            val &= ~(1 << 1)  # mask
            val |= temp_measure << 1
        if calibrate_offset is not None:
            val &= 0xFE  # mask
            val |= calibrate_offset
        self._write_reg(_REG_ADDR_CTRL3, val, 1)

    def _control_4(
            self,
            hi_dynamic_range: bool | None = False,  # bit 4; Set Dynamic range of output data.
            # 0 = 14 bit signed value (-8192 to +8191) (Default)
            # 1 = 15 bit signed value (-16384 to +16383)
    ):
        """Control 4 Register (CTRL4).
        When a CTRL4 register value was changed during the measurement,
        The contents of the change are reflected after measurement."""
        if hi_dynamic_range is None:
            return
        val = 0x80 | (hi_dynamic_range << 4)
        self._write_reg(_REG_ADDR_CTRL4, val, 1)

    def perform_self_test(self) -> bool:
        """Возвращает True, если самопроверка пройдена!
        Не выполняйте проверку в режиме stand by!!! Только в режиме active_power_mode!!!"""

        # Проверяю, что датчик вообще включен (Active Mode)
        if self.in_standby_mode():
            return False

        # Гарантирую состояние Force State для стабильности теста
        if self.is_continuously_mode():
            self.set_continuous_mode(False)
            self.start_measurement()

        # Время на стабилизацию внутренних цепей В ЛЮБОМ СЛУЧАЕ!
        sleep_ms(20)

        # Проверяю начальное значение STB (должно быть _STB_READY_VALUE)
        val = self._read_reg(_REG_ADDR_SELF_TEST_RESPONSE)[0]
        if val != _STB_READY_VALUE:
            # иногда первое чтение после инициализации "мусорное"
            sleep_ms(10)
            val = self._read_reg(_REG_ADDR_SELF_TEST_RESPONSE)[0]
            if val != _STB_READY_VALUE:
                return False

        # Запускаю самопроверку (CTRL3.STC -> 1)
        self._control_3(self_test=True)

        # Жду завершения внутренней процедуры
        sleep_ms(30)

        # Проверяю, что значение изменилось на _STB_TEST_SUCCESS_VALUE
        val = self._read_reg(_REG_ADDR_SELF_TEST_RESPONSE)[0]
        if val != _STB_TEST_SUCCESS_VALUE:
            # Сбрасываю флаг при ошибке, чтобы датчик не "завис" в режиме теста
            self._control_3(self_test=False)
            return False

        # Повторное чтение должно вернуть исходное 0x55
        # (чип Alps обычно сам сбрасывает флаг после успешного чтения 0xAA)
        val = self._read_reg(_REG_ADDR_SELF_TEST_RESPONSE)[0]

        # очищаю бит самопроверки
        self._control_3(self_test=False)
        return val == _STB_READY_VALUE


    def soft_reset(self):
        """Выполняет программный сброс датчика"""
        self._control_3(soft_reset=True)  # CTRL3.SRST -> 1

    def in_standby_mode(self) -> bool:
        """Возвращает Истина, когда датчик находится в состоянии stand by и Ложь, когда датчик включен!"""
        tmp = 0x80 & self._read_ctrl1()     # PC bit
        return 0 == tmp

    def is_data_ready(self) -> bool:
        """Возвращает флаг Data Ready (DRDY)"""
        return self.get_data_status(raw=False).DataReady

    def start_measurement(self):
        """Запускает процесс измерения на основе текущих настроек экземпляра.
        Это метод, который записывает конфигурацию (ODR, режим, диапазон)
        в аппаратные регистры датчика (CTRL1 и CTRL4).

        Все параметры берутся из полей:
        self._update_rate_index, self._continuous_mode, self._magnitude_range_index.
        Датчик переводится в активный режим (Active Mode)."""
        # Получаю сырые биты ODR (0, 1, 2 или 3)
        # на основе текущего состояния self._update_rate_index
        _, odr_bits = _ODR_MAPPING[self._update_rate_index]

        # Определяю режим: True = Force State (однократный), False = Normal State (непрерывный)
        # Метод _control_1 ожидает именно force_state (инверсия continuous_mode)
        force_state = not self._continuous_mode

        # Применяю конфигурацию CTRL1 (Питание=ВКЛ, Частота, Режим) одним вызовом
        # active_power_mode в True, так как это метод "запуска"
        self._control_1(
            active_power_mode=True,
            output_data_rate=odr_bits,
            force_state=force_state
        )

        # Применяю разрешение АЦП (Magnitude Range) через CTRL4
        # _RANGE_MAPPING возвращает (actual_idx, rs_bit). rs_bit = 1 для G2 (15-bit), 0 для G8 (14-bit)
        _, rs_bit = _RANGE_MAPPING[self._magnitude_range_index]
        hi_dynamic_range = (rs_bit == 1)

        self._control_4(hi_dynamic_range=hi_dynamic_range)

        # Если это однократное измерение (Force State), даю команду на старт через CTRL3
        if force_state:
            self._control_3(force_state=True)

    def enable_temp_meas(self, enable: bool = True):
        """управляет измерением температуры в активном режиме датчика"""
        self._control_3(temp_measure=enable)

    @property
    def offset_drift_values(self) -> tuple[int, int, int]:
        """Возвращает Offset Drift Values (OFFX, OFFY, OFFZ)"""
        return self._mag_field_offs[0], self._mag_field_offs[1], self._mag_field_offs[2]

    def set_offset_drift_values(self, offs_x: int = 0, offs_y: int = 0, offs_z: int = 0):
        """Запись значений смещений в аппаратные регистры датчика (OFFX, OFFY, OFFZ).
        Значения должны быть в диапазоне от -8192 до +8191 (14-битное знаковое целое)."""
        t = offs_x, offs_y, offs_z
        ba = self._buf_6
        valid_rng = range(-8192, 8192)
        for index, value in enumerate(t):
            check_value(value, valid_rng, f"Invalid offset value: {value}")
            b = (value & 0xFFFF).to_bytes(2, "little")
            indx = index << 1
            ba[indx] = b[0]
            ba[1 + indx] = b[1] & 0x7F
            # запись начиная с адреса _REG_ADDR_OFFS_X_LSB
        self._connection.write_buf_to_mem(_REG_ADDR_OFFS_X_LSB, ba)

    def calibrate_offsets(self):
        """
        Запускает аппаратную калибровку смещений (Offset Calibration Function).

        Вызывать только когда датчик находится в активном режиме (Active Mode).
        Внутренняя логика чипа самостоятельно измеряет текущее магнитное поле,
        вычисляет компенсационные значения и записывает их в аппаратные регистры
        смещений (OFFX, OFFY, OFFZ).

        По завершении процесса (бит OCL автоматически сбрасывается чипом в 0),
        новые значения считываются в локальный буфер self._mag_field_offs.
        """
        # Запускаем аппаратную калибровку (устанавливаем бит OCL=1 в регистре CTRL3)
        self._control_3(calibrate_offset=True)

        # Ожидаем завершения калибровки. Чип автоматически сбросит бит OCL (бит 0) в 0.
        while True:
            ctrl3_val = self._read_reg(_REG_ADDR_CTRL3)[0]
            if not (ctrl3_val & 0x01):  # Проверяем бит 0 (OCL)
                break
            sleep_ms(10)

        # Считываем вычисленные чипом значения смещений в локальный буфер
        self._read_field(offset=True)

    def __next__(self) -> None | MagnetometerData:
        """возвращает результат только в режиме периодических измерений!"""
        if self.is_continuously_mode() and self.is_data_ready():
            return self.get_measurement_value(AXIS_ALL)
        return None

    def get_measurement_value(self, value_index: int | None) -> None | int | float | MagnetometerData:
        """Возвращает измеренное датчиком значение(значения) по его индексу/номеру."""
        raw_mode = self.set_raw_mode()
        if AXIS_ALL != value_index:
            raw_field_comp : int = self._read_raw_field_comp(value_index)
            if raw_mode:
                return raw_field_comp
            multiplier = _get_multiplier()
            return multiplier * raw_field_comp

        #if AXIS_ALL == value_index:
        self._read_field()
        mag_fcomp = self._mag_field_comp
        _mul = 1 if raw_mode else _get_multiplier()
        return MagnetometerData(x=_mul*mag_fcomp[0], y=_mul*mag_fcomp[1], z=_mul*mag_fcomp[2], is_raw=raw_mode)


    def is_single_shot_mode(self) -> bool:
        """Возвращает Истина, когда датчик находится в режиме однократных измерений,
        каждое из которых запускается методом start_measurement"""
        tmp = 0x02 & self._read_ctrl1()  # FS bit. Force State
        return 0 != tmp

    def is_continuously_mode(self) -> bool:
        """Возвращает Истина, когда датчик находится в режиме многократных измерений,
        производимых автоматически. Процесс запускается методом start_measurement"""
        return not self.is_single_shot_mode()

    def set_raw_mode(self, value: bool | None = None) -> bool:
        """Устанавливает тип значения, возвращаемого методом get_measurement_value.
        Если value Истина, то get_measurement_value возвращает сырые безразмерные значения.
        Если value Ложь, то get_measurement_value возвращает значения в Гаусс.
        Значение используется методом start_measurement!
        Возвращает текущее значение типа значения, возвращаемого методом get_measurement_value.
        """
        if value is None:
            return self._raw_mode
        self._raw_mode = value
        return value

    def set_update_rate_index(self, index: int | None = None) -> int:
        """
        Устанавливает или возвращает индекс частоты обновления (ODR).
        Только обновляет внутреннюю переменную. Запись в регистры
        произойдет при вызове start_measurement().
        """
        if index is None:
            return self._update_rate_index

        if not (0 <= index < len(_ODR_MAPPING)):
            raise ValueError(f"Неподдерживаемый индекс частоты: {index}")

        # Сохраняю фактическое значение
        actual_odr, _ = _ODR_MAPPING[index]
        self._update_rate_index = actual_odr
        return actual_odr

    def set_continuous_mode(self, value: bool | None = None) -> bool:
        """
        Устанавливает режим измерений (Normal или Force State).
        Только обновляет внутреннюю переменную. Запись в регистры
        произойдет при вызове start_measurement().
        """
        if value is None:
            return self._continuous_mode

        self._continuous_mode = value
        return self._continuous_mode

    def set_magnitude_range_index(self, range_idx: int | None = None) -> int:
        """Устанавливает или возвращает индекс диапазона.
        Для HSCDTD008A это переключает разрешение АЦП (14 или 15 бит),
        так как физический диапазон фиксирован на ±2.4 mT (±24 Gauss)."""
        if range_idx is None:
            return self._magnitude_range_index

        # Проверка на допустимые значения
        if range_idx not in (MagRange.G2, MagRange.G8):
            raise ValueError(f"HSCDTD008A не поддерживает индекс диапазона: {range_idx}")

        # Получаю фактический индекс и бит для записи из кортежа
        actual_idx, _ = _RANGE_MAPPING[range_idx]
        self._magnitude_range_index = actual_idx
        return actual_idx

    def set_oversample_index(self, index: int | None = None) -> int:
        """Устанавливает или возвращает индекс уровня передискретизации (OSR).

        Для HSCDTD008A аппаратное усреднение не поддерживается (бит AVG в регистре
        CTRL2 должен оставаться 0 согласно даташиту).

        Этот метод просто запоминает запрошенный уровень, чтобы высокоуровневый код
        (например, цикл калибровки) мог использовать это значение для программного
        усреднения N последних измерений."""
        if index is None:
            return self._over_sample_index

        # Сохраняю значение для программного использования.
        # Аппаратно чип это не поддерживает, запись в регистр не производится.
        self._over_sample_index = index
        return index

    def set_performance_profile(self, profile: int | PerformanceProfile | None = None) -> PerformanceProfile:
        """Устанавливает или возвращает профиль производительности (ODR + OSR).

        Для HSCDTD008A:
        - ODR устанавливается аппаратно (с автоматическим округлением до поддерживаемых частот).
        - OSR не поддерживается аппаратно, но сохраняется для использования
          высокоуровневым кодом (например, для программного усреднения).

        :param profile: Индекс из PerformanceProfiles, именованный кортеж PerformanceProfile или None.
        :return: Именованный кортеж PerformanceProfile с фактически установленными значениями."""
        if profile is None:
            # Режим геттера: возвращаем текущие фактические настройки
            return PerformanceProfile(
                update_rate=self.set_update_rate_index(),
                oversample=self.set_oversample_index()
            )

        if isinstance(profile, int):
            # проверка границ
            check_value(profile, range(len(_PROFILE_MAP)), f"Invalid performance profile index: {profile}")

            # Получаю целевой профиль из _PROFILE_MAP
            target_profile = _PROFILE_MAP[profile]

            # Сохраняю индекс профиля для внутреннего состояния
            self._performance_profile = profile

        elif isinstance(profile, PerformanceProfile):
            # Пользователь передал кастомный(!) именованный кортеж
            target_profile = profile

            # Сохраняю кортеж для внутреннего состояния
            self._performance_profile = profile

        else:
            raise TypeError("profile должен быть int (PerformanceProfiles), PerformanceProfile или None")

        # Применяю настройки через спец. методы.
        actual_ur = self.set_update_rate_index(target_profile.update_rate)
        # set_oversample_index сохраняет значение для программного использования.
        actual_os = self.set_oversample_index(target_profile.oversample)

        # Возвращаю профиль с тем, что реально установлено/сохранено
        return PerformanceProfile(
            update_rate=actual_ur,
            oversample=actual_os
        )

    def refresh_config(self):
        """
        Считывает текущие значения настроек из аппаратных регистров датчика HSCDTD008A
        и синхронизирует с ними внутренние поля экземпляра класса.

        Используется после инициализации (POR) или для проверки реального состояния железа,
        гарантируя, что программное состояние (_update_rate_index, _continuous_mode и т.д.)
        всегда соответствует тому, что реально записано в чипе.
        """
        ctrl1 = self._read_ctrl1()

        # Биты 4:3: ODR (Output Data Rate)
        # Даташит: 00=0.5Hz, 01=10Hz, 10=20Hz, 11=100Hz
        odr_bits = (ctrl1 >> 3) & 0b11

        self._update_rate_index = _ODR_TO_RATE[odr_bits]

        # Бит 1: FS (State Control). 0 = Normal State (непрерывный), 1 = Force State (однократный)
        fs_bit = (ctrl1 >> 1) & 0b1
        # Если FS == 0 (Normal), то continuous_mode = True. Если FS == 1 (Force), то False.
        self._continuous_mode = (fs_bit == 0)

        # =========================================================================
        # Чтение Control 4 Register (CTRL4, адрес 0x1E)
        # =========================================================================
        ctrl4 = self._read_reg(_REG_ADDR_CTRL4)[0]

        # Бит 4: RS (Resolution Select). 0 = 14-bit, 1 = 15-bit
        rs_bit = (ctrl4 >> 4) & 0b1

        if 1 == rs_bit:
            # 15-bit режим (0.075 uT/LSB) -> на "высокоточный" диапазон G2
            self._magnitude_range_index = MagRange.G2
        else:
            # 14-bit режим (0.15 uT/LSB, по умолчанию) -> на диапазон G8
            self._magnitude_range_index = MagRange.G8

        # =========================================================================
        # Синхронизация OSR (Over Sample Rate)
        # =========================================================================
        # Поскольку HSCDTD008A не поддерживает аппаратное изменение OSR
        # (бит AVG в CTRL2 должен быть 0), оставляю программное значение
        # без изменений или сбрасываю его в безопасное значение по умолчанию,
        # чтобы код знал, что аппаратного усреднения нет.
        # self._over_sample_index = OversampleLevels.ULTRA_HIGH  # (опционально)
        pass

    def setup(self):
        """
        Выполняет базовую инициализацию вспомогательных функций датчика.

        Этот метод приводит датчик к безопасному базовому состоянию перед применением
        основной конфигурации:
        1. Очищает регистр действий (CTRL3), гарантируя отсутствие зависших
           процессов самопроверки (Self Test) или калибровки смещений.
        2. Отключает неиспользуемые функции (FIFO, вывод DRDY на физический пин)
           через CTRL2 для экономии энергии и предотвращения шумов.
        3. Явно отключает измерение температуры по умолчанию (можно включить
           позже через enable_temp_meas, если потребуется).

        Примечание: Основная конфигурация (ODR, режим Force/Normal, диапазон)
        НЕ меняется здесь. Она применяется позже через refresh_config()
        и start_measurement().
        """
        # Очистка регистра действий (CTRL3)
        # =========================================================================
        # Даташит предупреждает: "Bit control at the same time is prohibited".
        # Самый безопасный способ гарантировать, что не запущен Self Test,
        # калибровка или однократный замер — записать 0x00 во весь регистр.
        self._write_reg(_REG_ADDR_CTRL3, 0x00, 1)

        # Настройка вспомогательных функций (CTRL2)
        # =========================================================================
        # Отключаю FIFO (экономия энергии, упрощение логики)
        # Отключаю вывод сигнала DRDY на физический пин (использую polling
        # через чтение регистра STAT, что надежнее при отсутствии прерываний)
        self._control_2(
            fifo_enable=False,
            den=False  # Data Ready Function Control Enable (на пин)
        )

        # Состояние измерения температуры
        # =========================================================================
        self.enable_temp_meas(True)