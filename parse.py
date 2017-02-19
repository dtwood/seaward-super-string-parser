#! /usr/bin/env python3

from construct import *

import codecs
import datetime
import gar
import sys


def trace(x):
    print(x)
    return x


class CustomFloat16(Adapter):
    def __init__(self, units, *args, **kwargs):
        self.units = units

        f = ByteSwapped(Bitwise(Struct(
            exponent=BitsInteger(2),
            significand=BitsInteger(14),
        )))
        super().__init__(f, *args, **kwargs)

    def _decode(self, obj, context):
        return {
            'value': obj['significand'] * (0.1 ** obj['exponent']),
            'units': self.units,
        }


result_flags = Bitwise(Struct(
    'unknown1' / Flag,
    'unknown2' / Flag,
    'greater_than' / Flag,
    'less_than' / Flag,
    'unknown3' / Flag,
    'unknown4' / Flag,
    'fail' / Flag,
    'pass' / Flag,
))


physical_test_type = Enum(
    Byte,
    earth_resistance=0x11,
    iec=0x16,
    insulation=0x20,
    substitute_leakage=0x83,
    polarity=0x91,
    mains_voltage=0x92,
    touch_or_leakage_current=0x96,
    rcd=0x9a,
    string=0xfd,
)

earth_resistance = Struct(
    'resistance' / CustomFloat16('ohm'),
    'result' / result_flags,
)
iec = Struct(
    'resistance' / CustomFloat16('ohm'),
    'result' / result_flags,
)
insulation = Struct(
    'voltage' / CustomFloat16('volt'),
    'resistance' / CustomFloat16('megaohm'),
    'result' / result_flags,
)
substitute_leakage = Struct(
    'current' / CustomFloat16('milliamp'),
    'result' / result_flags,
)
polarity = Struct(
    'result' / result_flags,
)
mains_voltage = Struct(
    'voltage' / CustomFloat16('volt'),
    'result' / result_flags,
)
touch_or_leakage_current = Struct(
    'load_current' / CustomFloat16('milliamp'),
    'unknown' / Bytes(2),
    'leakage_current' / CustomFloat16('milliamp'),
    'result' / result_flags,
)
rcd = Struct(
    'test_current' / CustomFloat16('milliamp'),
    'cycle_angle' / CustomFloat16('degree'),
    'trip_time' / CustomFloat16('millisecond'),
    'result' / result_flags,
)
string = Struct(
    'value' / String(34),
    'result' / result_flags,
)

physical_test_result = Struct(
    'ty' / physical_test_type,
    'value' / Switch(
        this.ty,
        {
            'earth_resistance': earth_resistance,
            'iec': iec,
            'insulation': insulation,
            'substitute_leakage': substitute_leakage,
            'polarity': polarity,
            'mains_voltage': mains_voltage,
            'touch_or_leakage_current': touch_or_leakage_current,
            'rcd': rcd,
            'string': string,
        }
    ),
)
visual_test_result = Struct(
    'start' / Const(b'\xfd'),
    'name' / String(16),
    'units' / String(16),
    'value' / Int16ul,
    'flag' / Flag,
)

record_type = Enum(Byte, test=0x01, end=0xaa, machine_info=0x55)
machine_info_record = Struct(
    'machine' / String(20),
    'serial' / String(20),
    Const(b'\xff'),
)
test_record = Struct(
    'result' / result_flags,
    'id' / String(16, encoding='utf-8'),
    Const(b'\x00')[64],
    'venue' / String(16, encoding='utf-8'),
    'location' / String(16, encoding='utf-8'),
    'hour' / Int8ul,
    'minute' / Int8ul,
    'second' / Int8ul,
    'day' / Int8ul,
    'month' / Int8ul,
    'year' / Int16ul,
    'user' / String(16, encoding='utf-8'),
    'comments' / String(128, encoding='utf-8'),
    Const(b'\x02'),
    'full_retest_period' / Int8ul,
    'test_type' / String(30, encoding='utf-8'),
    'visual_retest_period' / Int8ul,
    String(15),
    'test_config' / Hex(PascalString(Int8ul)),
    Const(b'\xfe'),
    'visual_test_results' / visual_test_result[:],
    'physical_test_results' / physical_test_result[:],
    Const(b'\xff'),
)
final_record = Struct(
    Const(b'\xff'),
)
record = Struct(
    'start' / Const(b'\x54'),
    'length' / Int16ul,
    'checksum' / Int16ul,
    Const(b'\x00\x00'),
    'record_type' / RawCopy(record_type),
    'data' / RawCopy(Switch(
        this.record_type.value, {
            'machine_info': machine_info_record,
            'test': test_record,
            'end': final_record,
        }
    )),
    Check(
        (sum_(this.record_type.data + this.data.data) & 0xffff ==
            this.checksum) |
        (sum_(this.record_type.data + this.data.data) & 0xffff ==
            this.checksum + 1)
    ),
)

pat_file = Struct(
    'records' / record[:],
    ExprValidator(Peek(Int8ul), lambda obj, ctx: obj is None)
)


def get_results(data):
    extracted_gar = gar.get_gar_contents(data)
    result = pat_file.parse(extracted_gar['TestResults.sss'])
    del extracted_gar['TestResults.sss']

    return {
        'results': [
            {
                'id': record.data.value['id'],
                'venue': record.data.value.venue,
                'location': record.data.value.location,
                'visual_retest_period': datetime.timedelta(
                    days=record.data.value.visual_retest_period * 30),
                'full_retest_period': datetime.timedelta(
                    days=record.data.value.full_retest_period * 30),
                'test_time': datetime.datetime(
                    year=record.data.value.year,
                    month=record.data.value.month,
                    day=record.data.value.day,
                    hour=record.data.value.hour,
                    minute=record.data.value.minute,
                    second=record.data.value.second,
                ),
                'test_type': record.data.value.test_type,
                'comments': record.data.value.comments,
                'subtests': [
                    {
                        'test_type': 'visual',
                        'result': {
                            'pass':
                            record.data.value.result['pass'] or
                            len(record.data.value.physical_test_results) != 0,
                            'fail':
                            record.data.value.result.fail and
                            len(record.data.value.physical_test_results) == 0
                        }
                    }
                ] + [
                    {
                        'test_type': result.ty,
                        **result.value
                    }
                    for result in record.data.value.physical_test_results
                ],
                'result': record.data.value.result,
                'test_config': record.data.value.test_config,
            }
            for record in result.records
            if record.record_type.value == 'test'
        ],
        'images': extracted_gar,
    }


def main():
    try:
        f = sys.argv[1]
    except IndexError:
        f = "ApolloDownload.gar"

    with open(f, 'rb') as f:
        output = get_results(f.read())

    output['results'].sort(key=lambda result: result['test_time'])

    import pprint
    pprint.pprint(output)


if __name__ == '__main__':
    main()
