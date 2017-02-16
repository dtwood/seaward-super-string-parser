#! /usr/bin/env python3

from construct import *
import codecs
import datetime
import sys
import gar


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


@singleton
class ResultFlags(Adapter):
    def __init__(self, *args, **kwargs):
        f = Bitwise(Struct(
            unknown1=Flag,
            unknown2=Flag,
            greater_than=Flag,
            less_than=Flag,
            unknown3=Flag,
            unknown4=Flag,
            unknown5=Flag,
            pass_=Flag,
        ))
        super().__init__(f, *args, **kwargs)

    def _decode(self, obj, context):
        return obj


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
    resistance=CustomFloat16('ohm'),
    result=ResultFlags,
)
iec = Struct(
    resistance=CustomFloat16('ohm'),
    result=ResultFlags,
)
insulation = Struct(
    voltage=CustomFloat16('volt'),
    resistance=CustomFloat16('megaohm'),
    result=ResultFlags,
)
substitute_leakage = Struct(
    current=CustomFloat16('milliamp'),
    result=ResultFlags,
)
polarity = Struct(
    result=ResultFlags,
)
mains_voltage = Struct(
    voltage=CustomFloat16('volt'),
    result=ResultFlags,
)
touch_or_leakage_current = Struct(
    load_current=CustomFloat16('milliamp'),
    unknown=Bytes(2),
    leakage_current=CustomFloat16('milliamp'),
    result=ResultFlags,
)
rcd = Struct(
    test_current=CustomFloat16('milliamp'),
    cycle_angle=CustomFloat16('degree'),
    trip_time=CustomFloat16('millisecond'),
    result=ResultFlags,
)
string = Struct(
    value=String(34),
    result=ResultFlags,
)

physical_test_result = Struct(
    ty=physical_test_type,
    value=Switch(
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
    start=Const(b'\xfd'),
    name=String(16),
    units=String(16),
    value=Int16ul,
    flag=Flag,
)

record_type = Enum(Byte, test=0x01, end=0xaa, machine_info=0x55)
machine_info_record = Struct(
    machine=String(20),
    serial=String(20),
)
test_record = Struct(
    success=ResultFlags,
    id_=String(16),
    zeros=Const(b'\x00')[64],
    venue=String(16),
    location=String(16),
    hour=Int8ul,
    minute=Int8ul,
    second=Int8ul,
    day=Int8ul,
    month=Int8ul,
    year=Int16ul,
    user=String(16),
    comments=String(128),
    unknown1=Const(b'\x02'),
    full_retest_period=Int8ul,
    test_type=String(30),
    visual_retest_period=Int8ul,
    almost_always_nulls=String(15),
    test_config=PascalString(Int8ul),
    start_results=Const(b'\xfe'),
    visual_test_results=visual_test_result[:],
    physical_test_results=physical_test_result[:],
)
final_record = Struct(
)
record = Struct(
    start=Const(b'\x54'),
    length=Int16ul,
    checksum=Int16ul,
    zeros=Const(b'\x00\x00'),
    record_type=RawCopy(record_type),
    data=RawCopy(Switch(this.record_type.value, {
        'machine_info': machine_info_record,
        'test': test_record,
        'end': final_record,
    })),
    end=Const(b'\xff'),
    checksum_computed=Computed(
        sum_(this.record_type.data + this.data.data + this.end) &
        0xffff
    )
)

pat_file = Struct(
    records=record[:],
)


def get_results(data):
    extracted_gar = gar.get_gar_contents(data)
    result = pat_file.parse(extracted_gar['TestResults.sss'])
    del extracted_gar['TestResults.sss']

    assert(result.records[-1].record_type.value == 'end')
    for record in result.records:
        assert(record.checksum == record.checksum_computed or
               record.checksum == record.checksum_computed - 1)

    return {
        'results': [
            {
                'id': record.data.value.id_.decode("utf-8"),
                'venue': record.data.value.venue.decode("utf-8"),
                'location': record.data.value.location.decode("utf-8"),
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
                'test_type': record.data.value.test_type.decode('utf-8'),
                'comments': record.data.value.comments.decode('utf-8'),
                'subtests': [
                    {
                        'test_type': 'visual',
                        'result': {
                            'pass_':
                            record.data.value.success.pass_ or
                            len(record.data.value.physical_test_results) != 0
                        }
                    }
                ] + [
                    {
                        'test_type': result.ty,
                        **result.value
                    }
                    for result in record.data.value.physical_test_results
                ],
                'result': record.data.value.success.pass_,
                'test_config': codecs.encode(
                    record.data.value.test_config,
                    encoding='hex_codec'
                )
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
