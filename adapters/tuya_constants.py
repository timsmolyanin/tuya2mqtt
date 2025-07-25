"""Проксируем все никак не связанные с транспортом константы/утилиты TinyTuya."""
import tinytuya

UDPPORT       = tinytuya.UDPPORT
UDPPORTS      = tinytuya.UDPPORTS
UDPPORTAPP    = tinytuya.UDPPORTAPP
SCANTIME      = tinytuya.SCANTIME
CONTROL       = tinytuya.CONTROL
__version__   = tinytuya.__version__

# utils
decrypt_udp   = tinytuya.decrypt_udp
termcolor     = tinytuya.termcolor
