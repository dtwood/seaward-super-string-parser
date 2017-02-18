import construct


class MyRestreamedBytesIO(construct.RestreamedBytesIO):
    def read(self, count=None):
        if count is None:
            srw = 0
            rdata = b''
            while True:
                if self.decoderunit is None:
                    data = self.substream.read()
                else:
                    data = self.substream.read(self.decoderunit)
                if data is None or len(data) == 0:
                    break
                srw += len(data)
                rdata += self.decoder(data, self.context)
            self.sincereadwritten += srw
            return rdata
        elif count < 0:
            raise ValueError("count cannot be negative")
        else:
            while len(self.rbuffer) < count:
                if self.decoderunit is None:
                    data = self.substream.read(count)
                else:
                    data = self.substream.read(self.decoderunit)
                if data is None or len(data) == 0:
                    raise IOError(
                        "Restreamed cannot satisfy read request of %d bytes" %
                        count
                    )
                self.rbuffer += self.decoder(data, self.context)
            data, self.rbuffer = self.rbuffer[:count], self.rbuffer[count:]
            self.sincereadwritten += count
            return data

    def write(self, data):
        self.wbuffer += data
        datalen = len(data)
        while len(self.wbuffer) >= self.encoderunit:
            data, self.wbuffer = self.wbuffer[:self.encoderunit], \
                self.wbuffer[self.encoderunit:]
            self.substream.write(self.encoder(data, self.context))
        self.sincereadwritten += datalen
        return datalen


class MyRestreamed(construct.Restreamed):
    def __init__(self, subcon, encoder, encoderunit, decoder, decoderunit,
                 sizecomputer):
        super().__init__(subcon, encoder, encoderunit, decoder, decoderunit,
                         sizecomputer)
        self.stream2 = MyRestreamedBytesIO(None, encoder, encoderunit, decoder,
                                           decoderunit)

    def _parse(self, stream, context, path):
        self.stream2.substream = stream
        self.stream2.context = context
        obj = self.subcon._parse(self.stream2, context, path)
        self.stream2.close()
        return obj

    def _build(self, obj, stream, context, path):
        self.stream2.substream = stream
        self.stream2.context = context
        buildret = self.subcon._build(obj, self.stream2, context, path)
        self.stream2.close()
        return buildret
