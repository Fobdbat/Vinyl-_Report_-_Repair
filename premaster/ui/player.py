# -*- coding: utf-8 -*-
"""Reproductor A/B: original i reparat sincronitzats; el canvi A/B és instantani i manté la posició."""
import threading

import numpy as np

try:
    import sounddevice as sd
    AVAILABLE = True
    ERROR = ""
except Exception as exc:  # PortAudio no disponible
    sd = None
    AVAILABLE = False
    ERROR = str(exc)

PREVIEW_FS = 48000


def _stereo32(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return np.ascontiguousarray(x[:, :2])


class ABPlayer(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.stream = None
        self.a = None
        self.b = None
        self.fs = 44100
        self.pos = 0
        self.which = "A"
        self.gain_a = 1.0
        self.gain_b = 1.0
        self.match = False
        self.match_a = 1.0
        self.match_b = 1.0
        self.playing = False

    @property
    def length(self):
        if self.a is None:
            return 0
        return max(len(self.a), len(self.b) if self.b is not None else 0)

    def load(self, a, b, fs, lufs_a=None, lufs_b=None):
        """a, b: arrays (mostres, canals). Si el dispositiu no admet fs, es remostreja a 48 kHz."""
        self.stop()
        a = _stereo32(a)
        b = _stereo32(b)
        if AVAILABLE:
            try:
                sd.check_output_settings(samplerate=fs, channels=2, dtype="float32")
            except Exception:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(int(fs), PREVIEW_FS)
                a = _stereo32(resample_poly(a, PREVIEW_FS // g, int(fs) // g, axis=0))
                b = _stereo32(resample_poly(b, PREVIEW_FS // g, int(fs) // g, axis=0))
                fs = PREVIEW_FS
        n = max(len(a), len(b))
        if len(a) < n:
            a = np.vstack([a, np.zeros((n - len(a), 2), np.float32)])
        if len(b) < n:
            b = np.vstack([b, np.zeros((n - len(b), 2), np.float32)])
        with self.lock:
            self.a, self.b, self.fs, self.pos = a, b, int(fs), 0
            # Igualació de nivell: s'abaixa el més fort (mai no se n'apuja cap)
            self.match_a = self.match_b = 1.0
            if lufs_a is not None and lufs_b is not None:
                diff = lufs_a - lufs_b
                if diff > 0:
                    self.match_a = 10 ** (-diff / 20.0)
                else:
                    self.match_b = 10 ** (diff / 20.0)

    def _callback(self, outdata, frames, time_info, status):
        with self.lock:
            src = self.a if self.which == "A" else self.b
            g = (self.match_a if self.which == "A" else self.match_b) if self.match else 1.0
            p = self.pos
            chunk = src[p:p + frames]
            n = len(chunk)
            outdata[:n] = chunk * g
            if n < frames:
                outdata[n:] = 0
            self.pos = p + frames
            if self.pos >= len(src):
                self.playing = False
                raise sd.CallbackStop()

    def play(self):
        if not AVAILABLE or self.a is None:
            return False
        self.stop()
        if self.pos >= self.length:
            self.pos = 0
        self.stream = sd.OutputStream(samplerate=self.fs, channels=2, dtype="float32", callback=self._callback,
                                      blocksize=1024)
        self.playing = True
        self.stream.start()
        return True

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.playing = False

    def set_which(self, which):
        with self.lock:
            self.which = which

    def seek(self, seconds):
        with self.lock:
            self.pos = max(0, min(int(seconds * self.fs), self.length))

    @property
    def position(self):
        return self.pos / float(self.fs) if self.fs else 0.0

    @property
    def duration(self):
        return self.length / float(self.fs) if self.fs else 0.0
