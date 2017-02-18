import construct


class MyRestreamedBytesIO(construct.RestreamedBytesIO):
    def read(self, count=None):
        if count is None:
            srw = 0
            rdata = b''
            while True:
                data = self.substream.read(self.decoderunit)
                if data is None or len(data) == 0:
                    break
                srw += len(data)
                rdata += self.decoder(data)
            self.sincereadwritten += srw
            return rdata
        else:
            if count < 0:
                raise ValueError("count cannot be negative")
            while len(self.rbuffer) < count:
                data = self.substream.read(self.decoderunit)
                if data is None or len(data) == 0:
                    raise IOError(
                        "Restreamed cannot satisfy read request of %d bytes" %
                        count
                    )
                self.rbuffer += self.decoder(data)
            data, self.rbuffer = self.rbuffer[:count], self.rbuffer[count:]
            self.sincereadwritten += count
            return data


class MyRestreamed(construct.Restreamed):
    def __init__(self, subcon, encoder, encoderunit, decoder, decoderunit,
                 sizecomputer):
        super().__init__(subcon, encoder, encoderunit, decoder, decoderunit,
                         sizecomputer)
        self.stream2 = MyRestreamedBytesIO(None, encoder, encoderunit, decoder,
                                           decoderunit)
