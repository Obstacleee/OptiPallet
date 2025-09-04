# Fichier: sender.py
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder
from pymodbus.constants import Endian


class ModbusSender:
    def __init__(self, config):
        self.config = config['plc']
        self.addresses = config['modbus_addresses']
        self.client = ModbusTcpClient(host=self.config['ip'], port=self.config['port'])
        self.byteorder = Endian.Big if self.config['byte_order'] == 'Big' else Endian.Little
        self.wordorder = Endian.Little if self.config['word_order'] == 'Little' else Endian.Big

    def connect(self):
        return self.client.connect()

    def disconnect(self):
        self.client.close()

    def is_connected(self):
        return self.client.is_socket_open()

    def read_32bit_int(self, address):
        try:
            rr = self.client.read_holding_registers(address, 2, unit=self.config['unit_id'])
            if rr.isError(): return None
            decoder = BinaryPayloadDecoder.fromRegisters(rr.registers, byteorder=self.byteorder,
                                                         wordorder=self.wordorder)
            return decoder.decode_32bit_int()
        except Exception:
            return None


    def write_32bit_int(self, address, value):
        try:
            builder = BinaryPayloadBuilder(byteorder=self.byteorder, wordorder=self.wordorder)
            builder.add_32bit_int(value)
            payload = builder.to_registers()
            self.client.write_registers(address, payload, unit=self.config['unit_id'])
            return True
        except Exception as e:
            print(f"  ❌ Erreur d'écriture 32 bits : {e}")
            return False

    def read_dimensions(self):
        try:
            rr = self.client.read_holding_registers(self.addresses['box_l'], 10,
                                                    unit=self.config['unit_id'])  # 5 floats = 10 registres
            if rr.isError(): return None
            decoder = BinaryPayloadDecoder.fromRegisters(rr.registers, byteorder=self.byteorder,
                                                         wordorder=self.wordorder)
            dims = {
                "box_dims": {
                    "l": int(decoder.decode_32bit_float()),
                    "w": int(decoder.decode_32bit_float()),
                    "h": int(decoder.decode_32bit_float())
                },
                "pallet_dims": {
                    "L": int(decoder.decode_32bit_float()),
                    "W": int(decoder.decode_32bit_float())
                }
            }
            return dims
        except Exception:
            return None

    def send_template(self, template):
        print("  Envoi des données du template à l'automate...")
        self._send_layer(template['layer1'], self.addresses['layer1_start'])
        self._send_layer(template['layer2'], self.addresses['layer2_start'])
        print("  ✅ Données envoyées.")

    def _send_layer(self, layer_data, start_address):
        builder = BinaryPayloadBuilder(byteorder=self.byteorder, wordorder=self.wordorder)
        for box in layer_data:
            builder.add_32bit_float(float(box['x']))
            builder.add_32bit_float(float(box['y']))
            builder.add_32bit_float(float(box['rotation']))
            builder.add_32bit_float(float(box['label_face']))

        registers_used = len(layer_data) * 4 * 2
        registers_to_pad = 200 - registers_used
        if registers_to_pad > 0:
            for _ in range(registers_to_pad // 2):
                builder.add_32bit_float(9999.99)

        payload = builder.to_registers()
        for i in range(0, len(payload), 100):
            chunk = payload[i:i + 100]
            self.client.write_registers(start_address + i, chunk, unit=self.config['unit_id'])