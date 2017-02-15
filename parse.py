#! /usr/bin/env python3

from construct import *
import sys


def get_grammar():
    pass_fail = Enum(Byte, pass_=1, fail=2)
    record_type = Enum(Byte, test=0x01, end=0xaa, machine_info=0x55)

    machine_info_record = Struct(
        machine=String(20),
        serial=String(20),
    )
    test_result = Struct(
        start=Const(b'\xfd'),
        name=String(16),
        units=String(16),
        value=Int16ul,
        flag=Flag,
    )
    test_record = Struct(
        success=pass_fail,
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
        unknown2=Const(b'\x02'),
        full_retest_period=Int8ul,
        test_type=String(30),
        visual_retest_period=Int8ul,
        unknown3=String(15),
        unknown4=RawCopy(PascalString(Int8ul)),
        start_results=Const(b'\xfe'),
        results=RawCopy(test_result[:]),
        unknown5=Bytes(this._.length - this.unknown4.length - this.results.length - 314),
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
        checksum_computed=Computed(sum_(this.record_type.data + this.data.data + this.end) & 0xffff)
    )
    pat_file = Struct(
        records=record[:],
    )

    return pat_file


def main():
    grammar = get_grammar()

    with open(sys.argv[1], 'rb') as f:
        result = grammar.parse(f.read())

    assert(result.records[-1].record_type.value == 'end')
    for record in result.records:
        assert(record.checksum == record.checksum_computed or
               record.checksum == record.checksum_computed - 1)

    import pprint
    import datetime

    filtered = [record for record in result.records if record.record_type.data == b'\x01']
    output = [{
        'id': record.data.value.id_.decode("utf-8"),
        'venue': record.data.value.venue.decode("utf-8"),
        'location': record.data.value.location.decode("utf-8"),
        'visual_retest_period': record.data.value.visual_retest_period,
        'full_retest_period': record.data.value.full_retest_period,
        'test_time':  datetime.datetime(
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
                'test_type': 'historical',
                'result': 'pass' if record.data.value.success == 'pass_' else 'fail',
            }
        ],
    } for record in filtered if record.data.value.id_ == b'dt6']
    pprint.pprint(output)

if __name__ == '__main__':
    main()
