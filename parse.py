#! /usr/bin/env python3

from construct import *
import construct
import sys


def get_grammar():
    pass_fail = Enum(Byte, pass_=1, fail=2)
    record_type = Enum(Byte, test=0x01, end=0xaa)

    test_result = Struct(
        start=Const(b'\xfd'),
        name=String(16),
        units=String(16),
        value=Int16ub,
        flag=Flag,
    )
    test_record = Struct(
        success=pass_fail,
        id_=String(16),
        zeros=Const(b'\x00')[64],
        venue=String(16),
        location=String(16),
        unknown1=String(5),
        seven=Const(b'\xe0\x07'),
        user=String(16),
        comments=String(128),
        unknown2=String(1),
        period1=Int8ul,
        test_type=String(30),
        period2=Int8ul,
        unknown3=String(15),
        unknown4=RawCopy(PascalString(Int8ul)),
        start_results=Const(b'\xfe'),
        results=RawCopy(test_result[:]),
        unknown5=Byte[this._.length - this.unknown4.length - this.results.length - 314],
    )
    final_record = Struct(
    )
    record = Struct(
        start=Const(b'\xff\x54'),
        length=Int16ul,
        checksum=Int16ul,
        zeros=Const(b'\x00\x00'),
        record_type=record_type,
        data=Embedded(Switch(this.record_type, {
            'test': test_record,
            'end': final_record,
        })),
    )
    pat_file = Struct(
        unknown1=Const(b'\x54\x2a\x00\x28\x06\x00\x00\x55'),
        machine=String(20),
        serial=String(20),
        records=record[:],
        eof=Const(b'\xff'),
    )

    return pat_file


def main():
    grammar = get_grammar()

    with open(sys.argv[1], 'rb') as f:
        result = grammar.parse(f.read())
        print(result)

if __name__ == '__main__':
    main()
