#! /usr/bin/env python3

from construct import *
import construct
import sys


def get_grammar():
    pass_fail = Enum(Byte, fail=1, pass_=2)
    test_result = Struct(
        start = Const(b'\xfd'),
        name = String(16),
        units = String(16),
        value = Int16ub,
        flag = Flag,
    )
    test_record = Struct(
        record_type = Const(b'\x01'),
        unknown = pass_fail,
        id_ = String(80),
        venue = String(16),
        location = String(16),
        unknown4 = String(7),
        user = String(16),
        comments = String(128),
        unknown5 = String(1),
        date1 = Int8ul,
        test_type = String(30),
        date2 = Int8ul,
        unknown6 = String(15),
        unknown7 = RawCopy(PascalString(Int8ul)),
        start_results = Const(b'\xfe'),
        results = RawCopy(test_result[:]),
        unknown8 = RawCopy(Byte[this._.length - this.unknown7.length - this.results.length - 314]),
    )
    final_record = Struct(
        record_type = Const(b'\xaa'),
    )
    record = RawCopy(Struct (
        start = Const(b'\xff\x54'),
        length = Int16ul,
        checksum = Int16ul,
        zeros = Const(b'\x00\x00'),
        data = RawCopy(Select(test_record, final_record)),
    ))
    pat_file = Struct(
        unknown1 = Const(b'\x54\x2a\x00\x28\x06\x00\x00\x55'),
        machine = String(20),
        serial = String(20),
        records = record[:],
        eof = Const(b'\xff'),
    )

    return pat_file


def main():
    grammar = get_grammar()

    with open(sys.argv[1], 'rb') as f:
        result = grammar.parse(f.read())
        print(result)

if __name__ == '__main__':
    main()
