#ifndef BOOT_ANIM_PLAYER_H
#define BOOT_ANIM_PLAYER_H

#include <Arduino.h>
#include <SPIFFS.h>
#include <rom/miniz.h>

#define ANIM_MAGIC      0x54423352  // 'R4BT' little-endian
#define ANIM_FILE       "/boot_anim.bin"
#define ANIM_FRAME_BUF  (128 * 160 * 2)

struct AnimHeader {
    char     magic[4];
    uint8_t  version;
    uint16_t width;
    uint16_t height;
    uint8_t  fps;
    uint16_t totalFrames;
    uint32_t frameSize;
    uint32_t compressedSize;
} __attribute__((packed));

class BootAnimPlayer {
public:
    bool begin(const char* path = ANIM_FILE) {
        Serial.printf("[BootAnim] Opening %s...\n", path);
        _file = SPIFFS.open(path, "r");
        if (!_file) {
            Serial.println("[BootAnim] File not found in SPIFFS!");
            return false;
        }

        AnimHeader hdr;
        if (_file.read((uint8_t*)&hdr, sizeof(hdr)) != sizeof(hdr)) {
            Serial.println("[BootAnim] Failed to read header (file too small).");
            _file.close();
            return false;
        }

        if (memcmp(hdr.magic, "R4BT", 4) != 0) {
            _file.close();
            return false;
        }

        _width       = hdr.width;
        _height      = hdr.height;
        _fps         = hdr.fps;
        _totalFrames = hdr.totalFrames;
        _frameSize   = hdr.frameSize;
        _compSize    = hdr.compressedSize;
        _dataOffset  = _file.position();
        _currentFrame = 0;

        _dictBuf = (uint8_t*)malloc(32768);
        _inBuf   = (uint8_t*)malloc(4096);
        _inflator= (tinfl_decompressor*)calloc(1, sizeof(tinfl_decompressor));

        if (!_dictBuf || !_inBuf || !_inflator) {
            if (_dictBuf) free(_dictBuf); 
            if (_inBuf)  free(_inBuf);
            if (_inflator) free(_inflator);
            _file.close();
            return false;
        }

        reset(nullptr);
        return true;
    }

    uint16_t getWidth()       { return _width; }
    uint16_t getHeight()      { return _height; }
    uint8_t  getFps()         { return _fps; }
    uint16_t getTotalFrames() { return _totalFrames; }
    uint32_t getFrameIntervalMs() { return 1000 / _fps; }

    bool decodeNextFrame(uint16_t* displayBuf) {
        if (_currentFrame >= _totalFrames) {
            reset(displayBuf);
        }

        if (_currentFrame == 0 && displayBuf) {
            memset(displayBuf, 0, _frameSize);
        }

        uint8_t* dst = (uint8_t*)displayBuf;
        size_t frameBytesDone = 0;

        while (frameBytesDone < _frameSize) {
            // Consume existing unread bytes first
            size_t available = 0;
            if (_dictWritePos >= _dictReadPos) {
                available = _dictWritePos - _dictReadPos;
            } else {
                available = 32768 - _dictReadPos; // Read up to wrap
            }

            if (available > 0) {
                size_t to_consume = available;
                if (to_consume > (_frameSize - frameBytesDone)) {
                    to_consume = _frameSize - frameBytesDone;
                }

                for (size_t i = 0; i < to_consume; i++) {
                    dst[frameBytesDone + i] ^= _dictBuf[_dictReadPos + i];
                }

                _dictReadPos += to_consume;
                if (_dictReadPos >= 32768) _dictReadPos = 0;
                frameBytesDone += to_consume;

                if (frameBytesDone == _frameSize) {
                    break;
                }
            }

            // Need more data, decompress
            if (_inBufPos == _inBufLen && !_eof) {
                _inBufLen = _file.read(_inBuf, 4096);
                _inBufPos = 0;
                if (_inBufLen == 0) _eof = true;
            }

            size_t in_bytes = _inBufLen - _inBufPos;
            size_t out_bytes = 32768 - _dictWritePos; // MUST be the exact distance to wrap!

            mz_uint32 flags = TINFL_FLAG_PARSE_ZLIB_HEADER;
            if (!_eof) flags |= TINFL_FLAG_HAS_MORE_INPUT;

            tinfl_status status = tinfl_decompress(
                _inflator,
                _inBuf + _inBufPos, &in_bytes,
                _dictBuf, _dictBuf + _dictWritePos, &out_bytes,
                flags
            );

            _inBufPos += in_bytes;
            _dictWritePos += out_bytes;
            if (_dictWritePos >= 32768) _dictWritePos = 0;

            if (status <= TINFL_STATUS_DONE) {
                // If we finished decompressing but the frame is incomplete
                if (frameBytesDone < _frameSize && _dictReadPos == _dictWritePos) {
                    return false;
                }
                if (_dictReadPos == _dictWritePos) {
                    break; // EOF reached and consumed
                }
            }
        }

        _currentFrame++;
        return true;
    }

    void reset(uint16_t* displayBuf) {
        _currentFrame = 0;
        if (_file) _file.seek(_dataOffset);
        if (_inflator) {
            memset(_inflator, 0, sizeof(tinfl_decompressor));
            tinfl_init(_inflator);
        }
        _dictWritePos = 0;
        _dictReadPos = 0;
        _inBufPos = 0;
        _inBufLen = 0;
        _eof = false;
        if (displayBuf) memset(displayBuf, 0, _frameSize);
    }

    void end() {
        if (_dictBuf) free(_dictBuf);
        if (_inBuf)  free(_inBuf);
        if (_inflator) free(_inflator);
        _dictBuf = nullptr;
        _inBuf  = nullptr;
        _inflator = nullptr;
        if (_file) _file.close();
    }

private:
    File      _file;
    uint16_t  _width;
    uint16_t  _height;
    uint8_t   _fps;
    uint16_t  _totalFrames;
    uint32_t  _frameSize;
    uint32_t  _compSize;
    uint32_t  _dataOffset;
    uint16_t  _currentFrame;

    tinfl_decompressor* _inflator;
    uint8_t* _dictBuf;
    uint8_t* _inBuf;
    size_t   _dictWritePos;
    size_t   _dictReadPos;
    size_t   _inBufPos;
    size_t   _inBufLen;
    bool     _eof;
};

#endif
