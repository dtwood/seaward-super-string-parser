#! /usr/bin/env python3

# Paul Sladen, 2014-12-04, Seaward GAR PAT testing file format debug harness
# Hereby placed in the public domain in the hopes of improving
# electrical safety and interoperability.

'''
== GAR ==
GAR files are a container format used for importing/exporting filesets to and
from some Seaward PAT testing machines ("Apollo" series?). As of 2014-12-05 I
have seen three examples of '.GAR' files; one purporting to contain an .SSS
file and a selection of JPEGs and two purporting to contain just an .SSS file.

== File Header ==
There is a single file-header that begins 0xcabcab (CAB CAB; cabinet?) for
magic/identification purposes, followed by single byte version number.  There
is no-end of file marker or overall checksum.

== Archive records ==
Each file stored within the GAR container is prefixed by:
    1. a record header giving the overall size of the record;
    2. a variable length human-readable string (aka the filename);
    3. a truncated monotonically-increasing semi-timestamp;
    4. the original pre-compression length.
    5. original length (little-endian, four octets)
    6. compressed contents (zlib)

== Compression ==
Compression is Deflate (as used in zipfiles and PNG images), wrapped with zlib
headers and footers.  This reduces the largely fixed-field .SSS files to ~10%
of their input size, while the already-compressed JPEG files remain ~99% of
their input size.  Each file's payload is compressed separately.

== Deflate ==
The `QByteArray::qCompress()` convention is used, which prepends an extra
four-byte header containing an additional little-endian uncompressed stream
size, then continues with the usual two-byte zlib header, deflate stream, and
four-byte zlib footer: [1].

As the contained files are likely to be under 65k in length, the first 2 bytes
of the original length are nulls, which proved to be a handy plaintext and
sanity check for the next step. :-D

There appear to be some people at Seaward posting patches to Qt [2] so I expect
the added qCompress length prefix is probably simply as a result of using Qt
somewhere, rather than an active choice.

[1]: http://ehc.ac/p/ctypes/mailman/message/23484411/
[2]: http://patchwork.openembedded.org/patch/80259/mbox/

== Obfuscation ==
The qCompress (with length prefix)-style Deflate/zlib streams are perturbed
additively (meaning bytewise ADD/SUB, not XOR) with the bottom 8-bits from
Marsaglia xorshift PNR, seeded from the pseudo-timestamp and payload length of
the corresponding file.

Xorshift uses 128-bits (four * 32-bit words) for state `(x, y, z, w)`, and the
standard default seeds are used for initialisation for `z` and `w` while, `x`
and `y` are seeded from truncated timestamp and from the original file-length.
The give-away for spotting xorshift is that the first round output depends
solely upon the `x` and `w` inputs, enabling confirmation of `x` (== timestamp)
independent to confirmation of `y` (== original file length).

== Integrity checking ==
Aside from failing to decode/validate, the zlib checksum provides the only
defacto integrity checking in the GAR file-format.
'''

from construct import *
from my_restreamed import MyRestreamed

import io
import struct
import zlib


def marsaglia_xorshift_128(x=123456789, y=362436069, z=521288629, w=88675123):
    '''
    Marsaglia xorshift, using default parameters
    https://en.wikipedia.org/wiki/Xorshift
    http://stackoverflow.com/questions/4508043/on-xorshift-random-number-generator-algorithm
    '''

    while True:
        t = (x ^ (x << 11)) & 0xffffffff
        x, y, z = y, z, w
        w = (w ^ (w >> 19) ^ (t ^ (t >> 8)))
        yield w


def deobfuscate_string(pnr, obfuscated, operation=int.__sub__):
    '''
    The lower 8-bits from the Xorshift PNR are subtracted from byte values
    during extraction, and added to byte values on insertion.  When calling
    deobfuscate_string() the whole string is processed.
    '''

    return bytes(
        operation(c, r) & 0xff
        for (c, r) in zip(obfuscated, pnr)
    )


subfile_contents_contents = Struct(
    expected_length=Int32ub,
    contents=Compressed(GreedyBytes, 'zlib'),
)

subfile_contents = Struct(
    header_length=Const(b'\x00\x0c'),
    mangling_method=Const(b'\x00\x01'),
    truncated_timestamp=Int32ub,
    original_length=Int32ub,
    _pnr=Computed(lambda obj: marsaglia_xorshift_128(
        x=obj.truncated_timestamp,
        y=obj.original_length
    )),
    _=Embedded(MyRestreamed(
        subfile_contents_contents,
        encoder=lambda d, ctx: deobfuscate_string(ctx._pnr, d, int.__add__),
        decoder=lambda d, ctx: deobfuscate_string(ctx._pnr, d),
        encoderunit=1,
        decoderunit=1,
        sizecomputer=lambda x: x,
    )),
)

subfile = Struct(
    filename=PascalString(Int32ub, encoding='utf-8'),
    compressed_length=Peek(Int32ub),
    _=Embedded(Prefixed(Int32ub, subfile_contents)),
)

gar_file = Struct(
    magic=Const(b'\xca\xbc\xab'),
    version=Const(b'\x01'),
    files=subfile[1],
)


def get_gar_contents(container):
    return {
        f.filename: f.contents
        for f in gar_file.parse(container).files
    }
